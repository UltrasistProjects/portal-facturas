from decimal import Decimal

from app.rules.base import NOT_FOR_INTERNATIONAL, not_applicable, outcome


def _amount(data: dict | None, key: str, default) -> Decimal:
    value = (data or {}).get(key)
    return Decimal(str(value if value is not None else default))


def financial_rules(invoice, data, duplicate_uuid: bool, duplicate_number: bool, international: bool = False):
    """Consistencia de importes y duplicados. `data` son los datos del comprobante (XML o PDF); sin ellos, los importes
    son los de la factura: para el internacional, los capturados (HU-15). Las comparaciones contra el contrato
    (FIN-001, FIN-003 y FIN-006) se retiraron con HU-24: el monto se valida contra la orden de compra (OC-005)."""
    subtotal = _amount(data, "subtotal", invoice.subtotal)
    total = _amount(data, "total", invoice.total)
    tax = _amount(data, "tax", invoice.tax)
    consistent = abs((subtotal + tax) - total) <= Decimal("0.02")
    return [
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
            # El UUID detectado en el comprobante: si es duplicado, no se asigna a la factura.
            (data or {}).get("uuid") or invoice.uuid,
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
    ]
