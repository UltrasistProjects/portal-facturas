"""Reglas del flujo de facturas. Los routers solo traducen HTTP <-> servicio (AUDITORIA COD-01).

Ningun servicio hace commit: el limite transaccional pertenece al endpoint (AUDITORIA COD-09).
"""

from collections.abc import Iterable
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import ALLOWED_TRANSITIONS, InvoiceStatus, ReviewDecision, RuleStatus, Severity
from app.core.errors import BusinessRuleError, InvalidInputError, InvalidTransitionError
from app.core.timeutils import to_business
from app.models import Invoice, Review
from app.services.audit_service import audit
from app.services.validation_score_service import calculate_score

# Estados en los que el expediente admite cambios de documentos.
EDITABLE_STATUSES = frozenset({InvoiceStatus.DRAFT, InvoiceStatus.REQUIRES_CORRECTION, InvoiceStatus.VALIDATION_FAILED})
PREVALIDATABLE_STATUSES = EDITABLE_STATUSES | {InvoiceStatus.UPLOADED}
REVIEW_TARGETS = {
    ReviewDecision.ACCEPTED: InvoiceStatus.ACCEPTED,
    ReviewDecision.REJECTED: InvoiceStatus.REJECTED,
    ReviewDecision.REQUIRES_CORRECTION: InvoiceStatus.REQUIRES_CORRECTION,
}


def provisional_folio() -> str:
    """Marcador unico mientras la BD asigna el id; se reemplaza en la misma transaccion (cabe en String(30))."""
    return f"TMP-{uuid4().hex[:24]}"


def internal_folio(invoice_id: int, created_at: datetime) -> str:
    """Folio derivado del id asignado por la BD: sin carrera entre altas concurrentes (AUDITORIA COD-06)."""
    return f"FAC-{to_business(created_at).year}-{invoice_id:05d}"


def violates(exc: IntegrityError, constraint_columns: str) -> bool:
    """True si el IntegrityError corresponde a la restriccion sobre esas columnas (mensaje de SQLite)."""
    return constraint_columns in str(exc.orig)


def is_editable(invoice: Invoice) -> bool:
    return invoice.status in EDITABLE_STATUSES


def ensure_editable(invoice: Invoice) -> None:
    if not is_editable(invoice):
        raise BusinessRuleError("El expediente no admite cambios en su estado actual")


def ensure_prevalidatable(invoice: Invoice) -> None:
    if invoice.status not in PREVALIDATABLE_STATUSES:
        raise BusinessRuleError("La factura no puede prevalidarse en este estado")


def has_critical_blockers(validations: Iterable) -> bool:
    return any(v.status == RuleStatus.FAIL and v.severity == Severity.CRITICAL for v in validations)


def ensure_can_accept(invoice: Invoice) -> None:
    """La regla de control central del flujo: nunca se acepta una factura con un FAIL critico."""
    if has_critical_blockers(invoice.validations):
        raise BusinessRuleError("No se puede aceptar con bloqueos criticos")


def next_clickbalance_status(invoice: Invoice) -> InvoiceStatus:
    if invoice.status == InvoiceStatus.ACCEPTED:
        return InvoiceStatus.READY_FOR_CLICKBALANCE
    return InvoiceStatus.UPLOADED_TO_CLICKBALANCE


def validation_summary(validations: Iterable) -> dict:
    return calculate_score(list(validations))


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


def review_invoice(db: Session, invoice: Invoice, decision: str, comments: str, reviewer_id: int) -> None:
    if decision == ReviewDecision.COMMENT:
        db.add(
            Review(invoice_id=invoice.id, reviewer_id=reviewer_id, decision=ReviewDecision.COMMENT, comments=comments)
        )
        audit(db, "COMMENT_ADDED", "Invoice", invoice.id, reviewer_id, new={"comments": comments})
        return
    target = REVIEW_TARGETS.get(decision)
    if target is None:
        raise InvalidInputError("Decision invalida")
    if target == InvoiceStatus.ACCEPTED:
        ensure_can_accept(invoice)
    transition_invoice(db, invoice, target, reviewer_id)
    invoice.comments = comments
    db.add(Review(invoice_id=invoice.id, reviewer_id=reviewer_id, decision=decision, comments=comments))
    audit(db, decision, "Invoice", invoice.id, reviewer_id, new={"comments": comments})
