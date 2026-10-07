import logging
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.constants import (
    BUSINESS_RULES,
    CATALOG_CODE_FORMATS,
    CATALOG_LABELS,
    CODE_BOUND_WARNINGS,
    DOCUMENT_REQUIREMENT_LABELS,
    FORMAT_EXTENSIONS,
    REQUIREMENT_PROFILE_LABELS,
    CatalogType,
    RequirementProfile,
    Role,
    SupplierOrigin,
)
from app.core.database import get_db
from app.core.errors import BusinessRuleError, InvalidInputError, NotFoundError
from app.core.middleware import content_security_policy_with_styles
from app.core.security import require_roles, validate_csrf
from app.models import AuditLog, EmailDelivery, Supplier, User
from app.repositories.pagination import back_to, list_query, paginate, search
from app.routers.common import templates
from app.schemas import UserCreate, validation_message
from app.services import catalog_service as catalogs
from app.services import contract_requirements_service as contract_requirements
from app.services import document_requirements_service as requirements
from app.services import identity_service as identity
from app.services import mail_layout, session_service
from app.services import notification_service as notifications
from app.services import notification_templates as templates_service
from app.services import supplier_requirements_service as supplier_requirements
from app.services import validation_rules_service as validation_rules
from app.services.audit_service import audit
from app.services.catalog_template import build_catalog_template, template_filename
from app.services.keycloak_admin import IdentityAdmin, IdentityProviderError, get_identity_admin
from app.services.supplier_import_service import ImportFileError
from app.services.supplier_template import XLSX_MEDIA_TYPE

router = APIRouter(prefix="/admin")
logger = logging.getLogger(__name__)


USERS_URL = "/admin/users"
USER_NOTICES = {"created": "Usuario creado"}
# Deshabilitar no depende de Keycloak (D10): si no responde, el usuario igual queda sin acceso al portal.
USER_WARNINGS = {
    "idp_sync_failed": (
        "El usuario quedó deshabilitado en el portal, pero Keycloak no se actualizó: deshabilítelo también en la "
        "consola de Keycloak."
    )
}
# Un usuario Proveedor siempre esta vinculado a su proveedor (usuario-proveedor-vinculado; ck_users_provider_supplier).
MSG_SUPPLIER_REQUIRED = "Seleccione el proveedor del usuario"
MSG_SUPPLIER_NOT_FOUND = "Proveedor inexistente"
MSG_ORPHAN_PROVIDER = "El usuario no está vinculado a un proveedor: dé de alta uno nuevo con su proveedor"


def _users_page(
    request: Request,
    db: Session,
    user,
    error: str | None = None,
    status_code: int = 200,
    q: str = "",
    page: int = 1,
    notice: str | None = None,
    form: dict[str, str] | None = None,
    warning: str | None = None,
    credentials: dict[str, str] | None = None,
):
    # Busqueda y paginacion en SQL (listados-paginados); el proveedor de cada usuario, en una consulta.
    q = q.strip()
    stmt = select(User).options(selectinload(User.supplier)).order_by(User.name, User.id)
    result = paginate(db, search(stmt, q, User.name, User.email), page)
    context = {
        "user": user,
        "users": result.items,
        "page": result,
        "q": q,
        "base_query": list_query(q=q),
        "notice": notice,
        "suppliers": list(db.scalars(select(Supplier).order_by(Supplier.business_name))),
        "error": error,
        "warning": warning,
        # Alta rechazada: lo capturado se conserva.
        "form": form or {},
        # Alta exitosa: la contrasena temporal se muestra solo en esta respuesta (D15, D1-A).
        "credentials": credentials,
    }
    response = templates.TemplateResponse(request, "admin/users.html", context, status_code=status_code)
    if credentials:
        response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/users")
