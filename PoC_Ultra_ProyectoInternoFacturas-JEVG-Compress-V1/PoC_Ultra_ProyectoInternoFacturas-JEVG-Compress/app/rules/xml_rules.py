from app.rules.base import not_applicable, outcome
from app.services.validation_settings_service import RuleParameters, normalize_name

# Una comparacion desactivada en Reglas de Validacion (HU-06) conserva su codigo y severidad pero no afecta el score.
DISABLED = "Comparación desactivada en Reglas de Validación"


def _compare(
    enabled: bool,
    code: str,
    severity: str,
    passed: bool,
    message_pass: str,
    message_fail: str,
    expected,
    detected,
    source_reference: str | None = None,
):
    source = "CFDI.xml" if source_reference else None
    if not enabled:
        return not_applicable(code, "XML", severity, DISABLED, expected, source)
    return outcome(
        code, "XML", passed, severity, message_pass, message_fail, expected, detected, source, source_reference
    )


def xml_rules(data: dict | None, error: str | None, params: RuleParameters):
    """Reglas del CFDI con la configuracion vigente de Reglas de Validacion y el catalogo de monedas (D3)."""
    if data is None:
        return [outcome("XML-001", "XML", False, "CRITICAL", "XML valido", error or "XML invalido")]
    essentials = all(
        data.get(k) is not None for k in ("issuer_rfc", "receiver_rfc", "date", "subtotal", "total", "currency")
    )
    currencies = sorted(params.currencies)
    detected_name = data.get("receiver_name")
    return [
        outcome(
            "XML-001",
            "XML",
            True,
            "CRITICAL",
            "XML valido y parseable",
            "XML invalido",
            "CFDI parseable",
            "CFDI parseable",
        ),
        _compare(
            params.check_receiver_rfc,
            "XML-002",
            "CRITICAL",
            data.get("receiver_rfc") == params.receiver_rfc,
            "RFC receptor correcto",
            "RFC receptor incorrecto",
            params.receiver_rfc,
            data.get("receiver_rfc"),
            "Receptor.Rfc",
        ),
        _compare(
            params.check_payment_method,
            "XML-003",
            "ERROR",
            data.get("payment_method") == params.payment_method,
            "MetodoPago correcto",
            f"MetodoPago debe ser {params.payment_method}",
            params.payment_method,
            data.get("payment_method"),
        ),
        _compare(
            params.check_payment_form,
            "XML-004",
            "ERROR",
            data.get("payment_form") == params.payment_form,
            "FormaPago correcta",
            f"FormaPago debe ser {params.payment_form}",
            params.payment_form,
            data.get("payment_form"),
        ),
        _compare(
            params.check_cfdi_use,
            "XML-005",
            "ERROR",
            data.get("cfdi_use") in params.allowed_cfdi_uses,
            "UsoCFDI permitido",
            "UsoCFDI no permitido",
            ", ".join(params.allowed_cfdi_uses),
            data.get("cfdi_use"),
        ),
        outcome(
            "XML-006",
            "XML",
            bool(data.get("uuid")),
            "CRITICAL",
            "UUID presente",
            "UUID ausente",
            "UUID",
            data.get("uuid"),
        ),
        outcome(
            "XML-007",
            "XML",
            data.get("currency") in params.currencies,
            "ERROR",
            "Moneda valida",
            "Moneda no valida",
            "/".join(currencies),
            data.get("currency"),
        ),
        outcome("XML-008", "XML", essentials, "CRITICAL", "Datos esenciales presentes", "Faltan datos esenciales"),
        _compare(
            params.check_receiver_name,
            "XML-009",
            "ERROR",
            bool(detected_name) and normalize_name(detected_name) == normalize_name(params.receiver_name),
            "Razón social del receptor correcta",
            "Razón social del receptor incorrecta",
            params.receiver_name,
            detected_name,
            "Receptor.Nombre",
        ),
        _compare(
            params.check_receiver_postal_code,
            "XML-010",
            "ERROR",
            data.get("receiver_postal_code") == params.receiver_postal_code,
            "Código postal del receptor correcto",
            "Código postal del receptor incorrecto",
            params.receiver_postal_code,
            data.get("receiver_postal_code"),
            "Receptor.DomicilioFiscalReceptor",
        ),
    ]
