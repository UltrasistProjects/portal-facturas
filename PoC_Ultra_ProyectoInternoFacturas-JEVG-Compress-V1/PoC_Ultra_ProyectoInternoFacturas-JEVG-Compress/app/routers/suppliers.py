import unicodedata
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.constants import (
    SUPPLIER_CLASSIFICATION_LABELS,
    SUPPLIER_ORIGIN_LABELS,
    SUPPLIER_STATUS_LABELS,
    CatalogType,
    ProcessingStatus,
    Role,
    SupplierStatus,
    SupplierType,
)
from app.core.countries import COUNTRIES
from app.core.database import get_db
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.security import get_current_user, require_roles, validate_csrf
from app.models import Document, EmailDelivery, Supplier
from app.repositories.pagination import list_query, paginate, search
from app.routers.common import templates
from app.schemas import SupplierCreate, SupplierUpdate, validation_message
from app.services import supplier_access_service as access
from app.services import supplier_import_service, supplier_service
from app.services.audit_service import audit
from app.services.catalog_service import active_entries
from app.services.file_service import LocalFileStorage, log_upload, safe_download_name
from app.services.notification_templates import format_datetime
from app.services.supplier_service import PROFILE_FIELDS, supplier_requirement_status
from app.services.supplier_template import MAX_FILE_MB, MAX_ROWS, TEMPLATE_FILENAME, XLSX_MEDIA_TYPE, build_template

router = APIRouter(prefix="/suppliers")

CREATE_FIELDS = ("origin", "rfc", "foreign_tax_id", "country", "supplier_type", "email", *PROFILE_FIELDS)
# Pais del proveedor internacional, por nombre sin acentos; Mexico corresponde al origen Nacional.
COUNTRY_OPTIONS = sorted(
    ((code, name) for code, name in COUNTRIES.items() if code != "MX"),
    key=lambda option: unicodedata.normalize("NFKD", option[1]).encode("ascii", "ignore"),
)


def portal_url(request: Request) -> str:
    """Direccion de inicio de sesion que llega en el correo de credenciales (HU-03, S6)."""
    return str(request.url_for("login_page"))


async def _submitted(request: Request, names: tuple[str, ...]) -> dict[str, str]:
    """Valores capturados en el formulario. Los vacios se omiten: el esquema los trata como faltantes."""
    form = await request.form()
    values = {name: form.get(name) for name in names}
    return {name: value.strip() for name, value in values.items() if isinstance(value, str) and value.strip()}


def _profile_values(supplier: Supplier) -> dict[str, str]:
    """Valores actuales del proveedor para el formulario de edicion, como llegarian del formulario: una casilla
    marcada es "true" y una sin marcar, vacia."""
    values = {name: getattr(supplier, name) for name in PROFILE_FIELDS}
    return {name: _form_value(value) for name, value in values.items()}


def _form_value(value) -> str:
    if value is True:
        return "true"
    return "" if value is None or value is False else str(value)


@router.get("")
def list_suppliers(
    request: Request,
    status: str = "",
    q: str = "",
    page: int = 1,
    authorization: int | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.PMO, Role.ADMINISTRADOR)),
):
    # El resumen se reconstruye de la auditoria: el parametro nunca se refleja tal cual (D5).
    summary = (
        access.authorization_summary(db, authorization) if authorization and user.role == Role.ADMINISTRADOR else None
    )
    return _suppliers_page(request, db, user, status_filter=status, summary=summary, q=q, page=page)


def _suppliers_page(
    request: Request,
    db: Session,
    user,
    error: str | None = None,
    status_code: int = 200,
    status_filter: str = "",
    summary: access.AuthorizationSummary | None = None,
    form: dict[str, str] | None = None,
    q: str = "",
    page: int = 1,
):
    # Busqueda, filtro y paginacion en SQL (listados-paginados); los contratos de la pagina, en una consulta.
    stmt = select(Supplier).options(selectinload(Supplier.contracts)).order_by(Supplier.business_name, Supplier.id)
    if status_filter in SupplierStatus.__members__:
        stmt = stmt.where(Supplier.status == SupplierStatus(status_filter))
    else:
        status_filter = ""
    q = q.strip()
    stmt = search(stmt, q, Supplier.business_name, Supplier.rfc, Supplier.foreign_tax_id, Supplier.email)
    result = paginate(db, stmt, page)
    is_admin = user.role == Role.ADMINISTRADOR
    context = {
        "user": user,
        "suppliers": result.items,
        "page": result,
        "q": q,
        "base_query": list_query(q=q, status=status_filter),
        "error": error,
        "status_filter": status_filter,
        "status_options": [(status.value, label) for status, label in SUPPLIER_STATUS_LABELS.items()],
        "failed_credentials": access.failed_credentials(db) if is_admin else set(),
        "summary": summary,
        "max_batch": access.MAX_BATCH,
        # Formulario de alta: lo capturado se conserva cuando el alta se rechaza.
        "form": form or {},
        "activities": active_entries(db, CatalogType.INDUSTRY) if is_admin else [],
        "classification_options": SUPPLIER_CLASSIFICATION_LABELS.items(),
        "type_options": [SupplierType.PERSONA_MORAL, SupplierType.PERSONA_FISICA],
        "origin_options": SUPPLIER_ORIGIN_LABELS.items(),
        "country_options": COUNTRY_OPTIONS,
    }
    return templates.TemplateResponse(request, "suppliers/list.html", context, status_code=status_code)


