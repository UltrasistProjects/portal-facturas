import logging
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    DOCUMENT_REQUIREMENT_LABELS,
    CatalogType,
    ContractStatus,
    DocumentType,
    InvoiceStatus,
    NotificationEvent,
    ProcessingStatus,
    Role,
    RuleStatus,
    SupplierOrigin,
    SupplierStatus,
)
from app.core.database import get_db
from app.core.errors import BusinessRuleError, DuplicateInvoiceError, InvalidInputError
from app.core.security import get_current_user, require_roles, validate_csrf
from app.models import Contract, Document, Invoice, ValidationResult
from app.repositories.invoice_repository import get_visible_invoice, inbox_status, search_invoices, warning_counts
from app.routers.common import templates
from app.schemas import InvoiceCreate, validation_message
from app.services import cancellation_service as cancellation
from app.services import catalog_service, review_service
from app.services import document_requirements_service as requirements
from app.services import document_view_service as document_view
from app.services import foreign_invoice_service as foreign
from app.services import payment_service as payment
from app.services.audit_service import audit
from app.services.file_service import LocalFileStorage, log_upload, safe_download_name
from app.services.invoice_history_service import decision_cause, history
from app.services.invoice_service import (
    ensure_editable,
    internal_folio,
    is_editable,
    lock_invoice,
    provisional_folio,
    sync_upload_status,
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
provider_only = require_roles(Role.PROVEEDOR)
MSG_SUPPLIER_NOT_ACTIVE = "Su proveedor no está autorizado para registrar facturas"
MSG_USER_WITHOUT_SUPPLIER = "Su usuario no está vinculado a un proveedor. Contacte al Administrador"
# Avisos que llegan por ?notice= tras una redireccion; otro valor se ignora (como en el tablero).
NOTICES = {"submitted": "Factura enviada a validación"}
DOCUMENT_NOTICES = {
    "amounts_saved": "Datos del Invoice guardados",
    "amounts_unchanged": "Sin cambios",
    "complement_saved": "Complemento de Pago guardado",
}
MSG_CONFIRM_PAYMENT = "Confirme que la factura fue pagada"
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
    status: str | None = None,
    origin: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    # Sin `status`, el PMO y el Administrador abren la bandeja de "Enviadas" (HU-18); los enlaces lo llevan explicito.
    effective = inbox_status(user, status)
    result = search_invoices(db, user, q, effective, page, origin=origin)
    reviewer = user.role != Role.PROVEEDOR
    context = {
        "user": user,
        "invoices": result.items,
        "page": result,
        "base_query": urlencode({"q": q, "status": effective, "origin": origin}),
        "q": q,
        "selected_status": effective,
        "selected_origin": origin,
        "statuses": InvoiceStatus,
        "origins": SupplierOrigin,
        "warnings": warning_counts(db, [invoice.id for invoice in result.items]) if reviewer else {},
        "pending_complements": [] if reviewer else payment.pending_notice(db, user.supplier_id),
    }
    return templates.TemplateResponse(request, "invoices/list.html", context)


def _ensure_supplier_active(user) -> None:
    if user.supplier is None:
        raise BusinessRuleError(MSG_USER_WITHOUT_SUPPLIER)
    if user.supplier.status != SupplierStatus.ACTIVE:
        raise BusinessRuleError(MSG_SUPPLIER_NOT_ACTIVE)


def _new_invoice_page(
    request: Request,
    db: Session,
    user,
    error: str | None = None,
    status_code: int = 200,
    values: dict | None = None,
):
    """El proveedor de la factura es el del usuario y el formulario solo recibe sus contratos activos (DT-05): los
    de otros proveedores nunca llegan al navegador. El internacional captura ademas los datos del Invoice (HU-15)."""
    contracts = list(
        db.scalars(
            select(Contract)
            .where(Contract.supplier_id == user.supplier_id, Contract.status == ContractStatus.ACTIVE)
            .order_by(Contract.project_name)
        )
    )
    international = user.supplier.origin == SupplierOrigin.INTERNATIONAL
    defaults = {"currency": contracts[0].currency} if contracts else {}
    context = {
        "user": user,
        "supplier": user.supplier,
        "contracts": contracts,
        "error": error,
        "international": international,
        "currencies": catalog_service.active_entries(db, CatalogType.CURRENCY) if international else [],
        "values": {**defaults, **(values or {})},
    }
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
    invoice_date: str = Form(""),
    subtotal: str = Form(""),
    tax: str = Form(""),
    total: str = Form(""),
    currency: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(provider_only),
):
    await validate_csrf(request)
    _ensure_supplier_active(user)
    submitted = {
        "contract_id": str(contract_id),
        "invoice_number": invoice_number,
        "service_period": service_period,
        "project_name": project_name,
        "purchase_order_number": purchase_order_number,
        "project_leader": project_leader,
        "invoice_date": invoice_date,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "currency": currency,
    }
    try:
        data = InvoiceCreate(
            invoice_number=invoice_number,
            service_period=service_period,
            project_name=project_name,
            purchase_order_number=purchase_order_number or None,
            project_leader=project_leader or None,
        )
    except ValidationError as exc:
        return _new_invoice_page(request, db, user, validation_message(exc), 400, submitted)
    # Datos del Invoice (HU-15): solo del proveedor internacional; al nacional se los da el XML y se ignoran.
    foreign_data = None
    if user.supplier.origin == SupplierOrigin.INTERNATIONAL:
        foreign_data, errors = foreign.parse_data(db, submitted)
        if errors:
            return _new_invoice_page(request, db, user, " ".join(errors), 400, submitted)
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
    if foreign_data:
        foreign.apply_data(invoice, foreign_data)
    db.add(invoice)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if violates(exc, "uq_invoices_supplier_number"):
            message = "Ya existe una factura con ese numero para el proveedor"
            return _new_invoice_page(request, db, user, message, 409, submitted)
        raise
    invoice.internal_folio = internal_folio(invoice.id, invoice.created_at)
    audit(db, "INVOICE_CREATED", "Invoice", invoice.id, user.id, new={"folio": invoice.internal_folio})
    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}/documents", status_code=303)