def users(
    request: Request,
    q: str = "",
    page: int = 1,
    ok: str = "",
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    return _users_page(request, db, user, q=q, page=page, notice=USER_NOTICES.get(ok), warning=USER_WARNINGS.get(ok))


@router.post("/users")
async def create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    role: Role = Form(...),
    supplier_id: int | None = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    await validate_csrf(request)
    form = {"name": name, "email": email, "role": role.value, "supplier_id": str(supplier_id or "")}

    def rejected(message: str, status_code: int):
        return _users_page(request, db, user, message, status_code, form=form)

    try:
        data = UserCreate(name=name, email=email, role=role, supplier_id=supplier_id)
    except ValidationError as exc:
        return rejected(validation_message(exc), 400)
    # El proveedor solo aplica al rol Proveedor, y ahi es obligatorio y debe existir.
    supplier_id = data.supplier_id if data.role == Role.PROVEEDOR else None
    if data.role == Role.PROVEEDOR and supplier_id is None:
        return rejected(MSG_SUPPLIER_REQUIRED, 400)
    if supplier_id is not None and db.get(Supplier, supplier_id) is None:
        return rejected(MSG_SUPPLIER_NOT_FOUND, 400)
    if db.scalar(select(User.id).where(User.email == data.email)):
        return rejected("Ya existe un usuario con ese correo.", 409)
    created = User(name=data.name, email=data.email, role=data.role, supplier_id=supplier_id)
    db.add(created)
    db.flush()
    # Cuenta en Keycloak dentro de la transaccion (D15): si Keycloak falla, no se crea nada.
    try:
        account = await run_in_threadpool(
            identity.provision, db, get_identity_admin(), email=data.email, role=data.role
        )
    except (identity.AccountConflict, IdentityProviderError) as exc:
        db.rollback()
        return rejected(exc.message, exc.status_code)
    created.keycloak_sub = account.sub
    audit(db, "USER_CREATED", "User", created.id, user.id, new={"role": data.role.value, "idp_account": account.origin})
    db.commit()
    # La respuesta muestra al usuario creado (busqueda por su correo) y su contrasena temporal, una sola vez.
    credentials = {"email": created.email, "password": account.password}
    return _users_page(request, db, user, q=created.email, notice=USER_NOTICES["created"], credentials=credentials)


@router.post("/users/{user_id}/toggle")
async def toggle_user(
    user_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMINISTRADOR))
):
    await validate_csrf(request)
    form = await request.form()
    target = db.get(User, user_id)
    warning = None
    if target and target.id != user.id:
        if not target.is_active and target.role == Role.PROVEEDOR and target.supplier_id is None:
            raise BusinessRuleError(MSG_ORPHAN_PROVIDER)
        old = target.is_active
        idp = get_identity_admin()
        if not old and target.keycloak_sub:
            # Habilitar: primero Keycloak; si no responde, el usuario sigue deshabilitado (D10).
            try:
                await run_in_threadpool(idp.set_enabled, target.keycloak_sub, True)
            except IdentityProviderError as exc:
                return _users_page(request, db, user, exc.message, exc.status_code)
        target.is_active = not old
        if not target.is_active:
            session_service.revoke_all_for_user(db, target.id)
        audit(
            db, "USER_STATUS_CHANGED", "User", target.id, user.id, {"is_active": old}, {"is_active": target.is_active}
        )
        db.commit()
        if old and target.keycloak_sub:
            # Deshabilitar: el portal ya le cerro el acceso; Keycloak se actualiza despues, sin revertir si falla.
            try:
                await run_in_threadpool(_disable_in_keycloak, idp, target.keycloak_sub)
            except IdentityProviderError as exc:
                audit(
                    db,
                    "IDP_SYNC_FAILED",
                    "User",
                    target.id,
                    user.id,
                    new={"operation": exc.operation, "error": exc.code},
                )
                db.commit()
                warning = "idp_sync_failed"
    url = back_to(USERS_URL, form)
    if warning:
        url += ("&" if "?" in url else "?") + list_query(ok=warning)
    return RedirectResponse(url, status_code=303)


def _disable_in_keycloak(idp: IdentityAdmin, sub: str) -> None:
    """Deshabilita la cuenta y cierra sus sesiones de Keycloak: no puede volver a entrar por SSO."""
    idp.set_enabled(sub, False)
    idp.logout(sub)


AUDIT_ENTRIES_PER_PAGE = 50


@router.get("/audit")
def audit_log(
    request: Request, page: int = 1, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMINISTRADOR))
):
    stmt = select(AuditLog).options(joinedload(AuditLog.user)).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
    result = paginate(db, stmt, page, AUDIT_ENTRIES_PER_PAGE)
    context = {"user": user, "entries": result.items, "page": result, "base_query": ""}
    return templates.TemplateResponse(request, "admin/audit.html", context)


