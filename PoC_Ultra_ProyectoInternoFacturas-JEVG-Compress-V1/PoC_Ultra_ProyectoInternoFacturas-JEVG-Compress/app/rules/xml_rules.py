from app.core.constants import BUSINESS_RULES
from app.rules.base import outcome


def xml_rules(data: dict | None, error: str | None = None):
    if data is None:
        return [outcome("XML-001", "XML", False, "CRITICAL", "XML valido", error or "XML invalido")]
    receiver = BUSINESS_RULES["receiver"]
    essentials = all(data.get(k) is not None for k in ("issuer_rfc", "receiver_rfc", "date", "subtotal", "total", "currency"))
    return [
        outcome("XML-001", "XML", True, "CRITICAL", "XML valido y parseable", "XML invalido", "CFDI parseable", "CFDI parseable"),
        outcome("XML-002", "XML", data.get("receiver_rfc") == receiver["rfc"], "CRITICAL", "RFC receptor correcto", "RFC receptor incorrecto", receiver["rfc"], data.get("receiver_rfc"), "CFDI.xml", "Receptor.Rfc"),
        outcome("XML-003", "XML", data.get("payment_method") == BUSINESS_RULES["payment_method"], "ERROR", "MetodoPago correcto", "MetodoPago debe ser PPD", BUSINESS_RULES["payment_method"], data.get("payment_method")),
        outcome("XML-004", "XML", data.get("payment_form") == BUSINESS_RULES["payment_form"], "ERROR", "FormaPago correcta", "FormaPago debe ser 99", BUSINESS_RULES["payment_form"], data.get("payment_form")),
        outcome("XML-005", "XML", data.get("cfdi_use") in BUSINESS_RULES["allowed_cfdi_uses"], "ERROR", "UsoCFDI permitido", "UsoCFDI no permitido", ", ".join(BUSINESS_RULES["allowed_cfdi_uses"]), data.get("cfdi_use")),
        outcome("XML-006", "XML", bool(data.get("uuid")), "CRITICAL", "UUID presente", "UUID ausente", "UUID", data.get("uuid")),
        outcome("XML-007", "XML", data.get("currency") in {"MXN", "USD", "EUR"}, "ERROR", "Moneda valida", "Moneda no valida", "MXN/USD/EUR", data.get("currency")),
        outcome("XML-008", "XML", essentials, "CRITICAL", "Datos esenciales presentes", "Faltan datos esenciales"),
    ]