def _status_delivery(db: Session, invoice: Invoice, notification: str, reviewer: bool):
    """Envio del correo cuyo resultado se muestra (id en la URL, solo si es de esta factura). El proveedor solo ve los
    avisos a Recepcion de Facturas que el origino (cancelacion y complemento de pago), y sin direcciones (HU-14)."""
    if not notification.isdigit():
        return None
    delivery = review_service.invoice_delivery(db, invoice, int(notification))
    if delivery and not reviewer and delivery.event not in PROVIDER_EVENTS:
        return None
    return delivery


PROVIDER_EVENTS = {NotificationEvent.INVOICE_CANCELLED, NotificationEvent.PAYMENT_COMPLEMENT}


def _detail_page(
    request: Request,
    db: Session,
    invoice,
    user,
    notice: str | None = None,
    submit_blocked=False,
    status_code=200,
    notification: str = "",
    cancel_error: str | None = None,
    payment_error: str | None = None,
):
    """Detalle de la factura. Tambien es la respuesta 409 de un envio que no procede (submit_blocked): muestra las
    reglas en FAIL que se acaban de guardar; la 400 de una cancelacion rechazada (cancel_error) y la del pago sin
    confirmar (payment_error)."""
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
    international = foreign.is_international(invoice)
    invoice_doc = foreign.current_invoice_document(invoice) if international else None
    reviewer = user.role != Role.PROVEEDOR
    cancelled = invoice.status == InvoiceStatus.CANCELLED
    paid = invoice.status == InvoiceStatus.PAID
    can_cancel = not reviewer and not cancelled and not paid
    ack_type = cancellation.acknowledgment_type(db) if can_cancel else None
    delivery = _status_delivery(db, invoice, notification, reviewer)
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
            "is_provider": user.role == Role.PROVEEDOR,
            "editable": editable,
            "can_submit": invoice.status in SUBMITTABLE_STATUSES,
            # Mientras la factura es editable, lo que impediria su envio (HU-13).
            "blocking": [v for v in validations if v.status == RuleStatus.FAIL] if editable else [],
            "notice": NOTICES.get(notice) if notice else None,
            "submit_blocked": submit_blocked,
            # Datos del Invoice (HU-15/16): la legibilidad del texto se tomo al cargarlo; no se relee el PDF aqui.
            "international": international,
            "has_invoice_doc": invoice_doc is not None,
            # Proveedor e historial para el PMO y el Administrador (HU-19); "Seguimiento" del proveedor, con la
            # decision atribuida a "PMO", y la causa vigente de un rechazo u observaciones (HU-17).
            "reviewer": reviewer,
            "history": history(db, invoice, for_provider=not reviewer),
            "decision_cause": decision_cause(db, invoice),
            # Decision del PMO (HU-20): panel, resultado del correo de la URL y reenvio si el ultimo envio fallo.
            "can_decide": reviewer and invoice.status == InvoiceStatus.UNDER_REVIEW,
            "can_resend": reviewer and review_service.can_resend(db, invoice),
            "delivery": delivery,
            "delivery_error": notification == "error" and (reviewer or cancelled),
            "max_observations": review_service.MAX_OBSERVATIONS,
            # Cancelacion (HU-14): seccion del proveedor con su error, y aviso de factura cancelada para todos.
            "cancelled": cancelled,
            "can_cancel": can_cancel,
            "cancel_error": cancel_error,
            "ack_type": ack_type,
            "ack_accept": ",".join(requirements.extensions(ack_type)) if ack_type else "",
            "ack_formats": requirements.formats_label(ack_type) if ack_type else "",
            # Pago y Complemento de Pago (HU Complemento de Pagos): panel del PMO en "Autorizada", aviso de factura
            # pagada, estado del complemento y enlace del proveedor para adjuntarlo.
            "can_pay": reviewer and invoice.status == InvoiceStatus.ACCEPTED,
            "paid": paid,
            "complement": payment.complement_status(invoice),
            "can_attach_complement": not reviewer and payment.is_pending(invoice),
            "payment_error": payment_error,
            "invoice_readable": (invoice_doc.metadata_json or {}).get("has_extractable_text") if invoice_doc else None,
        },
        status_code=status_code,
    )


