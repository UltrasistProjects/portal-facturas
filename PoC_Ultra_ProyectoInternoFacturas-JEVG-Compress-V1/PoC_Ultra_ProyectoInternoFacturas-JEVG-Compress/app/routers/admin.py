from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.constants import (
    BUSINESS_RULES,
    DOCUMENT_REQUIREMENT_LABELS,
    FIXED_REQUIREMENT_REASONS,
    FORMAT_EXTENSIONS,
    Role,
    SupplierOrigin,
)
from app.core.database import get_db
from app.core.errors import BusinessRuleError, InvalidInputError
from app.core.security import hash_password, require_roles, validate_csrf
from app.models import AuditLog, Supplier, User
from app.repositories.pagination import paginate
from app.routers.common import templates
from app.schemas import UserCreate, validation_message
from app.services import document_requirements_service as requirements
from app.services import notification_templates as templates_service
from app.services import session_service
from app.services.audit_service import audit

router = APIRouter(prefix="/admin")


def _users_page(request: Request, db: Session, user, error: str | None = None, status_code: int = 200):
    context = {
        "user": user,
        "users": list(db.scalars(select(User).order_by(User.name))),
        "suppliers": list(db.scalars(select(Supplier))),
        "error": error,
    }
    return templates.TemplateResponse(request, "admin/users.html", context, status_code=status_code)


@router.get("/users")
def users(request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))):
    return _users_page(request, db, user)


@router.post("/users")
async def create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: Role = Form(...),
    supplier_id: int | None = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMIN)),
):
    await validate_csrf(request)
    try:
        data = UserCreate(name=name, email=email, password=password, role=role, supplier_id=supplier_id)
    except ValidationError as exc:
        return _users_page(request, db, user, validation_message(exc), 400)
    if db.scalar(select(User.id).where(User.email == data.email)):
        return _users_page(request, db, user, "Ya existe un usuario con ese correo.", 409)
    created = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
        supplier_id=data.supplier_id if data.role == Role.PROVIDER else None,
    )
    db.add(created)
    db.flush()
    audit(db, "USER_CREATED", "User", created.id, user.id)
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/toggle")
async def toggle_user(
    user_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))
):
    await validate_csrf(request)
    target = db.get(User, user_id)
    if target and target.id != user.id:
        old = target.is_active
        target.is_active = not old
        if not target.is_active:
            session_service.revoke_all_for_user(db, target.id)
        audit(
            db, "USER_STATUS_CHANGED", "User", target.id, user.id, {"is_active": old}, {"is_active": target.is_active}
        )
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


AUDIT_ENTRIES_PER_PAGE = 50


@router.get("/audit")
def audit_log(request: Request, page: int = 1, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))):
    stmt = select(AuditLog).options(joinedload(AuditLog.user)).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
    result = paginate(db, stmt, page, AUDIT_ENTRIES_PER_PAGE)
    context = {"user": user, "entries": result.items, "page": result, "base_query": ""}
    return templates.TemplateResponse(request, "admin/audit.html", context)


@router.get("/rules")
def rules(request: Request, user=Depends(require_roles(Role.ADMIN))):
    # Fuente unica: los mismos valores que aplica el motor de validacion (AUDITORIA COD-04).
    rules_data = BUSINESS_RULES
    return templates.TemplateResponse(request, "admin/rules.html", {"user": user, "rules": rules_data})


# Archivos minimos por tipo de proveedor (HU-04). La logica vive en document_requirements_service; estas rutas
# solo traducen HTTP. Los errores vuelven a pintar la pagina con su codigo; el exito redirige con ?ok=<clave>.
REQUIRED_DOCUMENTS_URL = "/admin/required-documents"
REQUIRED_DOCUMENTS_NOTICES = {
    "saved": "Configuración guardada",
    "unchanged": "Sin cambios",
    "created": "Tipo de documento creado",
    "updated": "Tipo de documento actualizado",
    "status": "Estado del tipo de documento actualizado",
}
ORIGIN_COLUMNS = [
    (SupplierOrigin.NATIONAL, "national", "Nacional"),
    (SupplierOrigin.INTERNATIONAL, "international", "Internacional"),
]


def _required_documents_page(
    request: Request, db: Session, user, error: str | None = None, status_code: int = 200, notice: str | None = None
):
    types = requirements.catalog(db)
    context = {
        "user": user,
        "active_types": [t for t in types if t.is_active],
        "inactive_types": [t for t in types if not t.is_active],
        "config_version": requirements.config_version(types),
        "origins": ORIGIN_COLUMNS,
        "levels": DOCUMENT_REQUIREMENT_LABELS,
        "formats": list(FORMAT_EXTENSIONS),
        "fixed_requirement": requirements.fixed_requirement,
        "fixed_reasons": FIXED_REQUIREMENT_REASONS,
        "formats_label": requirements.formats_label,
        "error": error,
        "notice": notice,
    }
    return templates.TemplateResponse(request, "admin/required_documents.html", context, status_code=status_code)


def _required_documents_error(request: Request, db: Session, user, exc: BusinessRuleError):
    db.rollback()  # nada se guarda y se libera el bloqueo consultivo antes de volver a pintar
    return _required_documents_page(request, db, user, exc.message, exc.status_code)


def _required_documents_done(result: str):
    return RedirectResponse(f"{REQUIRED_DOCUMENTS_URL}?ok={result}", status_code=303)


@router.get("/required-documents")
def required_documents(
    request: Request, ok: str = "", db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))
):
    return _required_documents_page(request, db, user, notice=REQUIRED_DOCUMENTS_NOTICES.get(ok))