# Reglas de Validacion por origen (ajustes-finales-configuracion). Fuente unica de los parametros del motor: la
# pagina lee las reglas con el mismo servicio que cada prevalidacion; los pesos del score siguen en BUSINESS_RULES.
RULES_URL = "/admin/rules"
RULE_ORIGINS = {"national": SupplierOrigin.NATIONAL, "international": SupplierOrigin.INTERNATIONAL}
RULE_TITLES = {"national": "Nacionales", "international": "Internacionales"}
RULES_NOTICES = {
    "updated": "Regla actualizada",
    "deleted": "Regla eliminada",
    "restored": "Regla restaurada",
    "unchanged": "Sin cambios",
}
RULE_ACTIONS = {"delete": ("delete_rule", "deleted"), "restore": ("restore_rule", "restored")}


def _rule_origin(origin_code: str) -> SupplierOrigin:
    origin = RULE_ORIGINS.get(origin_code)
    if origin is None:
        raise NotFoundError("Página no encontrada")
    return origin


def _rules_page(
    request: Request,
    db: Session,
    user,
    origin_code: str,
    *,
    draft: validation_rules.Draft | None = None,
    draft_rule_id: int | None = None,
    error: str | None = None,
    notice: str | None = None,
    status_code: int = 200,
):
    """Reglas del origen; con un borrador rechazado (400), su formulario abierto con lo capturado y sus errores."""
    views = validation_rules.page_rules(db, _rule_origin(origin_code))
    show = request.query_params.get("eliminados") == "1" or (
        draft_rule_id is not None and any(not v.rule.is_active and v.rule.id == draft_rule_id for v in views)
    )
    catalogs_used = {v.definition.catalog for v in views if v.definition.catalog is not None}
    context = {
        "user": user,
        "origin_code": origin_code,
        "title": RULE_TITLES[origin_code],
        "active_rules": [v for v in views if v.rule.is_active],
        "deleted_rules": [v for v in views if not v.rule.is_active] if show else [],
        "deleted_count": sum(not v.rule.is_active for v in views),
        "show_deleted": show,
        "options": {catalog: catalogs.active_entries(db, catalog) for catalog in catalogs_used},
        "currencies": sorted(catalogs.active_codes(db, CatalogType.CURRENCY)),
        "weights": BUSINESS_RULES["score_weights"],
        "draft": draft,
        "draft_rule_id": draft_rule_id,
        "error": error,
        "notice": notice,
    }
    return templates.TemplateResponse(request, "admin/rules.html", context, status_code=status_code)


def _rules_done(origin_code: str, result: str):
    return RedirectResponse(f"{RULES_URL}/{origin_code}?ok={result}", status_code=303)


def _rule_error(request: Request, db: Session, user, origin_code: str, exc: BusinessRuleError):
    """Vuelve a pintar la pagina con el error; un 400 de validacion conserva el borrador de su regla."""
    db.rollback()
    if isinstance(exc, validation_rules.RuleValidationError):
        return _rules_page(request, db, user, origin_code, draft=exc.draft, draft_rule_id=exc.rule.id, status_code=400)
    return _rules_page(request, db, user, origin_code, error=exc.message, status_code=exc.status_code)


@router.get("/rules")
def rules(user=Depends(require_roles(Role.ADMINISTRADOR))):
    return RedirectResponse(f"{RULES_URL}/national", status_code=303)