@router.get("/{invoice_id}")
def invoice_detail(
    invoice_id: int,
    request: Request,
    notice: str = "",
    notification: str = "",
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return _detail_page(request, db, _invoice_or_404(db, invoice_id, user), user, notice, notification=notification)


def _documents_page(
    request: Request,
    db: Session,
    invoice,
    user,
    error: str | None = None,
    status_code: int = 200,
    notice: str | None = None,
    amounts: dict | None = None,
    amount_errors: list[str] | None = None,
    notification: str = "",
):
    """Carga documental con los tipos que aplican al origen del proveedor de la factura (HU-04) y, si es
    internacional, el formulario de los datos del Invoice (HU-15). En una factura "Pagada", solo el Complemento de
    Pago, su estado y el resultado del aviso a Recepcion de Facturas (HU Complemento de Pagos)."""
    international = foreign.is_international(invoice)
    paid = invoice.status == InvoiceStatus.PAID
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
        "notice": DOCUMENT_NOTICES.get(notice) if notice else None,
        "international": international,
        "amounts": amounts or (foreign.form_values(invoice) if international else {}),
        "amount_errors": amount_errors or [],
        "currencies": catalog_service.active_entries(db, CatalogType.CURRENCY) if international else [],
        "paid": paid,
        "complement": payment.complement_status(invoice),
        "delivery": _status_delivery(db, invoice, notification, reviewer=False) if paid else None,
        "delivery_error": paid and notification == "error",
    }
    return templates.TemplateResponse(request, "invoices/documents.html", context, status_code=status_code)


