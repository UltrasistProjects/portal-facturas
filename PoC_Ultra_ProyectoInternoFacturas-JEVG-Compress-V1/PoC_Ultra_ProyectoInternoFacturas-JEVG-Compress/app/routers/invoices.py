import logging
import re
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    DOCUMENT_REQUIREMENT_LABELS,
    PURCHASE_ORDER_ITEM_LABELS,
    CatalogType,
    DocumentType,
    InvoiceStatus,
    NotificationEvent,
    ProcessingStatus,
    Role,
    RuleStatus,
    SupplierOrigin,
    SupplierStatus,
)
from app.core.database import get_db, violates
from app.core.errors import BusinessRuleError, DuplicateInvoiceError, InvalidInputError
from app.core.security import get_current_user, require_roles, validate_csrf
from app.core.types import to_money
from app.models import Document, Invoice, ValidationResult
from app.repositories.invoice_repository import get_visible_invoice, inbox_status, search_invoices, warning_counts
from app.routers.common import templates
from app.rules.purchase_order_rules import detect_order_number, order_items
from app.services import cancellation_service as cancellation
from app.services import catalog_service, review_service
from app.services import document_requirements_service as requirements
from app.services import document_view_service as document_view
from app.services import foreign_invoice_service as foreign
from app.services import invoice_deletion_service as deletion
from app.services import invoice_extraction_service as extraction
from app.services import invoice_report_service as report
from app.services import payment_service as payment
from app.services.audit_service import audit
from app.services.file_service import LocalFileStorage, check_upload, log_upload, read_upload, safe_download_name
from app.services.invoice_history_service import decision_cause, history
from app.services.invoice_service import (
    ensure_editable,
    internal_folio,
    is_editable,
    lock_invoice,
    provisional_folio,
    sync_upload_status,
    validation_summary,
)
from app.services.pdf_service import analyze_pdf
from app.services.submission_service import SubmissionOutcome, submit_invoice
from app.services.validation_engine import identity_checks, run_validation, uuid_owner
from app.services.xml_service import XMLParseError, parse_cfdi

router = APIRouter(prefix="/invoices")
logger = logging.getLogger(__name__)
# Registro, carga documental, verificacion y envio: solo el proveedor (EP-01 DT-04). El PMO y el Administrador
# conservan el listado, el detalle y las descargas.
provider_only = require_roles(Role.PROVEEDOR)
# Eliminacion de una factura en Borrador o Cancelada: el Administrador o el proveedor duenio; el PMO no.
admin_or_provider = require_roles(Role.ADMINISTRADOR, Role.PROVEEDOR)
MSG_SUPPLIER_NOT_ACTIVE = "Su proveedor no está autorizado para registrar facturas"
MSG_USER_WITHOUT_SUPPLIER = "Su usuario no está vinculado a un proveedor. Contacte al Administrador"
MSG_DUPLICATE_NUMBER = "Ya existe una factura con ese número para el proveedor"
# Avisos que llegan por ?notice= tras una redireccion; otro valor se ignora (como en el tablero).
NOTICES = {"submitted": "Factura enviada a validación"}
DOCUMENT_NOTICES = {
    "amounts_saved": "Datos del Invoice guardados",
    "amounts_unchanged": "Sin cambios",
    "complement_saved": "Complemento de Pago guardado",
}
MSG_CONFIRM_PAYMENT = "Confirme la programación del pago"
SUBMITTABLE_STATUSES = frozenset({InvoiceStatus.UPLOADED, InvoiceStatus.REQUIRES_CORRECTION})
# Folio de la factura eliminada que el listado anuncia (?deleted=); otro valor se ignora.
DELETED_FOLIO = re.compile(r"FAC-\d{4}-\d{5,}")


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
    deleted: str = "",
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
        "notice": f"Factura {deleted} eliminada" if DELETED_FOLIO.fullmatch(deleted) else None,
    }
    return templates.TemplateResponse(request, "invoices/list.html", context)