@router.get("/rules/{origin_code}")
def rules_by_origin(
    origin_code: str,
    request: Request,
    ok: str = "",
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    return _rules_page(request, db, user, origin_code, notice=RULES_NOTICES.get(ok))


@router.post("/rules/{origin_code}/{rule_id}")
async def update_rule(
    origin_code: str,
    rule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    await validate_csrf(request)
    origin = _rule_origin(origin_code)
    raw = await request.form()
    parameters = [value for value in raw.getlist("parameter") if isinstance(value, str)]
    try:
        version = int(str(raw.get("version", "")))
    except ValueError:
        version = 0
    try:
        changed = validation_rules.update_rule(
            db, origin, rule_id, str(raw.get("name", "")), parameters, version, user.id
        )
    except BusinessRuleError as exc:
        return _rule_error(request, db, user, origin_code, exc)
    db.commit()
    if changed:
        # Sin los valores de los campos (como el resto de los eventos de configuracion).
        logger.info(
            "validation_rule.updated",
            extra={"event": "validation_rule.updated", "origin": origin.value, "rule_id": rule_id, "fields": changed},
        )
    return _rules_done(origin_code, "updated" if changed else "unchanged")


@router.post("/rules/{origin_code}/{rule_id}/{action}")
async def change_rule_status(
    origin_code: str,
    rule_id: int,
    action: str,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    """Eliminar (baja logica) o Restaurar una regla."""
    await validate_csrf(request)
    origin = _rule_origin(origin_code)
    if action not in RULE_ACTIONS:
        raise NotFoundError("Página no encontrada")
    function, ok = RULE_ACTIONS[action]
    try:
        changed = getattr(validation_rules, function)(db, origin, rule_id, user.id)
    except BusinessRuleError as exc:
        return _rule_error(request, db, user, origin_code, exc)
    db.commit()
    return _rules_done(origin_code, ok if changed else "unchanged")


# Requisitos minimos: archivos de factura (HU-04), alta de proveedor (HU-21) y alta de contrato (HU-22). La logica vive
# en sus servicios; estas rutas solo traducen HTTP. Los errores vuelven a pintar la pagina con su codigo; el exito
# redirige con ?ok=<clave>. Por omision se listan solo los tipos activos; ?eliminados=1 agrega los eliminados.
REQUIRED_DOCUMENTS_URL = "/admin/required-documents"
SUPPLIER_REQUIREMENTS_URL = "/admin/supplier-requirements"
CONTRACT_REQUIREMENTS_URL = "/admin/contract-requirements"
REQUIRED_DOCUMENTS_NOTICES = {
    "saved": "Configuración guardada",
    "unchanged": "Sin cambios",
    "created": "Tipo de documento creado",
    "updated": "Tipo de documento actualizado",
    "deleted": "Tipo eliminado",
    "restored": "Tipo restaurado",
}
REQUIREMENT_NOTICES = {
    "saved": "Configuración guardada",
    "unchanged": "Sin cambios",
    "created": "Requisito creado",
    "updated": "Requisito actualizado",
    "deleted": "Requisito eliminado",
    "restored": "Requisito restaurado",
}
ORIGIN_COLUMNS = [
    (SupplierOrigin.NATIONAL, "national", "Nacional"),
    (SupplierOrigin.INTERNATIONAL, "international", "Internacional"),
]
PROFILE_COLUMNS = [(profile, REQUIREMENT_PROFILE_LABELS[profile]) for profile in RequirementProfile]


def _type_lists(request: Request, types: list) -> dict:
    """Tipos activos y, con ?eliminados=1, los eliminados; el total de eliminados alimenta el enlace."""
    deleted = [t for t in types if not t.is_active]
    show = request.query_params.get("eliminados") == "1"
    return {
        "active_types": [t for t in types if t.is_active],
        "deleted_types": deleted if show else [],
        "deleted_count": len(deleted),
        "show_deleted": show,
    }


def _required_documents_page(
    request: Request, db: Session, user, error: str | None = None, status_code: int = 200, notice: str | None = None
):
    types = requirements.catalog(db)
    context = {
        "user": user,
        **_type_lists(request, types),
        "config_version": requirements.config_version(types),
        "origins": ORIGIN_COLUMNS,
        "levels": DOCUMENT_REQUIREMENT_LABELS,
        "formats": list(FORMAT_EXTENSIONS),
        "warnings": CODE_BOUND_WARNINGS,
        "formats_label": requirements.formats_label,
        "error": error,
        "notice": notice,
    }
    return templates.TemplateResponse(request, "admin/required_documents.html", context, status_code=status_code)


def _supplier_requirements_page(
    request: Request, db: Session, user, error: str | None = None, status_code: int = 200, notice: str | None = None
):
    types = supplier_requirements.catalog(db)
    context = {
        "user": user,
        **_type_lists(request, types),
        "config_version": supplier_requirements.config_version(types),
        "profiles": PROFILE_COLUMNS,
        "levels": DOCUMENT_REQUIREMENT_LABELS,
        "error": error,
        "notice": notice,
    }
    return templates.TemplateResponse(request, "admin/supplier_requirements.html", context, status_code=status_code)


def _contract_requirements_page(
    request: Request, db: Session, user, error: str | None = None, status_code: int = 200, notice: str | None = None
):
    types = contract_requirements.catalog(db)
    context = {
        "user": user,
        **_type_lists(request, types),
        "config_version": contract_requirements.config_version(types),
        "levels": DOCUMENT_REQUIREMENT_LABELS,
        "error": error,
        "notice": notice,
    }
    return templates.TemplateResponse(request, "admin/contract_requirements.html", context, status_code=status_code)


@dataclass(frozen=True)
class RequirementScreen:
    """Una pantalla de Requisitos minimos: su URL, su servicio y como se pinta."""

    url: str
    service: ModuleType
    page: Callable


REQUIRED_DOCUMENTS = RequirementScreen(REQUIRED_DOCUMENTS_URL, requirements, _required_documents_page)
SUPPLIER_REQUIREMENTS = RequirementScreen(SUPPLIER_REQUIREMENTS_URL, supplier_requirements, _supplier_requirements_page)
CONTRACT_REQUIREMENTS = RequirementScreen(CONTRACT_REQUIREMENTS_URL, contract_requirements, _contract_requirements_page)
REQUIREMENT_SCREENS = {
    "required-documents": REQUIRED_DOCUMENTS,
    "supplier-requirements": SUPPLIER_REQUIREMENTS,
    "contract-requirements": CONTRACT_REQUIREMENTS,
}
TYPE_ACTIONS = {"delete": ("delete_type", "deleted"), "restore": ("restore_type", "restored")}


def _screen_error(screen: RequirementScreen, request: Request, db: Session, user, exc: BusinessRuleError):
    db.rollback()  # nada se guarda y se libera el bloqueo consultivo antes de volver a pintar
    return screen.page(request, db, user, exc.message, exc.status_code)


def _screen_done(screen: RequirementScreen, result: str):
    return RedirectResponse(f"{screen.url}?ok={result}", status_code=303)


@router.get("/required-documents")
def required_documents(
    request: Request, ok: str = "", db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMINISTRADOR))
):
    return _required_documents_page(request, db, user, notice=REQUIRED_DOCUMENTS_NOTICES.get(ok))


@router.get("/supplier-requirements")
def supplier_requirements_page(
    request: Request, ok: str = "", db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMINISTRADOR))
):
    return _supplier_requirements_page(request, db, user, notice=REQUIREMENT_NOTICES.get(ok))


