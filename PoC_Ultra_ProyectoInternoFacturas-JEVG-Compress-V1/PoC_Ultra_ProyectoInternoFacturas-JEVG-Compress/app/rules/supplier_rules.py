from datetime import date

from app.core.constants import ContractStatus, SupplierStatus
from app.rules.base import outcome


def supplier_rules(supplier, contract, requirement_rows):
    active_contract = bool(
        contract
        and contract.status == ContractStatus.ACTIVE
        and contract.start_date <= date.today() <= contract.end_date
    )
    minimum = all(r["present"] for r in requirement_rows)
    validity = all(not r["expired"] for r in requirement_rows)
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
        outcome(
            "SUP-003", "SUP", minimum, "ERROR", "Expediente minimo disponible", "Expediente del proveedor incompleto"
        ),
        outcome(
            "SUP-004",
            "SUP",
            validity,
            "WARNING",
            "Documentos vigentes",
            "Hay documentos con advertencia de vigencia",
            warning=True,
        ),
    ]
