import logging
from decimal import Decimal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import ContractStatus, DocumentType, InvoiceStatus, ProcessingStatus, Role, SupplierStatus
from app.core.database import get_db
from app.core.errors import DuplicateInvoiceError
from app.core.security import get_current_user, require_roles, validate_csrf
from app.models import Contract, Document, Invoice, Supplier, ValidationResult
from app.repositories.invoice_repository import get_visible_invoice, search_invoices
from app.routers.common import templates
from app.schemas import InvoiceCreate, validation_message
from app.services.audit_service import audit
from app.services.file_service import LocalFileStorage, log_upload, safe_download_name
from app.services.invoice_service import (
    ensure_editable,
    ensure_prevalidatable,
    internal_folio,
    is_editable,
    next_clickbalance_status,
    provisional_folio,
    review_invoice,
    transition_invoice,
    validation_summary,
    violates,
)
from app.services.pdf_service import analyze_pdf
from app.services.reconciliation_service import reconcile_amount
from app.services.validation_engine import run_validation
from app.services.xml_service import XMLParseError, parse_cfdi

router = APIRouter(prefix="/invoices")
logger = logging.getLogger(__name__)


def _invoice_or_404(db: Session, invoice_id: int, user):
    invoice = get_visible_invoice(db, invoice_id, user)
    if not invoice:
        raise HTTPException(404, "Factura no encontrada")
    return invoice


