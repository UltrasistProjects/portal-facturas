from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    SUPPLIER_STATUS_LABELS,
    ProcessingStatus,
    Role,
    SupplierStatus,
    SupplierType,
)
from app.core.database import get_db
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.security import get_current_user, require_roles, validate_csrf
from app.models import Document, EmailDelivery, Supplier, User
from app.routers.common import templates
from app.schemas import SupplierCreate, validation_message
from app.services import supplier_access_service as access
from app.services import supplier_import_service
from app.services.audit_service import audit
from app.services.file_service import LocalFileStorage, log_upload
from app.services.notification_templates import format_datetime
from app.services.supplier_service import supplier_requirement_status
from app.services.supplier_template import MAX_FILE_MB, MAX_ROWS, TEMPLATE_FILENAME, XLSX_MEDIA_TYPE, build_template

router = APIRouter(prefix="/suppliers")


MSG_EMAIL_IN_USE = "El correo ya lo usa otro proveedor o usuario."


def portal_url(request: Request) -> str:
    """Direccion de inicio de sesion que llega en el correo de credenciales (HU-03, S6)."""
    return str(request.url_for("login_page"))


@router.get("")
def list_suppliers(
    request: Request,
    status: str = "",
    authorization: int | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.INTERNAL, Role.ADMIN)),
):
    # El resumen se reconstruye de la auditoria: el parametro nunca se refleja tal cual (D5).
    summary = access.authorization_summary(db, authorization) if authorization and user.role == Role.ADMIN else None
    return _suppliers_page(request, db, user, status_filter=status, summary=summary)


def _suppliers_page(
    request: Request,
    db: Session,
    user,
    error: str | None = None,
    status_code: int = 200,
    status_filter: str = "",
    summary: access.AuthorizationSummary | None = None,
):
    stmt = select(Supplier).order_by(Supplier.business_name)
    if status_filter in SupplierStatus.__members__:
        stmt = stmt.where(Supplier.status == SupplierStatus(status_filter))
    else:
        status_filter = ""
    context = {
        "user": user,
        "suppliers": list(db.scalars(stmt)),
        "error": error,
        "status_filter": status_filter,
        "status_options": [(status.value, label) for status, label in SUPPLIER_STATUS_LABELS.items()],
        "failed_credentials": access.failed_credentials(db) if user.role == Role.ADMIN else set(),
        "summary": summary,
        "max_batch": access.MAX_BATCH,
    }
    return templates.TemplateResponse(request, "suppliers/list.html", context, status_code=status_code)


@router.post("")
async def create_supplier(
    request: Request,
    business_name: str = Form(...),
    rfc: str = Form(...),
    supplier_type: SupplierType = Form(...),
    email: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMIN)),
):
    await validate_csrf(request)
    try:
        data = SupplierCreate(business_name=business_name, rfc=rfc, supplier_type=supplier_type, email=email)
    except ValidationError as exc:
        return _suppliers_page(request, db, user, validation_message(exc), 400)
    if db.scalar(select(Supplier.id).where(Supplier.rfc == data.rfc)):
        return _suppliers_page(request, db, user, "Ya existe un proveedor con ese RFC.", 409)
    # Un correo corresponde a un solo proveedor y a su usuario (RD-06 de HU-01): HU-03 lo usa como usuario del portal.
    email_in_use = db.scalar(select(Supplier.id).where(func.lower(Supplier.email) == data.email)) or db.scalar(
        select(User.id).where(func.lower(User.email) == data.email)
    )
    if email_in_use:
        return _suppliers_page(request, db, user, MSG_EMAIL_IN_USE, 409)
    # Nace Registrado, como la carga masiva: el acceso al portal llega con la autorizacion (HU-02).
    supplier = Supplier(
        business_name=data.business_name,
        rfc=data.rfc,
        supplier_type=data.supplier_type,
        email=data.email,
        status=SupplierStatus.REGISTERED,
    )
    db.add(supplier)
    db.flush()
    audit(db, "SUPPLIER_CREATED", "Supplier", supplier.id, user.id)
    db.commit()
    return RedirectResponse(f"/suppliers/{supplier.id}", status_code=303)


# Las rutas /import se declaran antes de /{supplier_id}: de lo contrario "import" se tomaria como un id (422).
@router.get("/import")
def import_page(request: Request, user=Depends(require_roles(Role.ADMIN))):
    context = {"user": user, "max_rows": MAX_ROWS, "max_file_mb": MAX_FILE_MB}
    return templates.TemplateResponse(request, "suppliers/import.html", context)


@router.get("/import/template")
def import_template(user=Depends(require_roles(Role.ADMIN))):
    headers = {"Content-Disposition": f'attachment; filename="{TEMPLATE_FILENAME}"'}
    return Response(build_template(), media_type=XLSX_MEDIA_TYPE, headers=headers)


@router.post("/import")
async def import_suppliers(
    request: Request,
    upload: UploadFile | None = File(None),
    mode: str = Form(supplier_import_service.STRICT),
    expected_sha256: str | None = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMIN)),
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
    user=Depends(require_roles(Role.ADMIN)),
):
    """Autorizacion masiva (HU-02) y envio de credenciales (HU-03). La logica vive en supplier_access_service."""
    await validate_csrf(request)
    try:
        result = access.authorize(db, supplier_ids, user, portal_url(request))
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
):
    docs = list(db.scalars(select(Document).where(Document.supplier_id == supplier.id, Document.invoice_id.is_(None))))
    context = {
        "user": user,
        "supplier": supplier,
        "requirements": supplier_requirement_status(supplier, docs),
        "access_error": access_error,
        "credentials_result": credentials_result,
        "format_datetime": format_datetime,
    }
    if user.role == Role.ADMIN:
        portal_user = access.provider_user(db, supplier)
        context["access"] = {
            "user": portal_user,
            "delivery": access.credentials_status(db, supplier.id),
            "can_resend": access.can_resend(supplier, portal_user),
        }
    return templates.TemplateResponse(request, "suppliers/detail.html", context, status_code=status_code)


@router.get("/{supplier_id}")
def supplier_detail(
    supplier_id: int,
    request: Request,
    credentials: int | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if user.role == Role.PROVIDER and user.supplier_id != supplier_id:
        raise HTTPException(403, "Acceso denegado")
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(404, "Proveedor no encontrado")
    # El resultado del reenvio se lee de la bitacora y solo si es un envio de credenciales de este proveedor.
    result = db.get(EmailDelivery, credentials) if credentials and user.role == Role.ADMIN else None
    if result is not None and (result.event != access.CREDENTIALS or result.entity_id != str(supplier.id)):
        result = None
    return _supplier_detail_page(request, db, user, supplier, credentials_result=result)


@router.post("/{supplier_id}/credentials")
async def resend_credentials(
    supplier_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))
):
    await validate_csrf(request)
    try:
        delivery = access.resend_credentials(db, supplier_id, user, portal_url(request))
    except NotFoundError:
        raise
    except BusinessRuleError as exc:
        db.rollback()
        supplier = db.get(Supplier, supplier_id)
        return _supplier_detail_page(request, db, user, supplier, access_error=exc.message, status_code=exc.status_code)
    return RedirectResponse(f"/suppliers/{supplier_id}?credentials={delivery.id}", status_code=303)


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
    if user.role == Role.INTERNAL or (user.role == Role.PROVIDER and user.supplier_id != supplier_id):
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
