import logging
from decimal import Decimal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import (
    DOCUMENT_REQUIREMENT_LABELS,
    ContractStatus,
    DocumentType,
    InvoiceStatus,
    ProcessingStatus,
    Role,
    RuleStatus,
    SupplierStatus,
)
from app.core.database import get_db
from app.core.errors import BusinessRuleError, DuplicateInvoiceError, InvalidInputError
from app.core.security import get_current_user, require_roles, validate_csrf
from app.models import Contract, Document, Invoice, ValidationResult
from app.repositories.invoice_repository import get_visible_invoice, search_invoices
from app.routers.common import templates
from app.schemas import InvoiceCreate, validation_message
from app.services import document_requirements_service as requirements
from app.services.audit_service import audit
from app.services.file_service import LocalFileStorage, log_upload, safe_download_name
from app.services.invoice_service import (
    ensure_editable,
    internal_folio,
    is_editable,
    lock_invoice,
    next_clickbalance_status,
    provisional_folio,
    review_invoice,
    sync_upload_status,
    transition_invoice,
    validation_summary,
    violates,
)
from app.services.pdf_service import analyze_pdf
from app.services.reconciliation_service import reconcile_amount
from app.services.submission_service import MSG_MISSING_REQUIRED, SubmissionOutcome, submit_invoice
from app.services.validation_engine import run_validation
from app.services.xml_service import XMLParseError, parse_cfdi

router = APIRouter(prefix="/invoices")
logger = logging.getLogger(__name__)
# Registro, carga documental, verificacion y envio: solo el proveedor (EP-01 DT-04). El PMO y el Administrador
# conservan el listado, el detalle y las descargas.
provider_only = require_roles(Role.PROVIDER)
MSG_SUPPLIER_NOT_ACTIVE = "Su proveedor no está autorizado para registrar facturas"
# Avisos que llegan por ?notice= tras una redireccion; otro valor se ignora (como en el tablero).
NOTICES = {"submitted": "Factura enviada a validación"}
SUBMITTABLE_STATUSES = frozenset({InvoiceStatus.UPLOADED, InvoiceStatus.REQUIRES_CORRECTION})


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


def _ensure_supplier_active(user) -> None:
    if user.supplier is None or user.supplier.status != SupplierStatus.ACTIVE:
        raise BusinessRuleError(MSG_SUPPLIER_NOT_ACTIVE)


def _new_invoice_page(request: Request, db: Session, user, error: str | None = None, status_code: int = 200):
    """El proveedor de la factura es el del usuario y el formulario solo recibe sus contratos activos (DT-05): los
    de otros proveedores nunca llegan al navegador."""
    contracts = list(
        db.scalars(
            select(Contract)
            .where(Contract.supplier_id == user.supplier_id, Contract.status == ContractStatus.ACTIVE)
            .order_by(Contract.project_name)
        )
    )
    context = {"user": user, "supplier": user.supplier, "contracts": contracts, "error": error}
    return templates.TemplateResponse(request, "invoices/new.html", context, status_code=status_code)


@router.get("/new")
def new_invoice(request: Request, db: Session = Depends(get_db), user=Depends(provider_only)):
    _ensure_supplier_active(user)
    return _new_invoice_page(request, db, user)


@router.post("/new")
async def create_invoice(
    request: Request,
    contract_id: int = Form(...),
    invoice_number: str = Form(...),
    service_period: str = Form(...),
    project_name: str = Form(...),
    purchase_order_number: str = Form(""),
    project_leader: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(provider_only),
):
    await validate_csrf(request)
    _ensure_supplier_active(user)
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
    # Un supplier_id recibido en el formulario se ignora: la factura es del proveedor del usuario.
    supplier_id = user.supplier_id
    contract = db.get(Contract, contract_id)
    if not contract or contract.supplier_id != supplier_id:
        raise HTTPException(400, "Contrato no corresponde al proveedor")
    if contract.status != ContractStatus.ACTIVE:
        raise HTTPException(400, "El contrato no está activo")
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


def _detail_page(
    request: Request, db: Session, invoice, user, notice: str | None = None, submit_blocked=False, status_code=200
):
    """Detalle de la factura. Tambien es la respuesta 409 de un envio que no procede (submit_blocked): muestra las
    reglas en FAIL que se acaban de guardar."""
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
    editable = is_editable(invoice)
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
            # Nombre del catalogo de cada documento, tambien de tipos inactivos o que ya no aplican (RD-10).
            "type_names": requirements.type_names(db),
            "is_provider": user.role == Role.PROVIDER,
            "editable": editable,
            "can_submit": invoice.status in SUBMITTABLE_STATUSES,
            # Mientras la factura es editable, lo que impediria su envio (HU-13).
            "blocking": [v for v in validations if v.status == RuleStatus.FAIL] if editable else [],
            "notice": NOTICES.get(notice) if notice else None,
            "submit_blocked": submit_blocked,
        },
        status_code=status_code,
    )


