from pathlib import Path
from typing import Any
from app.core.config import settings
from app.services.ai.base import DocumentAnalyzer


class AzureDocumentIntelligenceAnalyzer(DocumentAnalyzer):
    """Punto de extension. La integracion HTTP/SDK se habilita al definir endpoint y key."""
    def _ready(self) -> bool:
        return bool(settings.azure_document_intelligence_endpoint and settings.azure_document_intelligence_key)
    def health_check(self) -> dict[str, Any]:
        return {"available": self._ready(), "provider": "azure_document_intelligence"}
    def _unavailable(self):
        raise RuntimeError("Azure Document Intelligence no esta configurado")
    def analyze_document(self, path: Path) -> dict[str, Any]: self._unavailable()
    def extract_fields(self, path: Path, fields: list[str]) -> dict[str, Any]: self._unavailable()
    def semantic_compare(self, expected: str, detected: str) -> dict[str, Any]: self._unavailable()