@router.get("/contract-requirements")
def contract_requirements_page(
    request: Request, ok: str = "", db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMINISTRADOR))
):
    return _contract_requirements_page(request, db, user, notice=REQUIREMENT_NOTICES.get(ok))


async def _save_levels(screen: RequirementScreen, request: Request, db: Session, user):
    await validate_csrf(request)
    form = {key: value for key, value in (await request.form()).items() if isinstance(value, str)}
    try:
        changed = screen.service.save_requirements(db, form, user.id)
    except BusinessRuleError as exc:
        return _screen_error(screen, request, db, user, exc)
    db.commit()
    return _screen_done(screen, "saved" if changed else "unchanged")


@router.post("/required-documents")
async def save_required_documents(
    request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMINISTRADOR))
):
    return await _save_levels(REQUIRED_DOCUMENTS, request, db, user)


@router.post("/supplier-requirements")
async def save_supplier_requirements(
    request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMINISTRADOR))
):
    return await _save_levels(SUPPLIER_REQUIREMENTS, request, db, user)


@router.post("/contract-requirements")
async def save_contract_requirements(
    request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMINISTRADOR))
):
    return await _save_levels(CONTRACT_REQUIREMENTS, request, db, user)


async def _write_type(
    screen: RequirementScreen, request: Request, db: Session, user, write: Callable[[], bool], ok: str
):
    """Alta o edicion de un tipo: `write` llama al servicio y devuelve si hubo cambios."""
    await validate_csrf(request)
    try:
        changed = write()
    except BusinessRuleError as exc:
        return _screen_error(screen, request, db, user, exc)
    db.commit()
    return _screen_done(screen, ok if changed else "unchanged")


