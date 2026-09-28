"""Envio de la factura a validacion (HU-13; EP-01 DT-02): validar y pasar a "Enviada" en un solo paso.

Modulo aparte porque orquesta invoice_service y validation_engine, y validation_engine depende (a traves de
document_requirements_service) de invoice_service. No hace commit: el endpoint confirma la transaccion tambien cuando
el envio no procede, para conservar los resultados que lo explican.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy.orm import Session

from app.core.constants import InvoiceStatus, RuleStatus
from app.core.errors import BusinessRuleError
from app.models import Invoice
from app.services import document_requirements_service as requirements
from app.services.audit_service import audit
from app.services.invoice_service import is_editable, lock_invoice, sync_upload_status, transition_invoice
from app.services.validation_engine import run_validation

MSG_NOT_SUBMITTABLE = "La factura no puede enviarse en su estatus actual"
MSG_MISSING_REQUIRED = "Faltan archivos obligatorios. Cárguelos antes de enviar"


class SubmissionOutcome(StrEnum):
    SUBMITTED = "SUBMITTED"
    MISSING_REQUIRED = "MISSING_REQUIRED"
    RULES_FAILED = "RULES_FAILED"


@dataclass(frozen=True)
class SubmissionResult:
    outcome: SubmissionOutcome
    # Resultados en FAIL (RuleOutcome del motor) cuando las reglas impiden el envio.
    failures: list = field(default_factory=list)


def submit_invoice(db: Session, invoice: Invoice, user_id: int) -> SubmissionResult:
    """Envia desde "Cargada" u "Observaciones" si el motor, con la configuracion vigente, no registra ningun FAIL.

    Orden: bloqueo de fila, estatus editable (409 si no), recalculo de "Borrador"/"Cargada" (en "Borrador" no se
    ejecuta el motor), motor y, sin FAIL, transicion a UNDER_REVIEW (asigna submitted_at) e INVOICE_SUBMITTED."""
    lock_invoice(db, invoice)
    if not is_editable(invoice):
        raise BusinessRuleError(MSG_NOT_SUBMITTABLE)
    complete = requirements.pending_required(requirements.checklist(db, invoice)) == 0
    sync_upload_status(db, invoice, complete, user_id)
    if invoice.status == InvoiceStatus.DRAFT:
        return SubmissionResult(SubmissionOutcome.MISSING_REQUIRED)
    outcome = run_validation(db, invoice, user_id)
    failures = [result for result in outcome["results"] if result.status == RuleStatus.FAIL]
    if failures:
        return SubmissionResult(SubmissionOutcome.RULES_FAILED, failures)
    transition_invoice(db, invoice, InvoiceStatus.UNDER_REVIEW, user_id)
    audit(db, "INVOICE_SUBMITTED", "Invoice", invoice.id, user_id)
    return SubmissionResult(SubmissionOutcome.SUBMITTED)
