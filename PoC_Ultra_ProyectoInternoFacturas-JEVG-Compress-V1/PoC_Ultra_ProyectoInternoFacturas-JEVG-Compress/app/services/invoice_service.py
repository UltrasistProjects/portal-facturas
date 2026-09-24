from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.constants import ALLOWED_TRANSITIONS, InvoiceStatus
from app.core.errors import InvalidTransitionError
from app.models import Invoice
from app.services.audit_service import audit


def transition_invoice(db: Session, invoice: Invoice, target: InvoiceStatus, user_id: int | None = None) -> None:
    old = invoice.status
    if target not in ALLOWED_TRANSITIONS.get(old, set()):
        raise InvalidTransitionError(f"Transicion no permitida: {old.value} -> {target.value}")
    invoice.status = target
    now = datetime.now(timezone.utc)
    if target == InvoiceStatus.UNDER_REVIEW:
        invoice.submitted_at = now
    if target in {InvoiceStatus.ACCEPTED, InvoiceStatus.REJECTED, InvoiceStatus.REQUIRES_CORRECTION}:
        invoice.reviewed_at = now
        invoice.reviewed_by = user_id
    audit(db, "STATUS_CHANGED", "Invoice", invoice.id, user_id, {"status": old.value}, {"status": target.value})