@router.post("/required-documents/types")
async def create_document_type(
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    formats: list[str] = Form([]),
    national_requirement: str = Form("NOT_APPLICABLE"),
    international_requirement: str = Form("NOT_APPLICABLE"),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    def write() -> bool:
        requirements.create_type(
            db, user.id, name, description, formats, national_requirement, international_requirement
        )
        return True

    return await _write_type(REQUIRED_DOCUMENTS, request, db, user, write, "created")


@router.post("/required-documents/types/{type_id}")
async def update_document_type(
    type_id: int,
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    formats: list[str] = Form([]),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    def write() -> bool:
        return requirements.update_type(db, type_id, user.id, name, description, formats)

    return await _write_type(REQUIRED_DOCUMENTS, request, db, user, write, "updated")


@router.post("/supplier-requirements/types")
async def create_supplier_requirement(
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    persona_moral_requirement: str = Form("NOT_APPLICABLE"),
    persona_fisica_requirement: str = Form("NOT_APPLICABLE"),
    international_requirement: str = Form("NOT_APPLICABLE"),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    def write() -> bool:
        supplier_requirements.create_type(
            db,
            user.id,
            name,
            description,
            persona_moral_requirement=persona_moral_requirement,
            persona_fisica_requirement=persona_fisica_requirement,
            international_requirement=international_requirement,
        )
        return True

    return await _write_type(SUPPLIER_REQUIREMENTS, request, db, user, write, "created")


@router.post("/supplier-requirements/types/{type_id}")
async def update_supplier_requirement(
    type_id: int,
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    def write() -> bool:
        return supplier_requirements.update_type(db, type_id, user.id, name, description)

    return await _write_type(SUPPLIER_REQUIREMENTS, request, db, user, write, "updated")


@router.post("/contract-requirements/types")
async def create_contract_requirement(
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    requirement: str = Form("NOT_APPLICABLE"),
    allows_multiple: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    def write() -> bool:
        contract_requirements.create_type(
            db, user.id, name, description, requirement=requirement, allows_multiple=allows_multiple == "true"
        )
        return True

    return await _write_type(CONTRACT_REQUIREMENTS, request, db, user, write, "created")


@router.post("/contract-requirements/types/{type_id}")
async def update_contract_requirement(
    type_id: int,
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    def write() -> bool:
        return contract_requirements.update_type(db, type_id, user.id, name, description)

    return await _write_type(CONTRACT_REQUIREMENTS, request, db, user, write, "updated")


@router.post("/{screen_code}/types/{type_id}/{action}")
async def change_type_status(
    screen_code: str,
    type_id: int,
    action: str,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    """Eliminar (baja logica) o Restaurar un tipo de cualquiera de las tres pantallas de Requisitos minimos."""
    await validate_csrf(request)
    screen = REQUIREMENT_SCREENS.get(screen_code)
    if screen is None or action not in TYPE_ACTIONS:
        raise NotFoundError("Página no encontrada")
    function, ok = TYPE_ACTIONS[action]

    def write() -> bool:
        return getattr(screen.service, function)(db, type_id, user.id)

    return await _write_type(screen, request, db, user, write, ok)


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
    preview_html: str | None = None,
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
        "preview_html": preview_html,
    }
    return templates.TemplateResponse(
        request, "admin/notification_template_edit.html", context, status_code=status_code
    )


@router.get("/notification-templates")
def notification_templates(
    request: Request,
    updated: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
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
    user=Depends(require_roles(Role.ADMINISTRADOR)),
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
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    await validate_csrf(request)
    spec = templates_service.spec_for_code(code)
    draft = templates_service.check_draft(spec, subject, body)
    if draft.errors:
        return _template_editor(
            request, user, spec, draft.subject, draft.body, version, errors=draft.errors, status_code=400
        )
    preview = templates_service.compose_sample(spec, draft)
    # El correo tal como se envia, en un iframe srcdoc que hereda la CSP: se admiten solo sus atributos style.
    preview_html = mail_layout.render_preview(preview.subject, preview.body)
    response = _template_editor(
        request, user, spec, draft.subject, draft.body, version, preview=preview, preview_html=preview_html
    )
    hashes = mail_layout.style_hashes(preview_html)
    response.headers["Content-Security-Policy"] = content_security_policy_with_styles(hashes)
    return response


@router.post("/notification-templates/{code}")
async def save_notification_template(
    code: str,
    request: Request,
    subject: str = Form(""),
    body: str = Form(""),
    version: int = Form(0),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
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


# Destinatarios de notificaciones y correo de prueba (HU-08). La logica vive en notification_service; estas rutas solo
# traducen HTTP. Los errores vuelven a pintar la pagina con lo capturado; el exito redirige (?ok=<clave> o ?test=<id>).
NOTIFICATIONS_URL = "/admin/notifications"
NOTIFICATIONS_NOTICES = {"saved": "Configuración guardada", "unchanged": "Sin cambios"}


def _notifications_page(
    request: Request,
    db: Session,
    user,
    *,
    values: dict[str, str] | None = None,
    errors: list[str] | None = None,
    error: str | None = None,
    notice: str | None = None,
    test_delivery: EmailDelivery | None = None,
    test_address: str = "",
    test_errors: list[str] | None = None,
    status_code: int = 200,
    page: int = 1,
):
    config = notifications.load(db)
    lists = notifications.recipient_lists(config)
    deliveries = notifications.deliveries_page(db, page)
    context = {
        "user": user,
        "mailbox": lists[0],
        "copies": lists[1:],
        "values": values or {item.key: "\n".join(item.addresses) for item in lists},
        "config_version": notifications.config_version(config),
        "errors": errors or [],
        "error": error,
        "notice": notice,
        "test_delivery": test_delivery,
        "test_address": test_address,
        "test_errors": test_errors or [],
        "transport": notifications.transport_summary(),
        "deliveries": deliveries.items,
        "page": deliveries,
        "base_query": "",
        "delivery_label": notifications.delivery_label,
        "format_datetime": templates_service.format_datetime,
    }
    return templates.TemplateResponse(request, "admin/notifications.html", context, status_code=status_code)


@router.get("/notifications")
def notification_settings(
    request: Request,
    ok: str = "",
    test: int | None = None,
    page: int = 1,
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    # El resultado de la prueba se lee de la bitacora: el parametro nunca se refleja tal cual.
    delivery = db.get(EmailDelivery, test) if test else None
    if delivery is not None and delivery.event is not None:
        delivery = None
    return _notifications_page(
        request, db, user, notice=NOTIFICATIONS_NOTICES.get(ok), test_delivery=delivery, page=page
    )


@router.post("/notifications")
async def save_notification_settings(
    request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMINISTRADOR))
):
    await validate_csrf(request)
    form = {key: value for key, value in (await request.form()).items() if isinstance(value, str)}
    try:
        changed = notifications.save_recipients(db, form, user)
    except notifications.RecipientsValidationError as exc:
        db.rollback()  # libera el bloqueo consultivo antes de volver a pintar
        return _notifications_page(request, db, user, values=form, errors=exc.errors, status_code=exc.status_code)
    except BusinessRuleError as exc:
        db.rollback()
        return _notifications_page(request, db, user, values=form, error=exc.message, status_code=exc.status_code)
    return RedirectResponse(f"{NOTIFICATIONS_URL}?ok={'saved' if changed else 'unchanged'}", status_code=303)


@router.post("/notifications/test")
async def send_test_notification(
    request: Request,
    address: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    await validate_csrf(request)
    try:
        delivery = notifications.send_test(db, address, user)
    except notifications.RecipientsValidationError as exc:
        return _notifications_page(
            request, db, user, test_address=address, test_errors=exc.errors, status_code=exc.status_code
        )
    return RedirectResponse(f"{NOTIFICATIONS_URL}?test={delivery.id}", status_code=303)


# Catalogos de referencia (HU-07). La logica vive en catalog_service; estas rutas solo traducen HTTP. Las rutas
# /import y /template se declaran antes de /{entry_id}: de lo contrario "import" se tomaria como un id (422).
CATALOGS_URL = "/admin/catalogs"
CATALOG_NOTICES = {
    "created": "Clave agregada",
    "updated": "Descripción actualizada",
    "status": "Estado de la clave actualizado",
    "unchanged": "Sin cambios",
}


@router.get("/catalogs")
def catalog_list(request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMINISTRADOR))):
    context = {"user": user, "catalogs": catalogs.summaries(db)}
    return templates.TemplateResponse(request, "admin/catalogs.html", context)


def _catalog_page(
    request: Request,
    db: Session,
    user,
    catalog: CatalogType,
    *,
    error: str | None = None,
    notice: str | None = None,
    result: catalogs.ImportResult | None = None,
    import_error: str | None = None,
    status_code: int = 200,
    q: str = "",
    page: int = 1,
):
    q = q.strip()
    result_page = catalogs.page_entries(db, catalog, q, page)
    context = {
        "user": user,
        "catalog": catalog,
        "label": CATALOG_LABELS[catalog],
        "entries": result_page.items,
        "page": result_page,
        "q": q,
        "base_query": list_query(q=q),
        "counts": catalogs.counts(db, catalog),
        "in_use": catalogs.in_use(db)[catalog],
        "code_format": CATALOG_CODE_FORMATS[catalog][1],
        "max_rows": catalogs.MAX_ROWS,
        "error": error,
        "notice": notice,
        "result": result,
        "import_error": import_error,
    }
    return templates.TemplateResponse(request, "admin/catalog.html", context, status_code=status_code)


def _catalog_done(catalog: CatalogType, result: str, form=None, q: str = ""):
    """Al catalogo con el aviso: tras una accion en una fila, en la misma busqueda y pagina; tras un alta, buscando la
    clave creada (listados-paginados)."""
    url = back_to(f"{CATALOGS_URL}/{catalog.value}", form or {"q": q})
    return RedirectResponse(f"{url}{'&' if '?' in url else '?'}ok={result}", status_code=303)


@router.get("/catalogs/{code}")
def catalog_detail(
    code: str,
    request: Request,
    ok: str = "",
    q: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    catalog = catalogs.catalog_for_code(code)
    return _catalog_page(request, db, user, catalog, notice=CATALOG_NOTICES.get(ok), q=q, page=page)


@router.get("/catalogs/{code}/template")
def catalog_template(code: str, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMINISTRADOR))):
    catalog = catalogs.catalog_for_code(code)
    content = build_catalog_template(catalog, catalogs.entries(db, catalog))
    headers = {"Content-Disposition": f'attachment; filename="{template_filename(catalog)}"'}
    return Response(content, media_type=XLSX_MEDIA_TYPE, headers=headers)


@router.post("/catalogs/{code}/import")
async def import_catalog(
    code: str,
    request: Request,
    upload: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    await validate_csrf(request)
    catalog = catalogs.catalog_for_code(code)
    content = await upload.read(catalogs.MAX_FILE_BYTES + 1) if upload else b""
    try:
        result = catalogs.import_catalog(db, catalog, upload.filename if upload else None, content, user.id)
    except ImportFileError as exc:
        return _catalog_page(request, db, user, catalog, import_error=exc.message, status_code=400)
    return _catalog_page(request, db, user, catalog, result=result, status_code=400 if result.invalid else 200)


@router.post("/catalogs/{code}")
async def create_catalog_entry(
    code: str,
    request: Request,
    entry_code: str = Form(""),
    name: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    await validate_csrf(request)
    catalog = catalogs.catalog_for_code(code)
    try:
        created = catalogs.create_entry(db, catalog, entry_code, name, user.id)
    except NotFoundError:
        raise
    except BusinessRuleError as exc:
        db.rollback()
        return _catalog_page(request, db, user, catalog, error=exc.message, status_code=exc.status_code)
    db.commit()
    return _catalog_done(catalog, "created", q=created.code)


@router.post("/catalogs/{code}/{entry_id}")
async def update_catalog_entry(
    code: str,
    entry_id: int,
    request: Request,
    name: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    await validate_csrf(request)
    catalog = catalogs.catalog_for_code(code)
    try:
        changed = catalogs.update_entry(db, catalog, entry_id, name, user.id)
    except NotFoundError:
        raise
    except BusinessRuleError as exc:
        db.rollback()
        return _catalog_page(request, db, user, catalog, error=exc.message, status_code=exc.status_code)
    db.commit()
    return _catalog_done(catalog, "updated" if changed else "unchanged", await request.form())


@router.post("/catalogs/{code}/{entry_id}/status")
async def set_catalog_entry_status(
    code: str,
    entry_id: int,
    request: Request,
    active: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    await validate_csrf(request)
    catalog = catalogs.catalog_for_code(code)
    try:
        if active not in {"true", "false"}:
            raise InvalidInputError("Estado inválido")
        changed = catalogs.set_active(db, catalog, entry_id, active == "true", user.id)
    except NotFoundError:
        raise
    except BusinessRuleError as exc:
        db.rollback()
        return _catalog_page(request, db, user, catalog, error=exc.message, status_code=exc.status_code)
    db.commit()
    return _catalog_done(catalog, "status" if changed else "unchanged", await request.form())
