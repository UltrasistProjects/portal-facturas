from decimal import Decimal

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
            confidence=Decimal(str(result.get("confidence", 0))),
            message=result.get("explanation", "Comparacion semantica"),
            source_document="Mock/AI adapter",
            source_reference="semantic_compare",
            evidence={"items": result.get("evidence", [])},
        )
    ]
