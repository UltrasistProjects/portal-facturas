from pathlib import Path
from typing import Any
from app.core.config import settings
from app.services.ai.base import DocumentAnalyzer


class AzureContentUnderstandingAnalyzer(DocumentAnalyzer):
    def _ready(self): return bool(settings.azure_content_understanding_endpoint and settings.azure_content_understanding_key)
    def health_check(self) -> dict[str, Any]: return {"available": self._ready(), "provider": "azure_content_understanding"}
    def _unavailable(self): raise RuntimeError("Azure Content Understanding no esta configurado")
    def analyze_document(self, path: Path) -> dict[str, Any]: self._unavailable()
    def extract_fields(self, path: Path, fields: list[str]) -> dict[str, Any]: self._unavailable()
    def semantic_compare(self, expected: str, detected: str) -> dict[str, Any]: self._unavailable()