@router.post("/required-documents")
async def save_required_documents(
    request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))
):
    await validate_csrf(request)
    form = {key: value for key, value in (await request.form()).items() if isinstance(value, str)}
    try:
        changed = requirements.save_requirements(db, form, user.id)
    except BusinessRuleError as exc:
        return _required_documents_error(request, db, user, exc)
    db.commit()
    return _required_documents_done("saved" if changed else "unchanged")


@router.post("/required-documents/types")
async def create_document_type(
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    formats: list[str] = Form([]),
    national_requirement: str = Form("NOT_APPLICABLE"),
    international_requirement: str = Form("NOT_APPLICABLE"),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMIN)),
):
    await validate_csrf(request)
    try:
        requirements.create_type(
            db, user.id, name, description, formats, national_requirement, international_requirement
        )
    except BusinessRuleError as exc:
        return _required_documents_error(request, db, user, exc)
    db.commit()
    return _required_documents_done("created")


@router.post("/required-documents/types/{type_id}")
async def update_document_type(
    type_id: int,
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    formats: list[str] = Form([]),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMIN)),
):
    await validate_csrf(request)
    try:
        changed = requirements.update_type(db, type_id, user.id, name, description, formats)
    except BusinessRuleError as exc:
        return _required_documents_error(request, db, user, exc)
    db.commit()
    return _required_documents_done("updated" if changed else "unchanged")


@router.post("/required-documents/types/{type_id}/status")
async def set_document_type_status(
    type_id: int,
    request: Request,
    active: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMIN)),
):
    await validate_csrf(request)
    try:
        if active not in {"true", "false"}:
            raise InvalidInputError("Estado inválido")
        changed = requirements.set_active(db, type_id, user.id, active == "true")
    except BusinessRuleError as exc:
        return _required_documents_error(request, db, user, exc)
    db.commit()
    return _required_documents_done("status" if changed else "unchanged")


# Plantillas de correo (HU-05). La logica vive en el servicio; estas rutas solo traducen HTTP (D11).
TEMPLATES_URL = "/admin/notification-templates"
DEFAULT_LOADED_NOTICE = "Se cargó el texto predeterminado. Pulse Guardar para aplicarlo."


def _template_editor(
    request: Request,
    user,
    spec: templates_service.EventSpec,
    subject: str,
    body: str,
    version: int,
    *,
    errors: list[str] | None = None,
    error: str | None = None,
    notice: str | None = None,
    preview: templates_service.ComposedEmail | None = None,
    status_code: int = 200,
):
    context = {
        "user": user,
        "spec": spec,
        "subject": subject,
        "body": body,
        "version": version,
        "errors": errors or [],
        "error": error,
        "notice": notice,
        "preview": preview,
    }
    return templates.TemplateResponse(
        request, "admin/notification_template_edit.html", context, status_code=status_code
    )


@router.get("/notification-templates")
def notification_templates(
    request: Request,
    updated: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMIN)),
):
    # El aviso solo se muestra para un codigo del catalogo: el parametro nunca se refleja tal cual.
    spec = templates_service.EVENTS.get(updated)
    context = {
        "user": user,
        "rows": templates_service.list_templates(db),
        "notice": f"Plantilla actualizada: {spec.label}." if spec else None,
    }
    return templates.TemplateResponse(request, "admin/notification_templates.html", context)


@router.get("/notification-templates/{code}")
def edit_notification_template(
    code: str,
    request: Request,
    load_default: bool = Query(False, alias="default"),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMIN)),
):
    spec = templates_service.spec_for_code(code)
    current = templates_service.get_template(db, spec)
    if load_default:  # solo llena el formulario: la plantilla no cambia hasta Guardar (RD-08)
        return _template_editor(
            request, user, spec, spec.default_subject, spec.default_body, current.version, notice=DEFAULT_LOADED_NOTICE
        )
    return _template_editor(request, user, spec, current.subject, current.body, current.version)


@router.post("/notification-templates/{code}/preview")
async def preview_notification_template(
    code: str,
    request: Request,
    subject: str = Form(""),
    body: str = Form(""),
    version: int = Form(0),
    user=Depends(require_roles(Role.ADMIN)),
):
    await validate_csrf(request)
    spec = templates_service.spec_for_code(code)
    draft = templates_service.check_draft(spec, subject, body)
    if draft.errors:
        return _template_editor(
            request, user, spec, draft.subject, draft.body, version, errors=draft.errors, status_code=400
        )
    preview = templates_service.compose_sample(spec, draft)
    return _template_editor(request, user, spec, draft.subject, draft.body, version, preview=preview)


@router.post("/notification-templates/{code}")
async def save_notification_template(
    code: str,
    request: Request,
    subject: str = Form(""),
    body: str = Form(""),
    version: int = Form(0),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMIN)),
):
    await validate_csrf(request)
    spec = templates_service.spec_for_code(code)
    try:
        templates_service.save_template(db, spec, subject, body, version, user)
    except templates_service.TemplateValidationError as exc:
        draft = exc.draft
        return _template_editor(
            request, user, spec, draft.subject, draft.body, version, errors=draft.errors, status_code=400
        )
    except templates_service.ConcurrentEditError as exc:
        # Se conserva la version enviada: guardar de nuevo vuelve a dar 409 hasta abrir la vigente (D12).
        return _template_editor(request, user, spec, subject, body, version, error=exc.message, status_code=409)
    return RedirectResponse(f"{TEMPLATES_URL}?updated={spec.event.value}", status_code=303)