def _accepts_documents(invoice: Invoice) -> bool:
    """Editable, o "Pagada" con un Complemento de Pago requerido (lo carga aunque ya este adjuntado: reemplazo)."""
    return is_editable(invoice) or payment.complement_required(invoice)


@router.get("/{invoice_id}/documents")
def documents_page(
    invoice_id: int,
    request: Request,
    notice: str = "",
    notification: str = "",
    db: Session = Depends(get_db),
    user=Depends(provider_only),
):
    invoice = _invoice_or_404(db, invoice_id, user)
    if invoice.status == InvoiceStatus.PAID and not payment.complement_required(invoice):
        raise BusinessRuleError(payment.MSG_NOT_REQUIRED)
    if not _accepts_documents(invoice):
        return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)
    return _documents_page(request, db, invoice, user, notice=notice, notification=notification)


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
    if invoice.status == InvoiceStatus.PAID:
        # Una factura pagada solo recibe su Complemento de Pago (409 si no lo requiere o si es otro tipo).
        payment.ensure_paid_upload(invoice, document_type)
    else:
        ensure_editable(invoice)
    # Antes de leer o escribir el archivo: el tipo debe aplicar al origen del proveedor y admitir la extension; el XML
    # del Complemento de Pago debe ser un CFDI de tipo P que relacione la factura.
    complement_data = None
    try:
        requirements.ensure_format(requirements.offered_type(db, invoice, document_type), upload.filename)
        if document_type == DocumentType.PAYMENT_COMPLEMENT_XML.value:
            content = await upload.read(settings.max_upload_mb * 1024 * 1024 + 1)
            await upload.seek(0)
            complement_data = payment.check_complement_xml(invoice, content)
    except InvalidInputError as exc:
        return _documents_page(request, db, invoice, user, exc.message, 400)
    if document_type == DocumentType.FOREIGN_INVOICE.value:
        # HU-15: el nombre de archivo del Invoice no se repite entre las facturas del proveedor (bloqueo por proveedor).
        try:
            foreign.ensure_unique_filename(db, invoice, Path(upload.filename or "").name)
        except BusinessRuleError as exc:
            return _documents_page(request, db, invoice, user, exc.message, 409)
    try:
        stored = await LocalFileStorage().save_invoice_file(invoice.id, upload)
        metadata, pages, processing = {}, None, ProcessingStatus.PROCESSED
        if stored.path.suffix == ".pdf":
            pdf = analyze_pdf(stored.path)
            pages = pdf["page_count"]
            metadata = {k: v for k, v in pdf.items() if k != "text"}
            metadata["text_preview"] = pdf["text"][:2000]
        elif complement_data is not None:
            metadata = complement_data
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
    notify_reception = payment.register_complement(db, invoice, document, user.id)
    db.commit()
    if invoice.status != InvoiceStatus.PAID:
        return RedirectResponse(f"/invoices/{invoice.id}/documents", status_code=303)
    # Complemento en la factura pagada: despues del commit, el aviso a Recepcion de Facturas (solo por el XML).
    query = {"notice": "complement_saved"}
    if notify_reception:
        delivery = payment.notify_complement(db, invoice, document, user.id)
        query["notification"] = delivery.id if delivery else "error"
    return RedirectResponse(f"/invoices/{invoice.id}/documents?{urlencode(query)}", status_code=303)