@router.post("")
async def create_supplier(
    request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMINISTRADOR))
):
    await validate_csrf(request)
    submitted = await _submitted(request, CREATE_FIELDS)
    try:
        supplier = supplier_service.create_supplier(db, SupplierCreate(**submitted), user.id)
    except ValidationError as exc:
        return _suppliers_page(request, db, user, validation_message(exc), 400, form=submitted)
    except BusinessRuleError as exc:
        db.rollback()
        return _suppliers_page(request, db, user, exc.message, exc.status_code, form=submitted)
    db.commit()
    return RedirectResponse(f"/suppliers/{supplier.id}", status_code=303)


# Las rutas /import se declaran antes de /{supplier_id}: de lo contrario "import" se tomaria como un id (422).
@router.get("/import")
def import_page(request: Request, user=Depends(require_roles(Role.ADMINISTRADOR))):
    context = {"user": user, "max_rows": MAX_ROWS, "max_file_mb": MAX_FILE_MB}
    return templates.TemplateResponse(request, "suppliers/import.html", context)


@router.get("/import/template")
def import_template(user=Depends(require_roles(Role.ADMINISTRADOR))):
    headers = {"Content-Disposition": f'attachment; filename="{TEMPLATE_FILENAME}"'}
    return Response(build_template(), media_type=XLSX_MEDIA_TYPE, headers=headers)


@router.post("/import")
async def import_suppliers(
    request: Request,
    upload: UploadFile | None = File(None),
    mode: str = Form(supplier_import_service.STRICT),
    expected_sha256: str | None = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    """Siempre responde JSON (contrato D12); la pagina de carga lo consume con fetch."""
    await validate_csrf(request)
    content = await upload.read(supplier_import_service.MAX_FILE_BYTES + 1) if upload else b""
    status_code, body = supplier_import_service.import_suppliers(
        db, user, upload.filename if upload else None, content, mode, expected_sha256
    )
    return JSONResponse(body, status_code=status_code)


@router.post("/authorize")
async def authorize_suppliers(
    request: Request,
    supplier_ids: list[str] = Form([]),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    """Autorizacion masiva (HU-02) y envio de credenciales (HU-03). La logica vive en supplier_access_service; corre en
    el threadpool porque llama a Keycloak de forma sincrona."""
    await validate_csrf(request)
    try:
        result = await run_in_threadpool(access.authorize, db, supplier_ids, user, portal_url(request))
    except BusinessRuleError as exc:
        db.rollback()
        return _suppliers_page(request, db, user, exc.message, exc.status_code)
    return RedirectResponse(f"/suppliers?authorization={result.audit_id}", status_code=303)


def _supplier_detail_page(
    request: Request,
    db: Session,
    user,
    supplier: Supplier,
    access_error: str | None = None,
    credentials_result: EmailDelivery | None = None,
    status_code: int = 200,
    profile_error: str | None = None,
    profile_form: dict[str, str] | None = None,
):
    docs = list(db.scalars(select(Document).where(Document.supplier_id == supplier.id, Document.invoice_id.is_(None))))
    context = {
        "user": user,
        "supplier": supplier,
        "activity_name": supplier_service.activity_name(db, supplier.main_activity),
        "requirements": supplier_requirement_status(supplier, docs),
        "access_error": access_error,
        "credentials_result": credentials_result,
        "format_datetime": format_datetime,
    }
    if user.role == Role.ADMINISTRADOR:
        portal_user = access.provider_user(db, supplier)
        # Estado de la contrasena leido de Keycloak (D14): "No disponible" si no responde, sin que la pagina falle.
        password = access.password_state(portal_user)
        context["access"] = {
            "user": portal_user,
            "password": password,
            "delivery": access.credentials_status(db, supplier.id),
            "can_resend": access.can_resend(supplier, portal_user, password),
        }
        # Formulario de edicion: lo capturado se conserva cuando la edicion se rechaza.
        context["profile"] = profile_form if profile_form is not None else _profile_values(supplier)
        context["profile_error"] = profile_error
        context["activities"] = supplier_service.activity_options(db, supplier.main_activity)
        context["classification_options"] = SUPPLIER_CLASSIFICATION_LABELS.items()
    return templates.TemplateResponse(request, "suppliers/detail.html", context, status_code=status_code)


@router.get("/{supplier_id}")
def supplier_detail(
    supplier_id: int,
    request: Request,
    credentials: int | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if user.role == Role.PROVEEDOR and user.supplier_id != supplier_id:
        raise HTTPException(403, "Acceso denegado")
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(404, "Proveedor no encontrado")
    # El resultado del reenvio se lee de la bitacora y solo si es un envio de credenciales de este proveedor.
    result = db.get(EmailDelivery, credentials) if credentials and user.role == Role.ADMINISTRADOR else None
    if result is not None and (result.event != access.CREDENTIALS or result.entity_id != str(supplier.id)):
        result = None
    return _supplier_detail_page(request, db, user, supplier, credentials_result=result)


@router.post("/{supplier_id}/credentials")
async def resend_credentials(
    supplier_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMINISTRADOR))
):
    await validate_csrf(request)
    try:
        delivery = await run_in_threadpool(access.resend_credentials, db, supplier_id, user, portal_url(request))
    except NotFoundError:
        raise
    except BusinessRuleError as exc:
        db.rollback()
        supplier = db.get(Supplier, supplier_id)
        return await run_in_threadpool(
            _supplier_detail_page, request, db, user, supplier, access_error=exc.message, status_code=exc.status_code
        )
    return RedirectResponse(f"/suppliers/{supplier_id}?credentials={delivery.id}", status_code=303)


@router.post("/{supplier_id}/profile")
async def update_supplier(
    supplier_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMINISTRADOR))
):
    await validate_csrf(request)
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(404, "Proveedor no encontrado")
    submitted = await _submitted(request, PROFILE_FIELDS)
    try:
        data = SupplierUpdate(**submitted, supplier_type=supplier.supplier_type)
        supplier_service.update_supplier(db, supplier, data, user.id)
    except ValidationError as exc:
        return await run_in_threadpool(
            _supplier_detail_page,
            request,
            db,
            user,
            supplier,
            status_code=400,
            profile_error=validation_message(exc),
            profile_form=submitted,
        )
    except BusinessRuleError as exc:
        db.rollback()
        return await run_in_threadpool(
            _supplier_detail_page,
            request,
            db,
            user,
            supplier,
            status_code=exc.status_code,
            profile_error=exc.message,
            profile_form=submitted,
        )
    db.commit()
    return RedirectResponse(f"/suppliers/{supplier.id}", status_code=303)


