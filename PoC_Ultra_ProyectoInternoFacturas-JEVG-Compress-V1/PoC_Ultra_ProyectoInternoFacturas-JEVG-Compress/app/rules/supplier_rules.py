from datetime import date

from app.core.constants import ContractStatus, SupplierOrigin, SupplierStatus
from app.rules.base import NOT_FOR_INTERNATIONAL, not_applicable, outcome


def supplier_rules(supplier, contract, requirement_rows):
    active_contract = bool(
        contract
        and contract.status == ContractStatus.ACTIVE
        and contract.start_date <= date.today() <= contract.end_date
    )
    minimum = all(r["present"] for r in requirement_rows if r["required"])
    validity = all(not r["expired"] for r in requirement_rows)
    if supplier.origin == SupplierOrigin.INTERNATIONAL:
        # El Anexo A es el expediente de una persona mexicana; el del internacional esta pendiente (P-06 de EP-01).
        expedient = [
            not_applicable("SUP-003", "SUP", "ERROR", NOT_FOR_INTERNATIONAL),
            not_applicable("SUP-004", "SUP", "WARNING", NOT_FOR_INTERNATIONAL),
        ]
    else:
        expedient = [
            outcome(
                "SUP-003",
                "SUP",
                minimum,
                "ERROR",
                "Expediente minimo disponible",
                "Expediente del proveedor incompleto",
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
        *expedient,
    ]
