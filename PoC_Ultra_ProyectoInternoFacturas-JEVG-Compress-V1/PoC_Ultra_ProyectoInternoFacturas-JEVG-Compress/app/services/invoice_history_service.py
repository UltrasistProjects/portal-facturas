"""Historial de una factura para el PMO (HU-19): los envios del proveedor (auditoria INVOICE_SUBMITTED) y las
revisiones del PMO (tabla reviews), en orden cronologico. Dos consultas, sin tablas nuevas."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.constants import STATUS_LABELS, InvoiceStatus, ReviewDecision
from app.models import AuditLog, Invoice, Review, User

SUBMITTED = "Enviada a validación"
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


def history(db: Session, invoice: Invoice) -> list[HistoryEvent]:
    submissions = db.execute(
        select(AuditLog.timestamp, User.name)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(
            AuditLog.action == "INVOICE_SUBMITTED",
            AuditLog.entity == "Invoice",
            AuditLog.entity_id == str(invoice.id),
        )
    )
    events = [HistoryEvent(at, SUBMITTED, name) for at, name in submissions]
    reviews = db.scalars(select(Review).options(joinedload(Review.reviewer)).where(Review.invoice_id == invoice.id))
    events += [
        HistoryEvent(
            review.created_at,
            DECISION_LABELS.get(review.decision, str(review.decision)),
            review.reviewer.name if review.reviewer else None,
            review.comments or None,
        )
        for review in reviews
    ]
    return sorted(events, key=lambda event: event.at)
