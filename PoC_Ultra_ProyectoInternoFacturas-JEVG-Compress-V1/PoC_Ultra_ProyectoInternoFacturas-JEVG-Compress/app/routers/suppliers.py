from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import ProcessingStatus, Role, SupplierType
from app.core.database import get_db
from app.core.security import get_current_user, require_roles, validate_csrf
from app.models import Document, Supplier
from app.routers.common import templates
from app.schemas import SupplierCreate, validation_message
from app.services import supplier_import_service
from app.services.audit_service import audit
from app.services.file_service import LocalFileStorage, log_upload
from app.services.supplier_service import supplier_requirement_status
from app.services.supplier_template import MAX_FILE_MB, MAX_ROWS, TEMPLATE_FILENAME, XLSX_MEDIA_TYPE, build_template

router = APIRouter(prefix="/suppliers")


@router.get("")
def list_suppliers(
    request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.INTERNAL, Role.ADMIN))
):
    return _suppliers_page(request, db, user)


def _suppliers_page(request: Request, db: Session, user, error: str | None = None, status_code: int = 200):
    suppliers = list(db.scalars(select(Supplier).order_by(Supplier.business_name)))
    context = {"user": user, "suppliers": suppliers, "error": error}
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
    supplier = Supplier(
        business_name=data.business_name, rfc=data.rfc, supplier_type=data.supplier_type, email=data.email
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


@router.get("/{supplier_id}")
def supplier_detail(supplier_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role == Role.PROVIDER and user.supplier_id != supplier_id:
        raise HTTPException(403, "Acceso denegado")
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(404, "Proveedor no encontrado")
    docs = list(db.scalars(select(Document).where(Document.supplier_id == supplier.id, Document.invoice_id.is_(None))))
    requirements = supplier_requirement_status(supplier, docs)
    return templates.TemplateResponse(
        request, "suppliers/detail.html", {"user": user, "supplier": supplier, "requirements": requirements}
    )


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