@router.get("/report.pdf")
def invoice_report(
    q: str = "",
    status: str | None = None,
    origin: str = "",
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Reporte resumen en PDF (Ferromex): totales por estatus y origen con grafico de pie, con los filtros y el alcance
    del listado. Se declara antes de /{invoice_id} para que "report.pdf" no se lea como id."""
    data = report.summary(db, user, q.strip(), inbox_status(user, status), origin)
    headers = {"Content-Disposition": f'attachment; filename="{report.filename(data)}"'}
    return Response(report.render(data), media_type="application/pdf", headers=headers)


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
    """Paso 1 del registro. El nacional carga el PDF (obligatorio) y el XML (opcional) de su factura (HU-24); el
    internacional captura los datos del Invoice y su orden de compra (HU-15, HU-24). El proveedor es el del usuario."""
    international = user.supplier.origin == SupplierOrigin.INTERNATIONAL
    context = {
        "user": user,
        "supplier": user.supplier,
        "error": error,
        "international": international,
        "currencies": catalog_service.active_entries(db, CatalogType.CURRENCY) if international else [],
        "values": values or {},
        "max_upload_mb": settings.max_upload_mb,
    }
    return templates.TemplateResponse(request, "invoices/new.html", context, status_code=status_code)


@router.get("/new")
def new_invoice(request: Request, db: Session = Depends(get_db), user=Depends(provider_only)):
    _ensure_supplier_active(user)
    return _new_invoice_page(request, db, user)


def _has_file(upload: UploadFile | None) -> bool:
    return upload is not None and bool(upload.filename)


async def _read_invoice_file(db: Session, upload: UploadFile, document_type: DocumentType, extension: str) -> bytes:
    """Contenido de un archivo del Paso 1 con la extension de su tipo y las verificaciones del almacenamiento."""
    if Path(upload.filename or "").suffix.lower() != extension:
        name = requirements.type_names(db).get(document_type.value, document_type.value)
        raise InvalidInputError(f"Formato no admitido para {name}. Formatos admitidos: {extension[1:].upper()}")
    content = await read_upload(upload)
    try:
        check_upload(upload.filename, content)
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from exc
    await upload.seek(0)
    return content


def _extract_files(pdf: bytes | None, xml: bytes | None, pdf_read=None) -> extraction.Extraction:
    """Extraccion sobre copias temporales de los archivos (aun no se guardan): errores de lectura como 400."""
    with tempfile.TemporaryDirectory(prefix="factura_") as tmp:
        pdf_path = xml_path = None
        if pdf is not None:
            pdf_path = Path(tmp) / "factura.pdf"
            pdf_path.write_bytes(pdf)
        if xml is not None:
            xml_path = Path(tmp) / "factura.xml"
            xml_path.write_bytes(xml)
        try:
            return extraction.extract(pdf_path, xml_path, pdf_read=pdf_read)
        except XMLParseError as exc:
            logger.warning(
                "xml.parse_failed",
                extra={"event": "xml.parse_failed", "error_type": type(exc).__name__, "error": str(exc)},
            )
            raise InvalidInputError(str(exc)) from exc
        except ValueError as exc:  # PDF que no abre: analyze_pdf ya registro el detalle
            raise InvalidInputError(str(exc)) from exc


def _extracted_values(db: Session, invoice: Invoice, result: extraction.Extraction) -> dict:
    """Campos de la factura que salen de sus archivos (RD-01): numero, periodo, UUID (si no es de otra factura),
    fecha, importes, moneda activa del catalogo y numero de orden de compra detectado."""
    data = result.data
    values = {
        "invoice_number": result.number[:100],
        "service_period": result.period or "",
        "uuid": None if uuid_owner(db, data.get("uuid"), invoice.id or 0) else data.get("uuid"),
        "invoice_date": datetime.fromisoformat(data["date"]).date() if data.get("date") else None,
        "purchase_order_number": detect_order_number(c.get("description") for c in data.get("concepts") or []).number,
    }
    for field in ("subtotal", "tax", "total"):
        value = data.get(field)
        values[field] = to_money(Decimal(str(value))) if value is not None else Decimal("0")
    if data.get("currency") in catalog_service.active_codes(db, CatalogType.CURRENCY):
        values["currency"] = data["currency"]
    return values


def _invoice_document(invoice: Invoice, user, document_type: DocumentType, stored, metadata: dict | None, pages=None):
    return Document(
        invoice_id=invoice.id,
        supplier_id=invoice.supplier_id,
        document_type=document_type.value,
        original_filename=stored.original_filename,
        stored_filename=stored.stored_filename,
        path=stored.relative_path,
        mime_type=stored.mime_type,
        file_size=stored.file_size,
        sha256=stored.sha256,
        uploaded_by=user.id,
        processing_status=ProcessingStatus.PROCESSED,
        page_count=pages,
        metadata_json=metadata,
    )


async def _create_national(request: Request, db: Session, user, pdf: UploadFile | None, xml: UploadFile | None):
    """Paso 1 nacional (HU-24): valida y lee los archivos, crea la factura en "Borrador" con los datos extraidos y
    guarda ambos documentos. Nada se escribe si un archivo o sus datos no son aceptables."""
    if not _has_file(pdf):
        return _new_invoice_page(request, db, user, extraction.MSG_NO_PDF, 400)
    try:
        pdf_content = await _read_invoice_file(db, pdf, DocumentType.INVOICE_PDF, ".pdf")
        xml_content = await _read_invoice_file(db, xml, DocumentType.INVOICE_XML, ".xml") if _has_file(xml) else None
        result = _extract_files(pdf_content, xml_content)
    except BusinessRuleError as exc:
        return _new_invoice_page(request, db, user, exc.message, exc.status_code)
    invoice = Invoice(
        internal_folio=provisional_folio(),
        supplier_id=user.supplier_id,
        uploaded_by=user.id,
        currency="MXN",
    )
    for field, value in _extracted_values(db, invoice, result).items():
        setattr(invoice, field, value)
    db.add(invoice)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if violates(exc, "uq_invoices_supplier_number"):
            return _new_invoice_page(request, db, user, MSG_DUPLICATE_NUMBER, 409)
        raise
    invoice.internal_folio = internal_folio(invoice.id, invoice.created_at)
    storage = LocalFileStorage()
    stored_pdf = await storage.save_invoice_file(invoice.id, pdf)
    db.add(
        _invoice_document(
            invoice,
            user,
            DocumentType.INVOICE_PDF,
            stored_pdf,
            result.pdf_metadata(),
            result.pdf_analysis["page_count"],
        )
    )
    log_upload(DocumentType.INVOICE_PDF.value, stored_pdf, invoice_id=invoice.id)
    if xml_content is not None:
        stored_xml = await storage.save_invoice_file(invoice.id, xml)
        db.add(_invoice_document(invoice, user, DocumentType.INVOICE_XML, stored_xml, result.xml_metadata()))
        log_upload(DocumentType.INVOICE_XML.value, stored_xml, invoice_id=invoice.id)
    db.flush()
    db.expire(invoice, ["documents"])
    sync_upload_status(db, invoice, requirements.pending_required(requirements.checklist(db, invoice)) == 0, user.id)
    audit(
        db,
        "INVOICE_CREATED",
        "Invoice",
        invoice.id,
        user.id,
        new={"folio": invoice.internal_folio, "source": result.source},
    )
    extraction.log_extraction(invoice.id, result)
    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}/data", status_code=303)


async def _create_international(request: Request, db: Session, user, submitted: dict):
    """Paso 1 internacional (HU-15, HU-24): numero de factura y datos del Invoice con su orden de compra. El periodo
    sale de la fecha de la factura."""
    errors = []
    number = (submitted.get("invoice_number") or "").strip()
    if not 1 <= len(number) <= 100:
        errors.append("Número de factura: debe tener de 1 a 100 caracteres")
    foreign_data, data_errors = foreign.parse_data(db, submitted)
    errors += data_errors
    if errors:
        return _new_invoice_page(request, db, user, " ".join(errors), 400, submitted)
    invoice = Invoice(
        internal_folio=provisional_folio(),
        supplier_id=user.supplier_id,
        uploaded_by=user.id,
        invoice_number=number,
        service_period=f"{foreign_data.invoice_date.month:02d}/{foreign_data.invoice_date.year}",
        subtotal=Decimal("0"),
        tax=Decimal("0"),
        total=Decimal("0"),
        currency=foreign_data.currency,
    )
    foreign.apply_data(invoice, foreign_data)
    db.add(invoice)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if violates(exc, "uq_invoices_supplier_number"):
            return _new_invoice_page(request, db, user, MSG_DUPLICATE_NUMBER, 409, submitted)
        raise
    invoice.internal_folio = internal_folio(invoice.id, invoice.created_at)
    audit(db, "INVOICE_CREATED", "Invoice", invoice.id, user.id, new={"folio": invoice.internal_folio})
    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}/documents", status_code=303)


@router.post("/new")
async def create_invoice(
    request: Request,
    pdf: UploadFile | None = File(None),
    xml: UploadFile | None = File(None),
    invoice_number: str = Form(""),
    purchase_order_number: str = Form(""),
    invoice_date: str = Form(""),
    subtotal: str = Form(""),
    tax: str = Form(""),
    currency: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(provider_only),
):
    """Paso 1 del registro. Un supplier_id, contrato, proyecto o periodo recibidos en el formulario se ignoran: la
    factura es del proveedor del usuario y sus datos salen de sus archivos o del Invoice (HU-24)."""
    await validate_csrf(request)
    _ensure_supplier_active(user)
    if user.supplier.origin != SupplierOrigin.INTERNATIONAL:
        return await _create_national(request, db, user, pdf, xml)
    submitted = {
        "invoice_number": invoice_number,
        "purchase_order_number": purchase_order_number,
        "invoice_date": invoice_date,
        "subtotal": subtotal,
        "tax": tax,
        "currency": currency,
    }
    return await _create_international(request, db, user, submitted)


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
    delete_error: str | None = None,
    delete_open: bool = False,
):
    """Detalle de la factura. Tambien es la respuesta 409 de un envio que no procede (submit_blocked): muestra las
    reglas en FAIL que se acaban de guardar; la 400 de una cancelacion rechazada (cancel_error) y la del pago sin
    confirmar (payment_error) y la de la eliminacion sin confirmar (delete_error)."""
    validations = list(
        db.scalars(
            select(ValidationResult)
            .where(ValidationResult.invoice_id == invoice.id)
            .order_by(ValidationResult.category, ValidationResult.rule_code)
        )
    )
    stored = extraction.stored_data(invoice)
    summary = validation_summary(validations)
    editable = is_editable(invoice)
    international = foreign.is_international(invoice)
    invoice_doc = foreign.current_invoice_document(invoice) if international else None
    reviewer = user.role != Role.PROVEEDOR
    cancelled = invoice.status == InvoiceStatus.CANCELLED
    paid = invoice.status == InvoiceStatus.PAID
    can_cancel = not reviewer and not cancelled and not paid
    can_pay = reviewer and invoice.status == InvoiceStatus.ACCEPTED
    ack_type = cancellation.acknowledgment_type(db) if can_cancel else None
    delivery = _status_delivery(db, invoice, notification, reviewer)
    return templates.TemplateResponse(
        request,
        "invoices/detail.html",
        {
            "user": user,
            "invoice": invoice,
            "validations": validations,
            "xml": stored.data if stored else None,
            "data_source": stored.source_label if stored else None,
            # Orden de compra ligada al enviar (HU-24) con sus partidas; antes del envio, el numero detectado.
            "order": invoice.purchase_order,
            "order_items": order_items(invoice.purchase_order.data) if invoice.purchase_order else (),
            "item_labels": PURCHASE_ORDER_ITEM_LABELS,
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
            "can_pay": can_pay,
            "paid": paid,
            # "Programar pago" (Ferromex): la solicitud en JSON de la ventana de confirmacion y, ya programado, la que
            # se registro. Solo para el PMO y el Administrador.
            "payment_json": payment.schedule_request_json(db, invoice, user, datetime.now(timezone.utc))
            if can_pay or (reviewer and paid)
            else None,
            "complement": payment.complement_status(invoice),
            "can_attach_complement": not reviewer and payment.is_pending(invoice),
            "payment_error": payment_error,
            # Eliminacion de una factura en Borrador o Cancelada: el Administrador o el proveedor duenio.
            "can_delete": deletion.can_delete(user, invoice),
            "delete_error": delete_error,
            "delete_open": delete_open or bool(delete_error),
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
    eliminar: str = "",
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    invoice = _invoice_or_404(db, invoice_id, user)
    # "Eliminar" de la cabecera abre el panel de eliminacion (?eliminar=1#deletion), sin JavaScript.
    return _detail_page(request, db, invoice, user, notice, notification=notification, delete_open=bool(eliminar))


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


REVIEW_STEP = "data"
# Tipos cuyo reemplazo vuelve a extraer los datos de la factura nacional (HU-24, RD-04).
INVOICE_FILES = {DocumentType.INVOICE_PDF.value: ".pdf", DocumentType.INVOICE_XML.value: ".xml"}


def _audit_text(value):
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, date):
        return value.isoformat()
    return value


async def _reextract(db: Session, invoice: Invoice, document_type: str, upload: UploadFile):
    """Datos de la factura nacional con el PDF o el XML nuevo y el otro archivo vigente, antes de guardar nada: 409 si
    no son la misma factura o si el numero resultante ya es de otra factura del proveedor; 422 sin datos."""
    content = await _read_invoice_file(db, upload, DocumentType(document_type), INVOICE_FILES[document_type])
    if document_type == DocumentType.INVOICE_PDF.value:
        xml_doc = extraction.current_document(invoice, DocumentType.INVOICE_XML)
        xml = LocalFileStorage().resolve(xml_doc.path).read_bytes() if xml_doc else None
        result = _extract_files(content, xml)
    else:
        pdf_doc = extraction.current_document(invoice, DocumentType.INVOICE_PDF)
        stored = (pdf_doc.metadata_json or {}).get("invoice") if pdf_doc else None
        result = _extract_files(None, content, pdf_read=(None, stored, (stored or {}).get("source")))
    values = _extracted_values(db, invoice, result)
    if values["invoice_number"] != invoice.invoice_number and db.scalar(
        select(Invoice.id).where(
            Invoice.supplier_id == invoice.supplier_id,
            Invoice.invoice_number == values["invoice_number"],
            Invoice.id != invoice.id,
        )
    ):
        raise DuplicateInvoiceError(MSG_DUPLICATE_NUMBER)
    return result, values


def _apply_extracted(db: Session, invoice: Invoice, values: dict, user_id: int) -> None:
    old, new = {}, {}
    for field, value in values.items():
        current = getattr(invoice, field)
        if current != value:
            old[field], new[field] = _audit_text(current), _audit_text(value)
            setattr(invoice, field, value)
    if new:
        audit(db, "INVOICE_DATA_EXTRACTED", "Invoice", invoice.id, user_id, old=old, new=new)


@router.post("/{invoice_id}/documents")
async def upload_document(
    invoice_id: int,
    request: Request,
    document_type: str = Form(...),
    upload: UploadFile = File(...),
    next_step: str = Form("", alias="next"),
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
    international = foreign.is_international(invoice)
    review = next_step == REVIEW_STEP and not international

    def error_page(message: str, status_code: int):
        if review:
            return _review_page(request, db, invoice, user, message, status_code)
        return _documents_page(request, db, invoice, user, message, status_code)

    # Antes de leer o escribir el archivo: el tipo debe aplicar al origen del proveedor y admitir la extension; el XML
    # del Complemento de Pago debe ser un CFDI de tipo P que relacione la factura.
    complement_data = extracted = None
    try:
        requirements.ensure_format(requirements.offered_type(db, invoice, document_type), upload.filename)
        if document_type == DocumentType.PAYMENT_COMPLEMENT_XML.value:
            content = await read_upload(upload)
            await upload.seek(0)
            complement_data = payment.check_complement_xml(invoice, content)
        if document_type in INVOICE_FILES and not international and invoice.status != InvoiceStatus.PAID:
            extracted = await _reextract(db, invoice, document_type, upload)
    except BusinessRuleError as exc:
        return error_page(exc.message, exc.status_code)
    if document_type == DocumentType.FOREIGN_INVOICE.value:
        # HU-15: el nombre de archivo del Invoice no se repite entre las facturas del proveedor (bloqueo por proveedor).
        try:
            foreign.ensure_unique_filename(db, invoice, Path(upload.filename or "").name)
        except BusinessRuleError as exc:
            return error_page(exc.message, 409)
    try:
        stored = await LocalFileStorage().save_invoice_file(invoice.id, upload)
        metadata, pages, processing = {}, None, ProcessingStatus.PROCESSED
        if extracted is not None:
            result = extracted[0]
            if stored.path.suffix == ".pdf":
                metadata, pages = result.pdf_metadata(), result.pdf_analysis["page_count"]
            else:
                metadata = result.xml_metadata()
        elif stored.path.suffix == ".pdf":
            pdf = analyze_pdf(stored.path)
            pages = pdf["page_count"]
            metadata = {k: v for k, v in pdf.items() if k != "text"}
            metadata["text_preview"] = pdf["text"][:2000]
        elif complement_data is not None:
            metadata = complement_data
        elif stored.path.suffix == ".xml":
            metadata = extraction.json_safe(parse_cfdi(stored.path))
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
        return error_page(str(exc), 400)
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
    if extracted is not None:
        # Nuevos datos de la factura con el archivo reemplazado (RD-04): la Validacion 1 del Paso 2 se recalcula.
        _apply_extracted(db, invoice, extracted[1], user.id)
        extraction.log_extraction(invoice.id, extracted[0])
    notify_reception = payment.register_complement(db, invoice, document, user.id)
    db.commit()
    if invoice.status != InvoiceStatus.PAID:
        target = REVIEW_STEP if review else "documents"
        return RedirectResponse(f"/invoices/{invoice.id}/{target}", status_code=303)
    # Complemento en la factura pagada: despues del commit, el aviso a Recepcion de Facturas (solo por el XML).
    query = {"notice": "complement_saved"}
    if notify_reception:
        delivery = payment.notify_complement(db, invoice, document, user.id)
        query["notification"] = delivery.id if delivery else "error"
    return RedirectResponse(f"/invoices/{invoice.id}/documents?{urlencode(query)}", status_code=303)


def _review_page(
    request: Request, db: Session, invoice: Invoice, user, error: str | None = None, status_code: int = 200
):
    """Paso 2 de la factura nacional (HU-24): paginas del PDF, datos extraidos con la Validacion 1 junto a cada dato,
    orden de compra detectada y archivos de la factura con su carga."""
    stored = extraction.stored_data(invoice)
    data = stored.data if stored else {}
    checks = {result.rule_code: result for result in identity_checks(db, invoice, stored)}
    pdf_doc = extraction.current_document(invoice, DocumentType.INVOICE_PDF)
    page_count = (pdf_doc.page_count or (pdf_doc.metadata_json or {}).get("page_count") or 1) if pdf_doc else 0
    items = requirements.checklist(db, invoice)
    pending = requirements.pending_required(items)
    concepts = data.get("concepts") or []
    context = {
        "user": user,
        "invoice": invoice,
        "stored": stored,
        "data": data,
        "checks": checks,
        "concepts": concepts,
        "order_reference": detect_order_number(c.get("description") for c in concepts),
        "pdf_doc": pdf_doc,
        "pages": list(range(1, min(page_count, document_view.MAX_PAGES) + 1)),
        "items": items,
        "complete": pending == 0,
        "pending_label": requirements.pending_label(pending),
        "requirement_labels": DOCUMENT_REQUIREMENT_LABELS,
        "formats_label": requirements.formats_label,
        "accept": ",".join(dict.fromkeys(ext for item in items for ext in requirements.extensions(item.document_type))),
        "can_submit": invoice.status in SUBMITTABLE_STATUSES,
        "error": error,
    }
    return templates.TemplateResponse(request, "invoices/review.html", context, status_code=status_code)


@router.get("/{invoice_id}/data")
def review_data(invoice_id: int, request: Request, db: Session = Depends(get_db), user=Depends(provider_only)):
    """Paso 2 "Revision". No cambia el estatus ni los resultados guardados: la Validacion 1 se calcula al mostrarla."""
    invoice = _invoice_or_404(db, invoice_id, user)
    if foreign.is_international(invoice):
        return RedirectResponse(f"/invoices/{invoice.id}/documents", status_code=303)
    if not is_editable(invoice):
        return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)
    return _review_page(request, db, invoice, user)


@router.post("/{invoice_id}/amounts")
async def update_amounts(
    invoice_id: int,
    request: Request,
    invoice_date: str = Form(""),
    subtotal: str = Form(""),
    tax: str = Form(""),
    currency: str = Form(""),
    purchase_order_number: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(provider_only),
):
    """Edicion de los datos del Invoice y su orden de compra mientras la factura es editable (HU-15, HU-24). El total
    lo calcula el servidor."""
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    lock_invoice(db, invoice)
    ensure_editable(invoice)
    if not foreign.is_international(invoice):
        raise InvalidInputError(foreign.MSG_NOT_INTERNATIONAL)
    values = {
        "invoice_date": invoice_date,
        "subtotal": subtotal,
        "tax": tax,
        "currency": currency,
        "purchase_order_number": purchase_order_number,
    }
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
        raise BusinessRuleError(result.missing_message)
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
    """Programa el pago de una factura "Autorizada" (PAID, "Programado para pago" en Ferromex; HU Complemento de
    Pagos): se confirma y despues sale el correo al proveedor, con el aviso del Complemento de Pago si lo requiere; un
    envio fallido no revierte la programacion."""
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


@router.post("/{invoice_id}/delete")
async def delete_invoice(
    invoice_id: int,
    request: Request,
    confirm: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(admin_or_provider),
):
    """Elimina una factura en Borrador o Cancelada (spec flujo-facturas). Sin la confirmacion vuelve al detalle con el
    error (400); en otro estatus, 409. Los archivos se borran del disco despues de confirmar en la base."""
    await validate_csrf(request)
    invoice = _invoice_or_404(db, invoice_id, user)
    folio = invoice.internal_folio
    try:
        paths = deletion.delete_invoice(db, invoice, user.id, bool(confirm))
    except InvalidInputError as exc:
        db.rollback()
        return _detail_page(request, db, invoice, user, delete_error=exc.message, status_code=400)
    db.commit()
    LocalFileStorage().discard(paths)
    return RedirectResponse(f"/invoices?{urlencode({'deleted': folio})}", status_code=303)
