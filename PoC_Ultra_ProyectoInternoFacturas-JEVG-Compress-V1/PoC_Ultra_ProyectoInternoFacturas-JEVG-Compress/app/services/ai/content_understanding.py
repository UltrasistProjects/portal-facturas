from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.ai.base import AnalyzerUnavailable, DocumentAnalyzer


class AzureContentUnderstandingAnalyzer(DocumentAnalyzer):
    def _ready(self):
        return bool(
            settings.azure_content_understanding_endpoint
            and settings.azure_content_understanding_key.get_secret_value()
        )

    def health_check(self) -> dict[str, Any]:
        return {"available": self._ready(), "provider": "azure_content_understanding"}

    def _unavailable(self):
        raise AnalyzerUnavailable("Azure Content Understanding no esta configurado")

    def analyze_document(self, path: Path) -> dict[str, Any]:
        self._unavailable()

    def extract_invoice(self, path: Path) -> dict[str, Any]:
        self._unavailable()
