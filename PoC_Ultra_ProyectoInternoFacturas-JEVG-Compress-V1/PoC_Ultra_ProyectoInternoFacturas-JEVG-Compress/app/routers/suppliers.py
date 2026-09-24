from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import Role, SupplierType
from app.core.database import get_db
from app.core.security import get_current_user, require_roles, validate_csrf
from app.models import Document, Supplier
from app.routers.common import templates
from app.services.audit_service import audit
from app.services.file_service import LocalFileStorage
from app.services.supplier_service import supplier_requirement_status

router = APIRouter(prefix="/suppliers")


@router.get("")
def list_suppliers(
    request: Request, db: Session = Depends(get_db), user=Depends(require_roles(Role.INTERNAL, Role.ADMIN))
):
    suppliers = list(db.scalars(select(Supplier).order_by(Supplier.business_name)))
    return templates.TemplateResponse(request, "suppliers/list.html", {"user": user, "suppliers": suppliers})


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
    supplier = Supplier(
        business_name=business_name.strip(),
        rfc=rfc.upper().strip(),
        supplier_type=supplier_type,
        email=email.lower().strip(),
    )
    db.add(supplier)
    db.flush()
    audit(db, "SUPPLIER_CREATED", "Supplier", supplier.id, user.id)
    db.commit()
    return RedirectResponse(f"/suppliers/{supplier.id}", status_code=303)


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
        path=str(stored.path),
        mime_type=stored.mime_type,
        file_size=stored.file_size,
        sha256=stored.sha256,
        uploaded_by=user.id,
        processing_status="PROCESSED",
        document_date=document_date,
        metadata_json={"scope": "supplier"},
        replaced_document_id=previous.id if previous else None,
    )
    db.add(document)
    db.flush()
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
