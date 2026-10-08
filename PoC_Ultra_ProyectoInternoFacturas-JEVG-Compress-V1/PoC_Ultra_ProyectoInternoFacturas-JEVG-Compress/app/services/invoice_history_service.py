"""Historial de una factura (HU-19) y su seguimiento por el proveedor (HU-17): los envios del proveedor (auditoria
INVOICE_SUBMITTED), las revisiones del PMO (tabla reviews), la cancelacion (auditoria INVOICE_CANCELLED), el pago
(auditoria INVOICE_PAID) y cada carga del Complemento de Pago (auditoria PAYMENT_COMPLEMENT_UPLOADED), en orden
cronologico. Sin tablas nuevas."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.constants import STATUS_LABELS, InvoiceStatus, ReviewDecision
from app.core.timeutils import to_business
from app.models import AuditLog, Invoice, Review, User

SUBMITTED = "Enviada a validación"
CANCELLED = STATUS_LABELS[InvoiceStatus.CANCELLED]
PAID = STATUS_LABELS[InvoiceStatus.PAID]
COMPLEMENT_UPLOADED = "Complemento de pago adjuntado"
DATE_FORMAT = "%d/%m/%Y %H:%M"
# El proveedor ve la decision y el pago atribuidos al PMO, sin el nombre de quien los registro (EP-02 DT-07).
PROVIDER_REVIEWER = "PMO"
# La decision se muestra con la etiqueta del estatus al que lleva (modelo de estatus del ERS).
DECISION_LABELS = {
    ReviewDecision.ACCEPTED: STATUS_LABELS[InvoiceStatus.ACCEPTED],
    ReviewDecision.REJECTED: STATUS_LABELS[InvoiceStatus.REJECTED],
    ReviewDecision.REQUIRES_CORRECTION: STATUS_LABELS[InvoiceStatus.REQUIRES_CORRECTION],
    ReviewDecision.COMMENT: "Comentario",
}


@dataclass(frozen=True)
class HistoryEvent:
    at: datetime
    title: str
    actor: str | None
    detail: str | None = None


def _audited(db: Session, invoice: Invoice, action: str) -> list[tuple[datetime, str | None]]:
    return list(
        db.execute(
            select(AuditLog.timestamp, User.name)
            .outerjoin(User, User.id == AuditLog.user_id)
            .where(AuditLog.action == action, AuditLog.entity == "Invoice", AuditLog.entity_id == str(invoice.id))
        )
    )


def history(db: Session, invoice: Invoice, for_provider: bool = False) -> list[HistoryEvent]:
    """Eventos de la factura. Para el proveedor, las revisiones y el pago se atribuyen a "PMO" y se omiten los
    comentarios internos (COMMENT) del PoC."""
    events = [HistoryEvent(at, SUBMITTED, name) for at, name in _audited(db, invoice, "INVOICE_SUBMITTED")]
    reviews = db.scalars(select(Review).options(joinedload(Review.reviewer)).where(Review.invoice_id == invoice.id))
    for review in reviews:
        if for_provider and review.decision == ReviewDecision.COMMENT:
            continue
        reviewer = review.reviewer.name if review.reviewer else None
        events.append(
            HistoryEvent(
                review.created_at,
                DECISION_LABELS.get(review.decision, str(review.decision)),
                PROVIDER_REVIEWER if for_provider else reviewer,
                review.comments or None,
            )
        )
    if invoice.cancellation_deadline:
        deadline = to_business(invoice.cancellation_deadline).strftime(DATE_FORMAT)
        events += [
            HistoryEvent(at, CANCELLED, name, f"Fecha límite de aceptación: {deadline}")
            for at, name in _audited(db, invoice, "INVOICE_CANCELLED")
        ]
    if invoice.paid_at:
        due = invoice.payment_complement_due_at
        detail = f"Fecha límite del complemento: {to_business(due).strftime(DATE_FORMAT)}" if due else None
        events += [
            HistoryEvent(at, PAID, PROVIDER_REVIEWER if for_provider else name, detail)
            for at, name in _audited(db, invoice, "INVOICE_PAID")
        ]
    events += [
        HistoryEvent(at, COMPLEMENT_UPLOADED, name) for at, name in _audited(db, invoice, "PAYMENT_COMPLEMENT_UPLOADED")
    ]
    return sorted(events, key=lambda event: event.at)


def last_decision(db: Session, invoice: Invoice) -> Review | None:
    """Revision mas reciente con decision (no COMMENT): sus observaciones son las del correo de la decision."""
    return db.scalar(
        select(Review)
        .where(Review.invoice_id == invoice.id, Review.decision != ReviewDecision.COMMENT)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .limit(1)
    )


def decision_cause(db: Session, invoice: Invoice) -> str | None:
    """Motivo del rechazo u observaciones vigentes (HU-17): solo en "Rechazada" u "Observaciones"."""
    if invoice.status not in {InvoiceStatus.REJECTED, InvoiceStatus.REQUIRES_CORRECTION}:
        return None
    review = last_decision(db, invoice)
    return (review.comments if review else None) or invoice.comments
