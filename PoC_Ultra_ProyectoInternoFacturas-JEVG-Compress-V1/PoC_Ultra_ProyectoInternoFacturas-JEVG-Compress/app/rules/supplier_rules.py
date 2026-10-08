from datetime import date

from app.core.constants import ContractStatus, SupplierOrigin, SupplierStatus
from app.rules.base import NOT_FOR_INTERNATIONAL, not_applicable, outcome


def supplier_rules(supplier, contract, checklist):
    """`checklist` es el de supplier_requirements_service: los requisitos de alta del proveedor con la configuracion
    vigente (HU-21). SUP-003 exige los mismos requisitos que la autorizacion."""
    active_contract = bool(
        contract
        and contract.status == ContractStatus.ACTIVE
        and contract.start_date <= date.today() <= contract.end_date
    )
    international = supplier.origin == SupplierOrigin.INTERNATIONAL
    if international and not checklist.has_exigible:
        # Sin requisitos de alta exigibles para el internacional (P-06 de HU-21), como antes de HU-21.
        minimum = not_applicable("SUP-003", "SUP", "ERROR", NOT_FOR_INTERNATIONAL)
    else:
        pending = ", ".join(row.document_type.name for row in checklist.pending)
        minimum = outcome(
            "SUP-003",
            "SUP",
            not checklist.pending,
            "ERROR",
            "Expediente mínimo disponible",
            f"Expediente del proveedor incompleto. Pendientes: {pending}",
        )
    if international:
        validity = not_applicable("SUP-004", "SUP", "WARNING", NOT_FOR_INTERNATIONAL)
    else:
        validity = outcome(
            "SUP-004",
            "SUP",
            all(not row.expired for row in checklist.rows),
            "WARNING",
            "Documentos vigentes",
            "Hay documentos con advertencia de vigencia",
            warning=True,
        )
    return [
        outcome(
            "SUP-001",
            "SUP",
            supplier.status == SupplierStatus.ACTIVE,
            "CRITICAL",
            "Proveedor activo",
            "Proveedor inactivo",
        ),
        outcome("SUP-002", "SUP", active_contract, "CRITICAL", "Contrato vigente", "Contrato no vigente"),
        minimum,
        validity,
    ]