@router.post("/{supplier_id}/documents")
async def upload_supplier_document(
    supplier_id: int,
    request: Request,
    document_type: str = Form(...),
    document_date: date | None = Form(None),
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    await validate_csrf(request)
    if user.role == Role.PMO or (user.role == Role.PROVEEDOR and user.supplier_id != supplier_id):
        raise HTTPException(403, "No puede modificar este expediente")
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(404, "Proveedor no encontrado")
    allowed = {row["code"] for row in supplier_requirement_status(supplier, [])}
    if document_type not in allowed:
        raise HTTPException(400, "Tipo de Anexo A invalido")
    try:
        stored = await LocalFileStorage().save_supplier_file(supplier.id, upload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    previous = db.scalar(
        select(Document).where(
            Document.supplier_id == supplier.id,
            Document.invoice_id.is_(None),
            Document.document_type == document_type,
            Document.is_current.is_(True),
        )
    )
    if previous:
        previous.is_current = False
    document = Document(
        supplier_id=supplier.id,
        document_type=document_type,
        original_filename=stored.original_filename,
        stored_filename=stored.stored_filename,
        path=stored.relative_path,
        mime_type=stored.mime_type,
        file_size=stored.file_size,
        sha256=stored.sha256,
        uploaded_by=user.id,
        processing_status=ProcessingStatus.PROCESSED,
        document_date=document_date,
        metadata_json={"scope": "supplier"},
        replaced_document_id=previous.id if previous else None,
    )
    db.add(document)
    db.flush()
    log_upload(document_type, stored, supplier_id=supplier.id)
    audit(
        db,
        "SUPPLIER_DOCUMENT_REPLACED" if previous else "SUPPLIER_DOCUMENT_UPLOADED",
        "Document",
        document.id,
        user.id,
        new={"type": document_type},
    )
    db.commit()
    return RedirectResponse(f"/suppliers/{supplier.id}", status_code=303)


@router.get("/{supplier_id}/documents/{document_id}/download")
def download_supplier_document(
    supplier_id: int, document_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    # Mismo acceso que el expediente: el proveedor solo el suyo; PMO y Administrador, cualquiera.
    if user.role == Role.PROVEEDOR and user.supplier_id != supplier_id:
        raise HTTPException(403, "Acceso denegado")
    doc = db.get(Document, document_id)
    if not doc or doc.supplier_id != supplier_id or doc.invoice_id is not None:
        raise HTTPException(404, "Documento no encontrado")
    try:
        path = LocalFileStorage().resolve(doc.path)
    except FileNotFoundError:
        raise HTTPException(404, "Archivo no disponible") from None
    if not path.is_file():
        raise HTTPException(404, "Archivo no disponible")
    # Nunca el MIME almacenado: la descarga no debe interpretarse en el navegador (junto con nosniff).
    return FileResponse(path, filename=safe_download_name(doc.original_filename), media_type="application/octet-stream")
