from decimal import ROUND_HALF_UP, Decimal

from app.schemas import ValidationOutcome


def semantic_outcomes(result: dict) -> list[ValidationOutcome]:
    return [
        ValidationOutcome(
            rule_code="SEM-001",
            category="SEM",
            status="PASS" if result["result"] == "MATCH" else "WARNING",
            severity="WARNING",
            expected_value=result.get("expected"),
            detected_value=result.get("detected"),
            # 4 decimales: la escala de validation_results.confidence_bp.
            confidence=Decimal(str(result.get("confidence", 0))).quantize(Decimal("0.0001"), ROUND_HALF_UP),
            message=result.get("explanation", "Comparacion semantica"),
            source_document="Mock/AI adapter",
            source_reference="semantic_compare",
            evidence={"items": result.get("evidence", [])},
        )
    ]
