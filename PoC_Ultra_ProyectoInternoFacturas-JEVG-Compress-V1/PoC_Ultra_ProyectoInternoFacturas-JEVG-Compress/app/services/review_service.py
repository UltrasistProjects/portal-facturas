"""Decision del PMO sobre una factura "Enviada" y los correos de cambio de estatus (HU-20, RF-10, RN-HU20-01 a
RN-HU20-03), tambien el de la cancelacion del proveedor (HU-14), el del pago (HU Complemento de Pagos) y su reenvio.

Ningun servicio hace commit: el endpoint confirma la decision, la cancelacion o el reenvio y despues envia el correo,
de modo que un envio fallido no la revierte.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import DeliveryStatus, InvoiceStatus, NotificationEvent, ReviewDecision
from app.core.errors import BusinessRuleError, InvalidInputError
from app.models import EmailDelivery, Invoice, Review
from app.services import notification_service, payment_service
from app.services.audit_service import audit
from app.services.invoice_history_service import last_decision
from app.services.invoice_service import ensure_can_accept, lock_invoice, transition_invoice

logger = logging.getLogger(__name__)

MAX_OBSERVATIONS = 2000
MSG_INVALID = "Decisión inválida"
MSG_OBSERVATIONS_REQUIRED = "Capture las observaciones"
MSG_OBSERVATIONS_TOO_LONG = f"Las observaciones admiten hasta {MAX_OBSERVATIONS:,} caracteres"
MSG_ALREADY_REVIEWED = "La factura ya fue revisada"
MSG_NOT_UNDER_REVIEW = "La factura no está en revisión"
MSG_NOTHING_TO_RESEND = "No hay una notificación fallida que reenviar"
ENTITY = "Invoice"

# Las tres decisiones del ERS (COMMENT queda solo en revisiones historicas).
DECISIONS = {
    ReviewDecision.ACCEPTED: InvoiceStatus.ACCEPTED,
    ReviewDecision.REJECTED: InvoiceStatus.REJECTED,
    ReviewDecision.REQUIRES_CORRECTION: InvoiceStatus.REQUIRES_CORRECTION,
}
DECIDED = frozenset(DECISIONS.values())
WITH_OBSERVATIONS = {InvoiceStatus.REJECTED, InvoiceStatus.REQUIRES_CORRECTION}
# Correo de cada estatus (D4): Autorizada y Cancelada van al buzon de Recepcion de Facturas; Rechazada, Observaciones
# y Pagada, al proveedor. El Complemento de pago adjuntado (payment_service) no es el correo de un estatus.
EVENTS = {
    InvoiceStatus.ACCEPTED: NotificationEvent.INVOICE_AUTHORIZED,
    InvoiceStatus.REJECTED: NotificationEvent.INVOICE_REJECTED,
    InvoiceStatus.REQUIRES_CORRECTION: NotificationEvent.INVOICE_OBSERVATIONS,
    InvoiceStatus.CANCELLED: NotificationEvent.INVOICE_CANCELLED,
    InvoiceStatus.PAID: NotificationEvent.INVOICE_PAID,
}
MAILBOX_EVENTS = {NotificationEvent.INVOICE_AUTHORIZED, NotificationEvent.INVOICE_CANCELLED}


def _decision(value: str) -> ReviewDecision:
    try:
        decision = ReviewDecision(value)
    except ValueError:
        raise InvalidInputError(MSG_INVALID) from None
    if decision not in DECISIONS:
        raise InvalidInputError(MSG_INVALID)
    return decision


def decide(db: Session, invoice: Invoice, value: str, observations: str, reviewer_id: int) -> Review:
    """Aplica la decision del PMO (D1, D3). Bloquea la fila antes de comprobar el estatus: de dos decisiones
    simultaneas, la segunda encuentra la factura ya revisada (409)."""
    decision = _decision(value)
    target = DECISIONS[decision]
    text = (observations or "").strip()
    if target in WITH_OBSERVATIONS and not text:
        raise InvalidInputError(MSG_OBSERVATIONS_REQUIRED)
    if len(text) > MAX_OBSERVATIONS:
        raise InvalidInputError(MSG_OBSERVATIONS_TOO_LONG)
    lock_invoice(db, invoice)
    if invoice.status != InvoiceStatus.UNDER_REVIEW:
        raise BusinessRuleError(MSG_ALREADY_REVIEWED if invoice.status in DECIDED else MSG_NOT_UNDER_REVIEW)
    if target == InvoiceStatus.ACCEPTED:
        ensure_can_accept(invoice)
    transition_invoice(db, invoice, target, reviewer_id)
    invoice.comments = text or None
    review = Review(invoice_id=invoice.id, reviewer_id=reviewer_id, decision=decision, comments=text or None)
    db.add(review)
    audit(db, decision.value, ENTITY, invoice.id, reviewer_id, new={"comments": text or None})
    logger.info("review.decided", extra={"event": "review.decided", "invoice_id": invoice.id, "decision": decision})
    return review


def send_notification(db: Session, invoice: Invoice, observations: str | None, user_id: int) -> EmailDelivery | None:
    """Correo del estatus actual de la factura (decision, cancelacion o pago). Llamar despues de confirmar la
    transaccion."""
    event = EVENTS[invoice.status]
    cancelled = invoice.status == InvoiceStatus.CANCELLED
    paid = invoice.status == InvoiceStatus.PAID
    values = {
        "numero_factura": invoice.invoice_number,
        "folio_interno": invoice.internal_folio,
        "proveedor": invoice.supplier.business_name,
        "monto": invoice.total,
        "moneda": invoice.currency,
        "fecha_estatus": invoice.cancelled_at if cancelled else invoice.paid_at if paid else invoice.reviewed_at,
    }
    if invoice.status in WITH_OBSERVATIONS:
        values["observaciones"] = observations
    if cancelled:
        values["fecha_limite_cancelacion"] = invoice.cancellation_deadline
    if paid:
        # Reproduce la fecha limite registrada al pagar: el reenvio da el mismo aviso.
        values["aviso_complemento"] = payment_service.complement_notice(invoice)
    try:
        return notification_service.notify(
            db,
            event,
            supplier_email=None if event in MAILBOX_EVENTS else invoice.supplier.email,
            entity=ENTITY,
            entity_id=invoice.id,
            user_id=user_id,
            **values,
        )
    except notification_service.NotificationDataError as exc:
        # Datos incompletos para componer el correo: nada se envia ni se registra en la bitacora.
        logger.warning(
            "review.notification_error",
            extra={"event": "review.notification_error", "invoice_id": invoice.id, "error_type": type(exc).__name__},
        )
        return None


def notify_decision(db: Session, invoice: Invoice, review: Review) -> EmailDelivery | None:
    """Correo de la decision (RN-HU20-02, RN-HU20-03). Llamar despues de confirmar la decision."""
    return send_notification(db, invoice, review.comments, review.reviewer_id)


def last_delivery(db: Session, invoice: Invoice) -> EmailDelivery | None:
    """Ultimo envio del correo del estatus actual de la factura, o None."""
    event = EVENTS.get(invoice.status)
    if event is None:
        return None
    return db.scalar(
        select(EmailDelivery)
        .where(
            EmailDelivery.entity == ENTITY,
            EmailDelivery.entity_id == str(invoice.id),
            EmailDelivery.event == event,
        )
        .order_by(EmailDelivery.created_at.desc(), EmailDelivery.id.desc())
        .limit(1)
    )


def can_resend(db: Session, invoice: Invoice) -> bool:
    delivery = last_delivery(db, invoice)
    return delivery is not None and delivery.status == DeliveryStatus.FAILED


def invoice_delivery(db: Session, invoice: Invoice, delivery_id: int | None) -> EmailDelivery | None:
    """El envio de la URL, solo si es de esta factura: un id ajeno no muestra nada (D4)."""
    if not delivery_id:
        return None
    delivery = db.get(EmailDelivery, delivery_id)
    if delivery is None or delivery.entity != ENTITY or delivery.entity_id != str(invoice.id):
        return None
    return delivery


def prepare_resend(db: Session, invoice: Invoice, user_id: int) -> str | None:
    """Reenvio de la notificacion de la decision, de la cancelacion o del pago (D5): bloquea, exige que el ultimo
    envio haya fallado, audita y devuelve las observaciones de la ultima revision (la cancelacion y el pago no las
    usan). El endpoint confirma y despues llama a send_notification."""
    lock_invoice(db, invoice)
    if not can_resend(db, invoice):
        raise BusinessRuleError(MSG_NOTHING_TO_RESEND)
    review = last_decision(db, invoice)
    audit(db, "INVOICE_NOTIFICATION_RESENT", ENTITY, invoice.id, user_id, new={"event": EVENTS[invoice.status].value})
    return review.comments if review else invoice.comments