@router.post("/{invoice_id}/amounts")
async def update_amounts(
    invoice_id: int,
    request: Request,
    invoice_date: str = Form(""),
    subtotal: str = Form(""),
    tax: str = Form(""),
    total: str = Form(""),
    currency: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(provider_only),
):
    """Edicion de los datos del Invoice mientras la factura es editable (HU-15)."""
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    lock_invoice(db, invoice)
    ensure_editable(invoice)
    if not foreign.is_international(invoice):
        raise InvalidInputError(foreign.MSG_NOT_INTERNATIONAL)
    values = {"invoice_date": invoice_date, "subtotal": subtotal, "tax": tax, "total": total, "currency": currency}
    data, errors = foreign.parse_data(db, values)
    if errors:
        return _documents_page(request, db, invoice, user, status_code=400, amounts=values, amount_errors=errors)
    old, new = foreign.apply_data(invoice, data)
    if not new:
        return RedirectResponse(f"/invoices/{invoice.id}/documents?notice=amounts_unchanged", status_code=303)
    audit(db, "INVOICE_AMOUNTS_UPDATED", "Invoice", invoice.id, user.id, old=old, new=new)
    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}/documents?notice=amounts_saved", status_code=303)


def _document_or_404(db: Session, invoice: Invoice, document_id: int) -> tuple[Document, Path]:
    """Documento de esa factura y su archivo: la autorizacion de la descarga, compartida por la visualizacion."""
    doc = db.get(Document, document_id)
    if not doc or doc.invoice_id != invoice.id:
        raise HTTPException(404, "Documento no encontrado")
    try:
        path = LocalFileStorage().resolve(doc.path)
    except FileNotFoundError:
        raise HTTPException(404, "Archivo no disponible") from None
    if not path.is_file():
        raise HTTPException(404, "Archivo no disponible")
    return doc, path