@router.get("")
def invoice_list(
    request: Request,
    q: str = "",
    status: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    result = search_invoices(db, user, q, status, page)
    context = {
        "user": user,
        "invoices": result.items,
        "page": result,
        "base_query": urlencode({"q": q, "status": status}),
        "q": q,
        "selected_status": status,
        "statuses": InvoiceStatus,
    }
    return templates.TemplateResponse(request, "invoices/list.html", context)


def _new_invoice_page(request: Request, db: Session, user, error: str | None = None, status_code: int = 200):
    if user.role == Role.PROVIDER:
        suppliers = [user.supplier]
    else:
        suppliers = list(
            db.scalars(
                select(Supplier).where(Supplier.status == SupplierStatus.ACTIVE).order_by(Supplier.business_name)
            )
        )
    contracts = list(db.scalars(select(Contract).where(Contract.status == ContractStatus.ACTIVE)))
    context = {"user": user, "suppliers": suppliers, "contracts": contracts, "error": error}
    return templates.TemplateResponse(request, "invoices/new.html", context, status_code=status_code)


@router.get("/new")
def new_invoice(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _new_invoice_page(request, db, user)


@router.post("/new")
async def create_invoice(
    request: Request,
    supplier_id: int = Form(...),
    contract_id: int = Form(...),
    invoice_number: str = Form(...),
    service_period: str = Form(...),
    project_name: str = Form(...),
    purchase_order_number: str = Form(""),
    project_leader: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    await validate_csrf(request)
    try:
        data = InvoiceCreate(
            invoice_number=invoice_number,
            service_period=service_period,
            project_name=project_name,
            purchase_order_number=purchase_order_number or None,
            project_leader=project_leader or None,
        )
    except ValidationError as exc:
        return _new_invoice_page(request, db, user, validation_message(exc), 400)
    if user.role == Role.PROVIDER and supplier_id != user.supplier_id:
        raise HTTPException(403, "No puede crear facturas para otro proveedor")
    contract = db.get(Contract, contract_id)
    if not contract or contract.supplier_id != supplier_id:
        raise HTTPException(400, "Contrato no corresponde al proveedor")
    invoice = Invoice(
        internal_folio=provisional_folio(),
        supplier_id=supplier_id,
        uploaded_by=user.id,
        contract_id=contract_id,
        invoice_number=data.invoice_number,
        service_period=data.service_period,
        project_name=data.project_name,
        purchase_order_number=data.purchase_order_number or None,
        project_leader=data.project_leader or contract.project_leader,
        subtotal=Decimal("0"),
        tax=Decimal("0"),
        total=Decimal("0"),
    )
    db.add(invoice)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if violates(exc, "uq_invoices_supplier_number"):
            message = "Ya existe una factura con ese numero para el proveedor"
            return _new_invoice_page(request, db, user, message, 409)
        raise
    invoice.internal_folio = internal_folio(invoice.id, invoice.created_at)
    audit(db, "INVOICE_CREATED", "Invoice", invoice.id, user.id, new={"folio": invoice.internal_folio})
    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}/documents", status_code=303)


@router.get("/{invoice_id}")
def invoice_detail(invoice_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    invoice = _invoice_or_404(db, invoice_id, user)
    validations = list(
        db.scalars(
            select(ValidationResult)
            .where(ValidationResult.invoice_id == invoice.id)
            .order_by(ValidationResult.category, ValidationResult.rule_code)
        )
    )
    xml_doc = next(
        (d for d in invoice.documents if d.is_current and d.document_type == DocumentType.INVOICE_XML.value), None
    )
    xml_data = xml_doc.metadata_json if xml_doc else None
    rec = (
        reconcile_amount(Decimal(invoice.contract.authorized_amount), Decimal(invoice.subtotal))
        if invoice.contract
        else None
    )
    summary = validation_summary(validations)
    return templates.TemplateResponse(
        request,
        "invoices/detail.html",
        {
            "user": user,
            "invoice": invoice,
            "validations": validations,
            "xml": xml_data,
            "reconciliation": rec,
            "summary": summary,
        },
    )


@router.get("/{invoice_id}/documents")
def documents_page(invoice_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    invoice = _invoice_or_404(db, invoice_id, user)
    if user.role == Role.PROVIDER and not is_editable(invoice):
        return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)
    return templates.TemplateResponse(
        request, "invoices/documents.html", {"user": user, "invoice": invoice, "document_types": DocumentType}
    )


@router.post("/{invoice_id}/documents")
async def upload_document(
    invoice_id: int,
    request: Request,
    document_type: str = Form(...),
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    ensure_editable(invoice)
    if document_type not in {x.value for x in DocumentType}:
        raise HTTPException(400, "Tipo documental invalido")
    try:
        stored = await LocalFileStorage().save_invoice_file(invoice.id, upload)
        metadata, pages, processing = {}, None, ProcessingStatus.PROCESSED
        if stored.path.suffix == ".pdf":
            pdf = analyze_pdf(stored.path)
            pages = pdf["page_count"]
            metadata = {k: v for k, v in pdf.items() if k != "text"}
            metadata["text_preview"] = pdf["text"][:2000]
        elif stored.path.suffix == ".xml":
            from app.services.validation_engine import _json_safe

            metadata = _json_safe(parse_cfdi(stored.path))
    except (ValueError, XMLParseError) as exc:
        if isinstance(exc, XMLParseError):
            logger.warning(
                "xml.parse_failed",
                extra={
                    "event": "xml.parse_failed",
                    "invoice_id": invoice.id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        return templates.TemplateResponse(
            request,
            "invoices/documents.html",
            {"user": user, "invoice": invoice, "document_types": DocumentType, "error": str(exc)},
            status_code=400,
        )
    previous = next((d for d in invoice.documents if d.is_current and d.document_type == document_type), None)
    if previous:
        previous.is_current = False
    document = Document(
        invoice_id=invoice.id,
        supplier_id=invoice.supplier_id,
        document_type=document_type,
        original_filename=stored.original_filename,
        stored_filename=stored.stored_filename,
        path=stored.relative_path,
        mime_type=stored.mime_type,
        file_size=stored.file_size,
        sha256=stored.sha256,
        uploaded_by=user.id,
        processing_status=processing,
        page_count=pages,
        metadata_json=metadata,
        replaced_document_id=previous.id if previous else None,
    )
    db.add(document)
    db.flush()
    log_upload(document_type, stored, invoice_id=invoice.id)
    audit(
        db,
        "DOCUMENT_REPLACED" if previous else "DOCUMENT_UPLOADED",
        "Document",
        document.id,
        user.id,
        old={"document_id": previous.id} if previous else None,
        new={"type": document_type, "sha256": stored.sha256},
    )
    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}/documents", status_code=303)


@router.get("/{invoice_id}/documents/{document_id}/download")
def download_document(invoice_id: int, document_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    invoice = _invoice_or_404(db, invoice_id, user)
    doc = db.get(Document, document_id)
    if not doc or doc.invoice_id != invoice.id:
        raise HTTPException(404, "Documento no encontrado")
    try:
        path = LocalFileStorage().resolve(doc.path)
    except FileNotFoundError:
        raise HTTPException(404, "Archivo no disponible") from None
    if not path.is_file():
        raise HTTPException(404, "Archivo no disponible")
    # Nunca el MIME almacenado: la descarga no debe interpretarse en el navegador (junto con nosniff).
    return FileResponse(path, filename=safe_download_name(doc.original_filename), media_type="application/octet-stream")


@router.post("/{invoice_id}/validation")
async def validate_invoice(
    invoice_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    ensure_prevalidatable(invoice)
    run_validation(db, invoice, user.id)
    try:
        db.commit()
    except IntegrityError as exc:
        # Carrera: otra validacion asigno el mismo UUID despues de la comprobacion previa. Nada se persiste.
        db.rollback()
        if violates(exc, "uq_invoices_uuid"):
            raise DuplicateInvoiceError("El CFDI ya esta registrado en otra factura") from exc
        raise
    return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)


@router.get("/{invoice_id}/validation")
def validation_alias(invoice_id: int):
    return RedirectResponse(f"/invoices/{invoice_id}#validations", status_code=303)


@router.post("/{invoice_id}/submit")
async def submit(invoice_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    transition_invoice(db, invoice, InvoiceStatus.UNDER_REVIEW, user.id)
    audit(db, "INVOICE_SUBMITTED", "Invoice", invoice.id, user.id)
    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)


@router.get("/{invoice_id}/review")
def review_page(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.INTERNAL, Role.ADMIN)),
):
    invoice = _invoice_or_404(db, invoice_id, user)
    return templates.TemplateResponse(request, "invoices/review.html", {"user": user, "invoice": invoice})


@router.post("/{invoice_id}/review")
async def review_action(
    invoice_id: int,
    request: Request,
    decision: str = Form(...),
    comments: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.INTERNAL, Role.ADMIN)),
):
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    review_invoice(db, invoice, decision, comments, user.id)
    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)


@router.post("/{invoice_id}/clickbalance")
async def clickbalance(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.INTERNAL, Role.ADMIN)),
):
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    transition_invoice(db, invoice, next_clickbalance_status(invoice), user.id)
    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)
