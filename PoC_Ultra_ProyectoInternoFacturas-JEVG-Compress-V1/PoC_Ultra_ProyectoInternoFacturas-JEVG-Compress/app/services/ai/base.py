from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class AnalyzerUnavailable(RuntimeError):  # noqa: N818 - nombre de dominio: el analizador "no disponible"
    """El analizador documental no esta configurado o no puede leer el documento."""


class DocumentAnalyzer(ABC):
    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...

    @abstractmethod
    def analyze_document(self, path: Path) -> dict[str, Any]: ...

    @abstractmethod
    def extract_invoice(self, path: Path) -> dict[str, Any]:
        """Datos de la representacion impresa de un CFDI sin capa de texto (OCR, HU-24), con las mismas claves que
        parse_cfdi. Lanza AnalyzerUnavailable si el analizador no esta disponible; nunca inventa datos."""
