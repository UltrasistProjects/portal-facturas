from pathlib import Path
from typing import Any

from app.services.ai.base import AnalyzerUnavailable, DocumentAnalyzer

MSG_UNAVAILABLE = "El analizador documental de la demo no lee PDF escaneados"


class LocalMockAnalyzer(DocumentAnalyzer):
    """Analizador local determinista: nunca realiza llamadas de red ni inventa datos de una factura."""

    def health_check(self) -> dict[str, Any]:
        return {"available": True, "provider": "mock", "external_calls": False}

    def analyze_document(self, path: Path) -> dict[str, Any]:
        return {"status": "PROCESSED", "document": path.name, "provider": "mock", "requires_human_review": False}

    def extract_invoice(self, path: Path) -> dict[str, Any]:
        # En la demo un PDF sin texto no se lee: el registro pide el XML (P-09 de la HU-24).
        raise AnalyzerUnavailable(MSG_UNAVAILABLE)