@router.get("/{invoice_id}/documents/{document_id}/download")
def download_document(invoice_id: int, document_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    doc, path = _document_or_404(db, _invoice_or_404(db, invoice_id, user), document_id)
    # Nunca el MIME almacenado: la descarga no debe interpretarse en el navegador (junto con nosniff).
    return FileResponse(path, filename=safe_download_name(doc.original_filename), media_type="application/octet-stream")


# Visualizacion en el portal (HU-19): paginas del PDF como PNG, imagenes y texto escapado (document_view_service).
VIEW_CACHE = {"Cache-Control": "private, max-age=300"}


@router.get("/{invoice_id}/documents/{document_id}/view")
def view_document(
    invoice_id: int, document_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    invoice = _invoice_or_404(db, invoice_id, user)
    doc, path = _document_or_404(db, invoice, document_id)
    view_kind = document_view.kind(doc.path)
    context = {
        "user": user,
        "invoice": invoice,
        "document": doc,
        "type_name": requirements.type_names(db).get(doc.document_type, doc.document_type),
        "kind": view_kind.value,
        "pages": [],
        "total_pages": None,
        "max_pages": document_view.MAX_PAGES,
        "text": None,
        "truncated": False,
        "text_limit": document_view.TEXT_LIMIT,
    }
    if view_kind == document_view.ViewKind.PDF:
        total = document_view.pdf_page_count(path)
        context["total_pages"] = total
        context["pages"] = list(range(1, min(total or 0, document_view.MAX_PAGES) + 1))
    elif view_kind == document_view.ViewKind.TEXT:
        context["text"], context["truncated"] = document_view.read_text(path)
    return templates.TemplateResponse(request, "invoices/document_view.html", context, headers=VIEW_CACHE)


@router.get("/{invoice_id}/documents/{document_id}/pages/{number}")
def document_page(
    invoice_id: int, document_id: int, number: int, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    doc, path = _document_or_404(db, _invoice_or_404(db, invoice_id, user), document_id)
    png = (
        document_view.render_page(path, number) if document_view.kind(doc.path) == document_view.ViewKind.PDF else None
    )
    if png is None:
        raise HTTPException(404, "Página no disponible")
    return Response(png, media_type="image/png", headers=VIEW_CACHE)


@router.get("/{invoice_id}/documents/{document_id}/image")
def document_image(invoice_id: int, document_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    doc, path = _document_or_404(db, _invoice_or_404(db, invoice_id, user), document_id)
    if document_view.kind(doc.path) != document_view.ViewKind.IMAGE:
        raise HTTPException(404, "El documento no es una imagen")
    return FileResponse(
        path,
        media_type=document_view.IMAGE_TYPES[path.suffix.lower()],
        filename=safe_download_name(doc.original_filename),
        content_disposition_type="inline",
        headers=VIEW_CACHE,
    )


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


reviewers_only = require_roles(Role.PMO, Role.ADMINISTRADOR)


@router.get("/{invoice_id}/review")
def review_page(invoice_id: int):
    """La decision vive en el panel del detalle (HU-20); la pagina aparte se retiro."""
    return RedirectResponse(f"/invoices/{invoice_id}#decision", status_code=303)


def _notification_redirect(invoice: Invoice, delivery) -> RedirectResponse:
    """Al detalle con el resultado del correo: el id del envio, o `error` si no pudo componerse."""
    result = delivery.id if delivery else "error"
    return RedirectResponse(f"/invoices/{invoice.id}?notification={result}#decision-result", status_code=303)


@router.post("/{invoice_id}/review")
async def review_action(
    invoice_id: int,
    request: Request,
    decision: str = Form(...),
    comments: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(reviewers_only),
):
    """Decision del PMO (HU-20): se confirma y despues sale el correo, que no la revierte si falla."""
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    review = review_service.decide(db, invoice, decision, comments, user.id)
    db.commit()
    return _notification_redirect(invoice, review_service.notify_decision(db, invoice, review))


@router.post("/{invoice_id}/payment")
async def mark_paid(
    invoice_id: int,
    request: Request,
    confirm: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(reviewers_only),
):
    """Marca como "Pagada" una factura "Autorizada" (HU Complemento de Pagos): se confirma y despues sale el correo al
    proveedor, con el aviso del Complemento de Pago si lo requiere; un envio fallido no revierte el pago."""
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    # Sin la confirmacion, una factura que se podria pagar vuelve al detalle con el error; las demas responden 409.
    if not confirm and invoice.status == InvoiceStatus.ACCEPTED:
        return _detail_page(request, db, invoice, user, payment_error=MSG_CONFIRM_PAYMENT, status_code=400)
    payment.mark_paid(db, invoice, user.id)
    db.commit()
    return _notification_redirect(invoice, review_service.send_notification(db, invoice, None, user.id))


@router.post("/{invoice_id}/notification")
async def resend_notification(
    invoice_id: int, request: Request, db: Session = Depends(get_db), user=Depends(reviewers_only)
):
    """Reenvio del correo de la decision cuando el ultimo envio fallo (HU-20, D5)."""
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    observations = review_service.prepare_resend(db, invoice, user.id)
    db.commit()
    return _notification_redirect(invoice, review_service.send_notification(db, invoice, observations, user.id))


@router.post("/{invoice_id}/cancel")
async def cancel_invoice(
    invoice_id: int,
    request: Request,
    confirm: str = Form(""),
    upload: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user=Depends(provider_only),
):
    """Cancelacion por el proveedor con su acuse (HU-14): se confirma y despues sale el correo a Recepcion de
    Facturas, que no la revierte si falla."""
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    filename = upload.filename if upload else None
    try:
        cancellation.check_request(db, invoice, bool(confirm), filename)
        await cancellation.cancel(db, invoice, upload, user.id)
    except InvalidInputError as exc:
        db.rollback()
        return _detail_page(request, db, invoice, user, cancel_error=exc.message, status_code=400)
    db.commit()
    delivery = review_service.send_notification(db, invoice, None, user.id)
    result = delivery.id if delivery else "error"
    return RedirectResponse(f"/invoices/{invoice.id}?notification={result}#cancellation-result", status_code=303)
