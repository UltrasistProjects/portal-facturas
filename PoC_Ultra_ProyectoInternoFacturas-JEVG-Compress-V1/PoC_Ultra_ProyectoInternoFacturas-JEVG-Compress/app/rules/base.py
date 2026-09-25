from decimal import Decimal

from app.schemas import ValidationOutcome


def outcome(
    code: str,
    category: str,
    passed: bool | None,
    severity: str,
    message_pass: str,
    message_fail: str,
    expected=None,
    detected=None,
    source_document=None,
    source_reference=None,
    evidence=None,
    confidence: Decimal | None = None,
    warning: bool = False,
) -> ValidationOutcome:
    status = "NOT_EVALUATED" if passed is None else ("PASS" if passed else ("WARNING" if warning else "FAIL"))
    return ValidationOutcome(
        rule_code=code,
        category=category,
        status=status,
        severity=severity,
        expected_value=None if expected is None else str(expected),
        detected_value=None if detected is None else str(detected),
        confidence=confidence,
        message=message_pass if passed else message_fail,
        source_document=source_document,
        source_reference=source_reference,
        evidence=evidence or {},
    )


def not_applicable(
    code: str, category: str, severity: str, message: str, expected=None, source_document=None
) -> ValidationOutcome:
    """Resultado de una regla que no aplica al caso. Conserva la severidad que tendria la regla; no altera el score
    porque calculate_score excluye NOT_APPLICABLE."""
    return ValidationOutcome(
        rule_code=code,
        category=category,
        status="NOT_APPLICABLE",
        severity=severity,
        expected_value=None if expected is None else str(expected),
        message=message,
        source_document=source_document,
    )
