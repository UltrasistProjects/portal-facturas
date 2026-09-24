from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import DocumentType, InvoiceStatus, Role
from app.core.database import get_db
from app.core.security import get_current_user, require_roles, validate_csrf
from app.models import Contract, Document, Invoice, Review, Supplier, ValidationResult
from app.repositories.invoice_repository import get_visible_invoice, visible_invoices
from app.routers.common import templates
from app.schemas import InvoiceCreate, validation_message
from app.services.audit_service import audit
from app.services.file_service import LocalFileStorage, safe_download_name
from app.services.invoice_service import transition_invoice
from app.services.pdf_service import analyze_pdf
from app.services.reconciliation_service import reconcile_amount
from app.services.validation_engine import run_validation
from app.services.xml_service import XMLParseError, parse_cfdi

router = APIRouter(prefix="/invoices")


def _invoice_or_404(db: Session, invoice_id: int, user):
    invoice = get_visible_invoice(db, invoice_id, user)
    if not invoice:
        raise HTTPException(404, "Factura no encontrada")
    return invoice


@router.get("")
def invoice_list(
    request: Request, q: str = "", status: str = "", db: Session = Depends(get_db), user=Depends(get_current_user)
):
    rows = visible_invoices(db, user)
    if q:
        rows = [
            i
            for i in rows
            if q.lower() in f"{i.internal_folio} {i.invoice_number} {i.project_name} {i.supplier.business_name}".lower()
        ]
    if status:
        rows = [i for i in rows if i.status.value == status]
    return templates.TemplateResponse(
        request,
        "invoices/list.html",
        {"user": user, "invoices": rows, "q": q, "selected_status": status, "statuses": InvoiceStatus},
    )


def _new_invoice_page(request: Request, db: Session, user, error: str | None = None, status_code: int = 200):
    if user.role == Role.PROVIDER:
        suppliers = [user.supplier]
    else:
        suppliers = list(
            db.scalars(select(Supplier).where(Supplier.status == "ACTIVE").order_by(Supplier.business_name))
        )
    contracts = list(db.scalars(select(Contract).where(Contract.status == "ACTIVE")))
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
    count = db.scalar(select(Invoice.id).order_by(Invoice.id.desc()).limit(1)) or 0
    invoice = Invoice(
        internal_folio=f"FAC-{datetime.now().year}-{count + 1:05d}",
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
    db.flush()
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
    summary = {
        "pass": sum(v.status == "PASS" for v in validations),
        "warnings": sum(v.status == "WARNING" for v in validations),
        "errors": sum(v.status == "FAIL" for v in validations),
        "blockers": sum(v.status == "FAIL" and v.severity == "CRITICAL" for v in validations),
    }
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
    if user.role == Role.PROVIDER and invoice.status not in {
        InvoiceStatus.DRAFT,
        InvoiceStatus.REQUIRES_CORRECTION,
        InvoiceStatus.VALIDATION_FAILED,
    }:
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
    if invoice.status not in {InvoiceStatus.DRAFT, InvoiceStatus.REQUIRES_CORRECTION, InvoiceStatus.VALIDATION_FAILED}:
        raise HTTPException(409, "El expediente no admite cambios en su estado actual")
    if document_type not in {x.value for x in DocumentType}:
        raise HTTPException(400, "Tipo documental invalido")
    try:
        stored = await LocalFileStorage().save_invoice_file(invoice.id, upload)
        metadata, pages, processing = {}, None, "PROCESSED"
        if stored.path.suffix == ".pdf":
            pdf = analyze_pdf(stored.path)
            pages = pdf["page_count"]
            metadata = {k: v for k, v in pdf.items() if k != "text"}
            metadata["text_preview"] = pdf["text"][:2000]
        elif stored.path.suffix == ".xml":
            from app.services.validation_engine import _json_safe

            metadata = _json_safe(parse_cfdi(stored.path))
    except (ValueError, XMLParseError) as exc:
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
        path=str(stored.path),
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
    path = Path(doc.path)
    if not path.is_file():
        raise HTTPException(404, "Archivo no disponible")
    return FileResponse(path, filename=safe_download_name(doc.original_filename), media_type=doc.mime_type)


@router.post("/{invoice_id}/validation")
async def validate_invoice(
    invoice_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    if invoice.status not in {
        InvoiceStatus.DRAFT,
        InvoiceStatus.UPLOADED,
        InvoiceStatus.REQUIRES_CORRECTION,
        InvoiceStatus.VALIDATION_FAILED,
    }:
        raise HTTPException(409, "La factura no puede prevalidarse en este estado")
    run_validation(db, invoice, user.id)
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
    if decision == "COMMENT":
        db.add(Review(invoice_id=invoice.id, reviewer_id=user.id, decision="COMMENT", comments=comments))
        audit(db, "COMMENT_ADDED", "Invoice", invoice.id, user.id, new={"comments": comments})
        db.commit()
        return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)
    targets = {
        "ACCEPTED": InvoiceStatus.ACCEPTED,
        "REJECTED": InvoiceStatus.REJECTED,
        "REQUIRES_CORRECTION": InvoiceStatus.REQUIRES_CORRECTION,
    }
    if decision not in targets:
        raise HTTPException(400, "Decision invalida")
    blockers = any(v.status == "FAIL" and v.severity == "CRITICAL" for v in invoice.validations)
    if decision == "ACCEPTED" and blockers:
        raise HTTPException(409, "No se puede aceptar con bloqueos criticos")
    transition_invoice(db, invoice, targets[decision], user.id)
    invoice.comments = comments
    db.add(Review(invoice_id=invoice.id, reviewer_id=user.id, decision=decision, comments=comments))
    audit(db, decision, "Invoice", invoice.id, user.id, new={"comments": comments})
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
    target = (
        InvoiceStatus.READY_FOR_CLICKBALANCE
        if invoice.status == InvoiceStatus.ACCEPTED
        else InvoiceStatus.UPLOADED_TO_CLICKBALANCE
    )
    transition_invoice(db, invoice, target, user.id)
    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)