@router.get("/{invoice_id}")
def invoice_detail(
    invoice_id: int, request: Request, notice: str = "", db: Session = Depends(get_db), user=Depends(get_current_user)
):
    return _detail_page(request, db, _invoice_or_404(db, invoice_id, user), user, notice)


def _documents_page(request: Request, db: Session, invoice, user, error: str | None = None, status_code: int = 200):
    """Carga documental con los tipos que aplican al origen del proveedor de la factura (HU-04)."""
    items = requirements.checklist(db, invoice)
    pending = requirements.pending_required(items)
    context = {
        "user": user,
        "invoice": invoice,
        "items": items,
        "complete": pending == 0,
        "can_submit": invoice.status in SUBMITTABLE_STATUSES,
        "pending_label": requirements.pending_label(pending),
        "requirement_labels": DOCUMENT_REQUIREMENT_LABELS,
        "formats_label": requirements.formats_label,
        "accept": ",".join(dict.fromkeys(ext for item in items for ext in requirements.extensions(item.document_type))),
        "error": error,
    }
    return templates.TemplateResponse(request, "invoices/documents.html", context, status_code=status_code)


@router.get("/{invoice_id}/documents")
def documents_page(invoice_id: int, request: Request, db: Session = Depends(get_db), user=Depends(provider_only)):
    invoice = _invoice_or_404(db, invoice_id, user)
    if not is_editable(invoice):
        return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)
    return _documents_page(request, db, invoice, user)


@router.post("/{invoice_id}/documents")
async def upload_document(
    invoice_id: int,
    request: Request,
    document_type: str = Form(...),
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(provider_only),
):
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    lock_invoice(db, invoice)
    ensure_editable(invoice)
    # Antes de leer o escribir el archivo: el tipo debe aplicar al origen del proveedor y admitir la extension.
    try:
        requirements.ensure_format(requirements.offered_type(db, invoice, document_type), upload.filename)
    except InvalidInputError as exc:
        return _documents_page(request, db, invoice, user, exc.message, 400)
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
        return _documents_page(request, db, invoice, user, str(exc), 400)
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
    # El documento se creo por llave foranea: la coleccion cargada aun no lo incluye.
    db.expire(invoice, ["documents"])
    complete = requirements.pending_required(requirements.checklist(db, invoice)) == 0
    sync_upload_status(db, invoice, complete, user.id)
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


def _commit_validation(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        # Carrera: otra validacion asigno el mismo UUID despues de la comprobacion previa. Nada se persiste.
        db.rollback()
        if violates(exc, "uq_invoices_uuid"):
            raise DuplicateInvoiceError("El CFDI ya esta registrado en otra factura") from exc
        raise


@router.post("/{invoice_id}/validation")
async def validate_invoice(
    invoice_id: int, request: Request, db: Session = Depends(get_db), user=Depends(provider_only)
):
    """ "Verificar": guarda los resultados del motor sin cambiar el estatus, para corregir antes de enviar."""
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    lock_invoice(db, invoice)
    ensure_editable(invoice)
    run_validation(db, invoice, user.id)
    _commit_validation(db)
    return RedirectResponse(f"/invoices/{invoice.id}#validations", status_code=303)


@router.get("/{invoice_id}/validation")
def validation_alias(invoice_id: int):
    return RedirectResponse(f"/invoices/{invoice_id}#validations", status_code=303)


@router.post("/{invoice_id}/submit")
async def submit(invoice_id: int, request: Request, db: Session = Depends(get_db), user=Depends(provider_only)):
    """Envio a validacion (HU-13): se confirma tambien cuando no procede, para conservar los resultados y el
    recalculo de "Borrador"/"Cargada" que lo explican."""
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    result = submit_invoice(db, invoice, user.id)
    _commit_validation(db)
    if result.outcome == SubmissionOutcome.SUBMITTED:
        return RedirectResponse(f"/invoices/{invoice.id}?notice=submitted", status_code=303)
    if result.outcome == SubmissionOutcome.MISSING_REQUIRED:
        raise BusinessRuleError(MSG_MISSING_REQUIRED)
    return _detail_page(request, db, invoice, user, submit_blocked=True, status_code=409)


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
