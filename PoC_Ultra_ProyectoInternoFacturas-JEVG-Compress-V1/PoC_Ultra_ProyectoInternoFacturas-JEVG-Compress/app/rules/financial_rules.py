from decimal import Decimal

from app.rules.base import NOT_FOR_INTERNATIONAL, not_applicable, outcome
from app.services.contract_service import current_amendment_id
from app.services.reconciliation_service import reconcile_amount


def financial_rules(
    invoice, contract, xml_data, duplicate_uuid: bool, duplicate_number: bool, international: bool = False
):
    """Sin XML, los importes y la moneda son los de la factura: para el internacional, los capturados (HU-15)."""
    subtotal = Decimal(
        xml_data.get("subtotal") if xml_data and xml_data.get("subtotal") is not None else invoice.subtotal
    )
    total = Decimal(xml_data.get("total") if xml_data and xml_data.get("total") is not None else invoice.total)
    tax = Decimal(xml_data.get("tax") if xml_data and xml_data.get("tax") is not None else invoice.tax)
    rec = reconcile_amount(Decimal(contract.authorized_amount), subtotal) if contract else None
    consistent = abs((subtotal + tax) - total) <= Decimal("0.02")
    return [
        outcome(
            "FIN-001",
            "FIN",
            rec.result == "PASS" if rec else None,
            "CRITICAL",
            "Monto dentro de lo autorizado",
            "El subtotal excede el monto autorizado",
            contract.authorized_amount if contract else None,
            subtotal,
            "CFDI.xml",
            "Comprobante.SubTotal",
            {
                "difference": str(rec.difference) if rec else None,
                # Monto y enmienda vigentes al validar: la evidencia sigue siendo auditable si el contrato cambia.
                "authorized_amount": f"{contract.authorized_amount:.2f}" if contract else None,
                "amendment_id": current_amendment_id(contract) if contract else None,
            },
        ),
        outcome(
            "FIN-002",
            "FIN",
            consistent,
            "ERROR",
            "Subtotal, impuestos y total son consistentes",
            "Componentes numericos inconsistentes",
            subtotal + tax,
            total,
        ),
        outcome(
            "FIN-003",
            "FIN",
            invoice.currency == contract.currency if contract else None,
            "ERROR",
            "Moneda coincide con contrato",
            "Moneda no coincide con contrato",
            contract.currency if contract else None,
            invoice.currency,
        ),
        # El Invoice no tiene UUID: su duplicado se controla por nombre de archivo (FIN-007, HU-15).
        not_applicable("FIN-004", "FIN", "CRITICAL", NOT_FOR_INTERNATIONAL)
        if international
        else outcome(
            "FIN-004",
            "FIN",
            not duplicate_uuid,
            "CRITICAL",
            "UUID no duplicado",
            "Posible factura duplicada por UUID",
            "UUID unico",
            # El UUID detectado en el XML: si es duplicado, no se asigna a la factura.
            (xml_data or {}).get("uuid") or invoice.uuid,
        ),
        outcome(
            "FIN-005",
            "FIN",
            not duplicate_number,
            "ERROR",
            "Numero de factura no duplicado",
            "Posible duplicado por proveedor y numero",
            "Numero unico",
            invoice.invoice_number,
        ),
        outcome(
            "FIN-006",
            "FIN",
            rec.result == "PASS" if rec else None,
            "WARNING",
            "Diferencia dentro del monto autorizado",
            "Existe diferencia contra monto autorizado",
            contract.authorized_amount if contract else None,
            subtotal,
            evidence={
                "absolute_difference": str(rec.difference) if rec else None,
                "percentage": str(rec.percentage) if rec else None,
            },
        ),
    ]
