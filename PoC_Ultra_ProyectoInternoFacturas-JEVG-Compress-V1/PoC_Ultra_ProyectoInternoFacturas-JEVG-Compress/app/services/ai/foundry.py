from pathlib import Path
from typing import Any
from app.core.config import settings
from app.services.ai.base import DocumentAnalyzer


class AzureFoundryAnalyzer(DocumentAnalyzer):
    def _ready(self): return bool(settings.azure_openai_endpoint and settings.azure_openai_api_key and settings.azure_openai_deployment)
    def health_check(self) -> dict[str, Any]: return {"available": self._ready(), "provider": "azure_foundry"}
    def _unavailable(self): raise RuntimeError("Azure AI Foundry/OpenAI no esta configurado")
    def analyze_document(self, path: Path) -> dict[str, Any]: self._unavailable()
    def extract_fields(self, path: Path, fields: list[str]) -> dict[str, Any]: self._unavailable()
    def semantic_compare(self, expected: str, detected: str) -> dict[str, Any]: self._unavailable()

