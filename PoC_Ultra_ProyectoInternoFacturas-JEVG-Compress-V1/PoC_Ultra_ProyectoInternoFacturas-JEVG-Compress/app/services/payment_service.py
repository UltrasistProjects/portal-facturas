"""Pago de la factura y Complemento de Pago (HU Complemento de Pagos).

El PMO o el Administrador marcan como "Pagada" una factura "Autorizada". Si el proveedor es nacional y el CFDI es de
metodo de pago PPD, la factura requiere Complemento de Pago: el proveedor tiene 72 horas para adjuntar su XML (un CFDI
de tipo P que relacione el UUID de la factura). Mientras tenga complementos vencidos, no puede enviar facturas a
validacion; el bloqueo se calcula en cada envio, sin tareas programadas (D8).

Ningun servicio hace commit: el endpoint confirma el pago o la carga y despues envia el correo, de modo que un envio
fallido no los revierte.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    DEFERRED_PAYMENT_METHOD,
    PAYMENT_COMPLEMENT_TYPES,
    PAYMENT_COMPLEMENT_WINDOW,
    DocumentType,
    InvoiceStatus,
    NotificationEvent,
    SupplierOrigin,
)
from app.core.errors import BusinessRuleError, InvalidInputError
from app.models import Document, EmailDelivery, Invoice, InvoiceDocumentType
from app.services import notification_service
from app.services import notification_templates as nt
from app.services.audit_service import audit
from app.services.invoice_service import lock_invoice, transition_invoice
from app.services.xml_service import XMLParseError, parse_payment_complement

logger = logging.getLogger(__name__)

ENTITY = "Invoice"
MSG_ALREADY_PAID = "La factura ya fue pagada"
MSG_NOT_ACCEPTED = "Sólo una factura autorizada se puede marcar como pagada"
MSG_NOT_REQUIRED = "La factura no requiere Complemento de Pago"
MSG_ONLY_COMPLEMENT = "En una factura pagada sólo se puede cargar el Complemento de Pago"
MSG_NOT_COMPLEMENT = "El XML no es un Complemento de Pago (CFDI de tipo P)"
MSG_NOT_RELATED = "El Complemento de Pago no relaciona la factura {uuid}"
MSG_NO_INVOICE_UUID = "El Complemento de Pago no relaciona la factura: la factura aún no tiene el UUID de su CFDI"
MSG_OVERDUE = (
    "No puede enviar facturas a validación: tiene complementos de pago vencidos de las facturas {numbers}. "
    "Adjúntelos para continuar."
)
PAYMENT_TYPE = "P"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _current_document(invoice: Invoice, document_type: str) -> Document | None:
    return next((d for d in invoice.documents if d.is_current and d.document_type == document_type), None)


def invoice_uuid(invoice: Invoice) -> str | None:
    """UUID del CFDI de la factura: el que asigno el motor o, antes de verificar, el del XML vigente."""
    if invoice.uuid:
        return invoice.uuid
    xml = _current_document(invoice, DocumentType.INVOICE_XML)
    return (xml.metadata_json or {}).get("uuid") if xml else None


def complement_type_active(db: Session) -> bool:
    """El tipo "Complemento de pago (XML)" sigue en Archivos minimos: es la unica forma de adjuntar el complemento.
    Si el Administrador lo elimino, ninguna factura lo requiere al pagarse y los vencidos no bloquean el envio."""
    stmt = select(InvoiceDocumentType.is_active).where(InvoiceDocumentType.code == DocumentType.PAYMENT_COMPLEMENT_XML)
    return bool(db.scalar(stmt))


def requires_complement(invoice: Invoice) -> bool:
    """Proveedor nacional y MetodoPago PPD en el XML del CFDI vigente, leido de los datos que extrajo el motor. Sin
    XML o sin metodo de pago, no lo requiere."""
    if invoice.supplier.origin != SupplierOrigin.NATIONAL:
        return False
    xml = _current_document(invoice, DocumentType.INVOICE_XML)
    return xml is not None and (xml.metadata_json or {}).get("payment_method") == DEFERRED_PAYMENT_METHOD


def complement_required(invoice: Invoice) -> bool:
    """La factura "Pagada" quedo con fecha limite del complemento al pagarse."""
    return invoice.status == InvoiceStatus.PAID and invoice.payment_complement_due_at is not None


def is_pending(invoice: Invoice) -> bool:
    return complement_required(invoice) and invoice.payment_complement_received_at is None


def is_overdue(invoice: Invoice, now: datetime | None = None) -> bool:
    return is_pending(invoice) and invoice.payment_complement_due_at <= (now or _now())


# --- Pago ---------------------------------------------------------------------------------------------------------


def mark_paid(db: Session, invoice: Invoice, user_id: int) -> None:
    """Pasa una factura "Autorizada" a "Pagada" y fija si requiere complemento. Bloquea la fila antes de comprobar el
    estatus: de dos pagos simultaneos, o de un pago y una cancelacion, el segundo recibe 409."""
    lock_invoice(db, invoice)
    if invoice.status == InvoiceStatus.PAID:
        raise BusinessRuleError(MSG_ALREADY_PAID)
    if invoice.status != InvoiceStatus.ACCEPTED:
        raise BusinessRuleError(MSG_NOT_ACCEPTED)
    transition_invoice(db, invoice, InvoiceStatus.PAID, user_id)
    required = requires_complement(invoice) and complement_type_active(db)
    if required:
        invoice.payment_complement_due_at = invoice.paid_at + PAYMENT_COMPLEMENT_WINDOW
        # Un complemento cargado antes del pago ya paso la verificacion del CFDI de pago: cuenta como adjuntado.
        complement = _current_document(invoice, DocumentType.PAYMENT_COMPLEMENT_XML)
        if complement is not None:
            invoice.payment_complement_received_at = complement.uploaded_at
    due = invoice.payment_complement_due_at
    audit(
        db,
        "INVOICE_PAID",
        ENTITY,
        invoice.id,
        user_id,
        new={
            "paid_at": invoice.paid_at.isoformat(),
            "requires_complement": required,
            "complement_due_at": due.isoformat() if due else None,
        },
    )


def complement_notice(invoice: Invoice) -> str:
    """Valor de {{aviso_complemento}}: el aviso con la fecha limite registrada, o vacio si no se requiere o ya se
    adjunto (p. ej. cargado antes del pago)."""
    if not is_pending(invoice):
        return ""
    return nt.COMPLEMENT_NOTICE.format(fecha=nt.format_datetime(invoice.payment_complement_due_at))


# --- Complemento --------------------------------------------------------------------------------------------------


def ensure_paid_upload(invoice: Invoice, document_type: str) -> None:
    """En una factura "Pagada" solo se carga el Complemento de Pago, y solo si lo requiere (409)."""
    if not complement_required(invoice):
        raise BusinessRuleError(MSG_NOT_REQUIRED)
    if document_type not in PAYMENT_COMPLEMENT_TYPES:
        raise BusinessRuleError(MSG_ONLY_COMPLEMENT)


def check_complement_xml(invoice: Invoice, content: bytes) -> dict:
    """Antes de escribir el archivo: CFDI de tipo P que relaciona el UUID de la factura (400). Devuelve los metadatos
    del documento (UUID del complemento y facturas relacionadas)."""
    try:
        data = parse_payment_complement(content)
    except XMLParseError:
        raise InvalidInputError(MSG_NOT_COMPLEMENT) from None
    if (data["voucher_type"] or "").upper() != PAYMENT_TYPE:
        raise InvalidInputError(MSG_NOT_COMPLEMENT)
    uuid = invoice_uuid(invoice)
    if not uuid:
        raise InvalidInputError(MSG_NO_INVOICE_UUID)
    if uuid.strip().upper() not in data["related_uuids"]:
        raise InvalidInputError(MSG_NOT_RELATED.format(uuid=uuid))
    return data


def register_complement(db: Session, invoice: Invoice, document: Document, user_id: int) -> bool:
    """Carga valida del XML del complemento: la primera fija payment_complement_received_at y cada una se audita.
    True si la factura esta "Pagada" y por tanto sale el correo a Recepcion de Facturas."""
    if document.document_type != DocumentType.PAYMENT_COMPLEMENT_XML:
        return False
    paid = complement_required(invoice)
    if paid and invoice.payment_complement_received_at is None:
        invoice.payment_complement_received_at = document.uploaded_at or _now()
    audit(
        db,
        "PAYMENT_COMPLEMENT_UPLOADED",
        ENTITY,
        invoice.id,
        user_id,
        new={"document_id": document.id, "uuid": (document.metadata_json or {}).get("uuid")},
    )
    return paid


def notify_complement(db: Session, invoice: Invoice, document: Document, user_id: int) -> EmailDelivery | None:
    """Correo "Complemento de pago adjuntado" a Recepcion de Facturas. Llamar despues de confirmar la carga."""
    try:
        return notification_service.notify(
            db,
            NotificationEvent.PAYMENT_COMPLEMENT,
            entity=ENTITY,
            entity_id=invoice.id,
            user_id=user_id,
            numero_factura=invoice.invoice_number,
            folio_interno=invoice.internal_folio,
            proveedor=invoice.supplier.business_name,
            monto=invoice.total,
            moneda=invoice.currency,
            fecha_estatus=document.uploaded_at,
        )
    except notification_service.NotificationDataError as exc:
        logger.warning(
            "payment.notification_error",
            extra={"event": "payment.notification_error", "invoice_id": invoice.id, "error_type": type(exc).__name__},
        )
        return None


# --- Pendientes y bloqueo -----------------------------------------------------------------------------------------


def pending_complements(db: Session, supplier_id: int) -> list[Invoice]:
    """Facturas del proveedor con el complemento pendiente, por fecha limite (indice ix_invoices_pending_complement)."""
    return list(
        db.scalars(
            select(Invoice)
            .where(
                Invoice.supplier_id == supplier_id,
                Invoice.status == InvoiceStatus.PAID,
                Invoice.payment_complement_due_at.is_not(None),
                Invoice.payment_complement_received_at.is_(None),
            )
            .order_by(Invoice.payment_complement_due_at, Invoice.id)
        )
    )


def overdue_complements(db: Session, supplier_id: int, now: datetime | None = None) -> list[Invoice]:
    now = now or _now()
    return [invoice for invoice in pending_complements(db, supplier_id) if invoice.payment_complement_due_at <= now]


def ensure_no_overdue_complements(db: Session, supplier_id: int) -> None:
    """Bloqueo del envio a validacion (409) mientras el proveedor tenga complementos vencidos y se puedan adjuntar."""
    if not complement_type_active(db):
        return
    overdue = overdue_complements(db, supplier_id)
    if overdue:
        raise BusinessRuleError(MSG_OVERDUE.format(numbers=", ".join(i.invoice_number for i in overdue)))


@dataclass(frozen=True)
class ComplementStatus:
    """Estado del complemento de una factura "Pagada" para el detalle: not_required, pending, overdue o received."""

    state: str
    text: str


def complement_status(invoice: Invoice, now: datetime | None = None) -> ComplementStatus | None:
    if invoice.status != InvoiceStatus.PAID:
        return None
    if not complement_required(invoice):
        return ComplementStatus("not_required", "No requerido")
    if invoice.payment_complement_received_at is not None:
        return ComplementStatus(
            "received", f"Adjuntado el {nt.format_datetime(invoice.payment_complement_received_at)}"
        )
    due = nt.format_datetime(invoice.payment_complement_due_at)
    if is_overdue(invoice, now):
        return ComplementStatus(
            "overdue", f"Vencido desde el {due}. El proveedor no puede enviar nuevas facturas a validación."
        )
    return ComplementStatus("pending", f"Pendiente: adjúntelo antes del {due}")


@dataclass(frozen=True)
class PendingComplement:
    invoice: Invoice
    due: str
    overdue: bool


def pending_notice(db: Session, supplier_id: int | None) -> list[PendingComplement]:
    """Aviso del tablero y del listado del proveedor: primero los vencidos, cada grupo por fecha limite."""
    if supplier_id is None:
        return []
    now = _now()
    rows = [
        PendingComplement(invoice, nt.format_datetime(invoice.payment_complement_due_at), is_overdue(invoice, now))
        for invoice in pending_complements(db, supplier_id)
    ]
    return sorted(rows, key=lambda row: not row.overdue)
