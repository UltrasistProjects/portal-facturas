from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Motivos de AnalyzerUnavailable: se registran en el log (nunca el detalle del servicio ni datos del documento).
NOT_CONFIGURED = "not_configured"
AUTH = "auth"  # llave invalida o sin permiso
NOT_FOUND = "not_found"  # endpoint, modelo o deployment inexistente
QUOTA = "quota"  # 429: cuota o limite de peticiones
TIMEOUT = "timeout"
NETWORK = "network"
SERVICE = "service"  # 5xx u otra respuesta HTTP inesperada
FAILED = "failed"  # el servicio respondio, pero no pudo analizar el documento
INVALID_RESPONSE = "invalid_response"  # la respuesta no tiene la forma esperada
NO_TEXT = "no_text"  # el analizador necesita texto y el PDF no lo tiene


class AnalyzerUnavailable(RuntimeError):  # noqa: N818 - nombre de dominio: el analizador "no disponible"
    """El analizador documental no esta configurado o no puede leer el documento. `reason` es uno de los motivos de
    este modulo; el mensaje nunca incluye llaves ni contenido del documento."""

    def __init__(self, message: str, reason: str = NOT_CONFIGURED):
        super().__init__(message)
        self.reason = reason
        # Pasos que si se completaron antes de la falla (p. ej. el OCR cuando falla OpenAI), para medir el consumo.
        self.steps: list[dict[str, Any]] = []


@dataclass
class InvoiceReading:
    """Datos de la factura (las claves de parse_cfdi) y la evidencia del proceso, sin secretos: proveedor, modelo o
    deployment, version de API, confianza por campo y duracion."""

    data: dict[str, Any]
    source: str
    evidence: dict[str, Any] = field(default_factory=dict)


class DocumentAnalyzer(ABC):
    # Proveedor real (red): con la IA activa, todo PDF de factura pasa por el; el mock solo lee PDF sin texto.
    reads_all_pdfs = False
    source = "ocr"

    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...

    @abstractmethod
    def analyze_document(self, path: Path) -> dict[str, Any]: ...

    @abstractmethod
    def extract_invoice(self, path: Path) -> dict[str, Any]:
        """Datos de la representacion impresa de un CFDI (OCR, HU-24), con las mismas claves que parse_cfdi. Lanza
        AnalyzerUnavailable si el analizador no esta disponible; nunca inventa datos."""

    def read_invoice(self, path: Path) -> InvoiceReading:
        """extract_invoice con su evidencia; los analizadores reales la completan."""
        return InvoiceReading(self.extract_invoice(path), self.source)
