from app.core.constants import BUSINESS_RULES


def calculate_score(results) -> dict:
    evaluated = [r for r in results if r.status not in {"NOT_APPLICABLE", "NOT_EVALUATED"}]
    max_penalty = sum(BUSINESS_RULES["score_weights"].get(r.severity, 0) for r in evaluated) or 1
    penalty = sum(BUSINESS_RULES["score_weights"].get(r.severity, 0) for r in evaluated if r.status in {"FAIL", "WARNING"})
    score = max(0, round(100 * (1 - penalty / max_penalty)))
    return {"score": score, "total": len(results), "pass": sum(r.status == "PASS" for r in results),
            "warnings": sum(r.status == "WARNING" for r in results), "errors": sum(r.status == "FAIL" for r in results),
            "blockers": sum(r.status == "FAIL" and r.severity == "CRITICAL" for r in results)}

