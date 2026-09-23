from pathlib import Path
from typing import Any
from app.rules.contract_rules import normalize_text
from app.services.ai.base import DocumentAnalyzer


class LocalMockAnalyzer(DocumentAnalyzer):
    """Analizador local determinista: nunca realiza llamadas de red."""
    def health_check(self) -> dict[str, Any]:
        return {"available": True, "provider": "mock", "external_calls": False}

    def analyze_document(self, path: Path) -> dict[str, Any]:
        return {"status": "PROCESSED", "document": path.name, "provider": "mock", "requires_human_review": False}

    def extract_fields(self, path: Path, fields: list[str]) -> dict[str, Any]:
        return {name: {"value": f"DEMO_{name}", "confidence": 0.85, "source": path.name} for name in fields}

    def semantic_compare(self, expected: str, detected: str) -> dict[str, Any]:
        exp, det = normalize_text(expected), normalize_text(detected)
        power_match = "power platform" in exp and ("power automate" in det or "power apps" in det)
        overlap = set(exp.split()) & set(det.split())
        matched = power_match or bool(overlap)
        confidence = 0.93 if power_match else (0.82 if matched else 0.35)
        return {"result": "MATCH" if matched else "AMBIGUOUS", "confidence": confidence,
                "explanation": "Coincidencia semantica mock determinista; requiere criterio humano si es ambigua.",
                "expected": expected, "detected": detected,
                "evidence": [{"source": "Contrato/metadata", "value": expected}, {"source": "CFDI.xml/Conceptos", "value": detected}]}

