import unicodedata

from app.rules.base import NOT_FOR_INTERNATIONAL, not_applicable, outcome
from app.rules.definitions import RuleSet

# Una regla eliminada en Reglas de Validacion conserva su codigo y severidad pero no afecta el score.
DISABLED = "Regla inactiva en Reglas de Validación"
# Sin XML vigente y con el XML del CFDI fuera de los archivos obligatorios del proveedor nacional.
XML_NOT_REQUIRED = "El XML del CFDI no se exige en Archivos mínimos"
# Severidad de cada regla del CFDI; la conservan sus resultados NOT_APPLICABLE.
SEVERITIES = {
    "XML-001": "CRITICAL",
    "XML-002": "CRITICAL",
    "XML-003": "ERROR",
    "XML-004": "ERROR",
    "XML-005": "ERROR",
    "XML-006": "CRITICAL",
    "XML-007": "ERROR",
    "XML-008": "CRITICAL",
    "XML-009": "ERROR",
    "XML-010": "ERROR",
    "XML-011": "ERROR",
}


def normalize_name(text: str | None) -> str:
    """Razon social comparable: sin acentos, sin distinguir mayusculas y con los espacios colapsados (S6)."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c))
    return " ".join(plain.split()).casefold()


def _compare(
    rules: RuleSet,
    code: str,
    passed,
    message_pass: str,
    message_fail: str,
    detected,
    source_reference: str | None = None,
    expected=None,
):
    """Comparacion con el valor esperado de una regla nacional; NOT_APPLICABLE si la regla esta eliminada.
    `passed` recibe el valor esperado."""
    severity = SEVERITIES[code]
    source = "CFDI.xml" if source_reference else None
    parameter = rules.parameter(code)
    shown = expected if expected is not None else parameter
    if not rules.active(code):
        return not_applicable(code, "XML", severity, DISABLED, shown, source)
    return outcome(
        code, "XML", passed(parameter), severity, message_pass, message_fail, shown, detected, source, source_reference
    )


def xml_rules(data: dict | None, error: str | None, rules: RuleSet, international: bool = False, required: bool = True):
    """Reglas del CFDI con las reglas nacionales vigentes de Reglas de Validacion y el catalogo de monedas. El Invoice
    del proveedor internacional no es un CFDI: todas resultan NOT_APPLICABLE (HU-16). Sin XML y con el XML del CFDI
    fuera de los obligatorios (`required` falso), tambien."""
    if international:
        return [not_applicable(code, "XML", severity, NOT_FOR_INTERNATIONAL) for code, severity in SEVERITIES.items()]
    if data is None and error is None and not required:
        return [not_applicable(code, "XML", severity, XML_NOT_REQUIRED) for code, severity in SEVERITIES.items()]
    if data is None:
        return [outcome("XML-001", "XML", False, "CRITICAL", "XML valido", error or "XML invalido")]
    essentials = all(
        data.get(k) is not None for k in ("issuer_rfc", "receiver_rfc", "date", "subtotal", "total", "currency")
    )
    detected_name = data.get("receiver_name")
    uses = rules.parameter("XML-005") or []
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
            rules,
            "XML-002",
            lambda rfc: data.get("receiver_rfc") == rfc,
            "RFC receptor correcto",
            "RFC receptor incorrecto",
            data.get("receiver_rfc"),
            "Receptor.Rfc",
        ),
        _compare(
            rules,
            "XML-003",
            lambda method: data.get("payment_method") == method,
            "MetodoPago correcto",
            f"MetodoPago debe ser {rules.parameter('XML-003')}",
            data.get("payment_method"),
        ),
        _compare(
            rules,
            "XML-004",
            lambda form: data.get("payment_form") == form,
            "FormaPago correcta",
            f"FormaPago debe ser {rules.parameter('XML-004')}",
            data.get("payment_form"),
        ),
        _compare(
            rules,
            "XML-005",
            lambda allowed: data.get("cfdi_use") in allowed,
            "UsoCFDI permitido",
            "UsoCFDI no permitido",
            data.get("cfdi_use"),
            expected=", ".join(uses),
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
            data.get("currency") in rules.currencies,
            "ERROR",
            "Moneda valida",
            "Moneda no valida",
            "/".join(sorted(rules.currencies)),
            data.get("currency"),
        ),
        outcome("XML-008", "XML", essentials, "CRITICAL", "Datos esenciales presentes", "Faltan datos esenciales"),
        _compare(
            rules,
            "XML-009",
            lambda name: bool(detected_name) and normalize_name(detected_name) == normalize_name(name),
            "Razón social del receptor correcta",
            "Razón social del receptor incorrecta",
            detected_name,
            "Receptor.Nombre",
        ),
        _compare(
            rules,
            "XML-010",
            lambda postal_code: data.get("receiver_postal_code") == postal_code,
            "Código postal del receptor correcto",
            "Código postal del receptor incorrecto",
            data.get("receiver_postal_code"),
            "Receptor.DomicilioFiscalReceptor",
        ),
        _compare(
            rules,
            "XML-011",
            lambda regime: data.get("receiver_regime") == regime,
            "Régimen fiscal del receptor correcto",
            f"RegimenFiscalReceptor debe ser {rules.parameter('XML-011')}",
            data.get("receiver_regime"),
            "Receptor.RegimenFiscalReceptor",
        ),
    ]
