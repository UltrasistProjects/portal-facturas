"""Azure Document Intelligence y OpenAI simulados (httpx.MockTransport): ninguna prueba de la IA sale a la red.

FakeAI responde como los servicios reales: Document Intelligence acepta el analisis (202 con Operation-Location) y lo
entrega al consultarlo; OpenAI responde con la API de Responses. Cada prueba cambia lo que hace falta para simular
una falla: un codigo HTTP, un tiempo agotado, un analisis fallido o una respuesta invalida.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from pydantic import SecretStr

from app.services.ai.document_intelligence import AzureDocumentIntelligenceAnalyzer
from app.services.ai.openai_analyzer import OpenAIInvoiceAnalyzer
from app.services.ai.pipeline import DocumentIntelligenceOpenAIAnalyzer
from app.services.pdf_service import analyze_pdf

ROOT = Path(__file__).resolve().parents[1]
PDF_3668 = ROOT / "data" / "pruebas-factura-3668" / "1-factura" / "CFDI-3668-GOHS60031745A.pdf"
DI_HOST, OPENAI_HOST = "di.test", "oai.test"
DI_KEY, OPENAI_KEY = "di-key-de-prueba-" + "x" * 20, "oai-key-de-prueba-" + "y" * 20
OPERATION = f"https://{DI_HOST}/documentintelligence/documentModels/prebuilt-invoice/analyzeResults/op-1"

# Lo que OpenAI devuelve para la 3668: las claves de parse_cfdi, como texto.
INVOICE_3668 = {
    "version": "4.0",
    "uuid": "A328F91A-DDDD-4624-89AC-877819F5B540",
    "series": None,
    "folio": "3668",
    "issuer_rfc": "GOHS60031745A",
    "issuer_name": "SOCORRO PATRICIA GONZALEZ HERNANDEZ",
    "issuer_regime": "612",
    "receiver_rfc": "IME010718PU3",
    "receiver_name": "INTERMODAL MEXICO",
    "receiver_postal_code": "11700",
    "receiver_regime": "601",
    "date": "2026-01-03T14:24:46",
    "subtotal": "3559.05",
    "tax": "569.45",
    "total": "4128.50",
    "currency": "MXN",
    "payment_form": "99",
    "payment_method": "PPD",
    "cfdi_use": "G03",
    "voucher_type": "I",
    "concepts": [
        {
            "description": "LTH TIPO L-31T-900 AR BATERIA (OC/25704872)",
            "quantity": "1.00",
            "unit_key": "H87",
            "unit": "PZ",
            "identification": "L-31T-900",
            "unit_value": "3559.05",
            "tax_object": "02",
            "amount": "3559.05",
            "taxes": [{"kind": "Traslado", "tax": "002", "rate": "0.160000", "base": "3559.05", "amount": "569.45"}],
        }
    ],
}
EXPECTED_3668 = {
    "uuid": "A328F91A-DDDD-4624-89AC-877819F5B540",
    "folio": "3668",
    "issuer_rfc": "GOHS60031745A",
    "receiver_rfc": "IME010718PU3",
    "subtotal": Decimal("3559.05"),
    "tax": Decimal("569.45"),
    "total": Decimal("4128.50"),
    "currency": "MXN",
    "payment_method": "PPD",
    "payment_form": "99",
    "cfdi_use": "G03",
}


def content_3668() -> str:
    """Texto de la 3668: el que el OCR de Document Intelligence entrega de la version escaneada."""
    return analyze_pdf(PDF_3668)["text"]


def currency(amount: float, confidence: float) -> dict[str, Any]:
    return {"type": "currency", "valueCurrency": {"amount": amount, "currencyCode": "MXN"}, "confidence": confidence}


def di_result(content: str) -> dict[str, Any]:
    """analyzeResult de prebuilt-invoice para la 3668 (la forma real; los RFC no los trae como campo)."""
    item = {
        "type": "object",
        "valueObject": {
            "Description": {"type": "string", "valueString": "LTH TIPO L-31T-900 AR BATERIA (OC/25704872)"},
            "Quantity": {"type": "number", "valueNumber": 1},
            "Unit": {"type": "string", "valueString": "PZ"},
            "UnitPrice": currency(3559.05, 0.9),
            "ProductCode": {"type": "string", "valueString": "L-31T-900"},
            "Amount": currency(3559.05, 0.95),
        },
    }
    fields = {
        "InvoiceId": {"type": "string", "valueString": "3668", "confidence": 0.843},
        "VendorName": {"type": "string", "valueString": "SOCORRO PATRICIA GONZALEZ HERNANDEZ", "confidence": 0.917},
        "CustomerName": {"type": "string", "valueString": "INTERMODAL MEXICO", "confidence": 0.929},
        "InvoiceDate": {
            "type": "date",
            "valueDate": "2026-01-03",
            "content": "2026-01-03T14:24:46",
            "confidence": 0.414,
        },
        "SubTotal": currency(3559.05, 0.941),
        "TotalTax": currency(569.45, 0.808),
        "InvoiceTotal": currency(4128.5, 0.936),
        "Items": {"type": "array", "valueArray": [item]},
    }
    return {
        "apiVersion": "2024-11-30",
        "modelId": "prebuilt-invoice",
        "content": content,
        "contentFormat": "text",
        "pages": [{"pageNumber": 1}],
        "documents": [{"docType": "invoice", "confidence": 1, "fields": fields}],
    }


def responses_body(payload: Any, status: str = "completed") -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return {
        "status": status,
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "content": [{"type": "output_text", "text": text}]},
        ],
        "usage": {"input_tokens": 1900, "output_tokens": 300},
    }


@dataclass
class FakeAI:
    content: str = field(default_factory=content_3668)
    invoice: Any = field(default_factory=lambda: json.loads(json.dumps(INVOICE_3668)))
    polls_before_ready: int = 1
    di_submit_status: int = 202
    di_poll_status: int = 200
    di_state: str = "succeeded"
    di_error: Exception | None = None
    openai_status: int = 200
    openai_error: Exception | None = None
    openai_body: dict | None = None
    requests: list[httpx.Request] = field(default_factory=list)
    _polls: int = 0

    def __post_init__(self):
        self.transport = httpx.MockTransport(self.handle)

    def calls(self, host: str) -> list[httpx.Request]:
        return [request for request in self.requests if request.url.host == host]

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == DI_HOST:
            return self._di(request)
        if request.url.host == OPENAI_HOST:
            return self._openai(request)
        return httpx.Response(404)  # pragma: no cover - una prueba apunto a otro host

    def _di(self, request: httpx.Request) -> httpx.Response:
        if self.di_error is not None:
            raise self.di_error
        if request.url.path.endswith("/info"):
            return httpx.Response(self.di_poll_status, json={"customDocumentModels": {"count": 0}})
        if request.method == "POST":
            if self.di_submit_status != 202:
                return httpx.Response(self.di_submit_status, json={"error": {"code": "Denied"}})
            return httpx.Response(202, headers={"Operation-Location": OPERATION, "Retry-After": "0"})
        if self.di_poll_status != 200:
            return httpx.Response(self.di_poll_status)
        self._polls += 1
        if self._polls <= self.polls_before_ready or self.di_state == "running":
            return httpx.Response(200, headers={"Retry-After": "0"}, json={"status": "running"})
        if self.di_state == "succeeded":
            return httpx.Response(200, json={"status": "succeeded", "analyzeResult": di_result(self.content)})
        return httpx.Response(200, json={"status": self.di_state, "error": {"code": "InvalidContent"}})

    def _openai(self, request: httpx.Request) -> httpx.Response:
        if self.openai_error is not None:
            raise self.openai_error
        if self.openai_status != 200:
            return httpx.Response(self.openai_status, json={"error": {"code": "x"}})
        return httpx.Response(200, json=self.openai_body or responses_body(self.invoice))

    def ocr(self, **kwargs) -> AzureDocumentIntelligenceAnalyzer:
        return AzureDocumentIntelligenceAnalyzer(transport=self.transport, sleep=lambda _: None, **kwargs)

    def llm(self, **kwargs) -> OpenAIInvoiceAnalyzer:
        return OpenAIInvoiceAnalyzer(transport=self.transport, **kwargs)

    def pipeline(self) -> DocumentIntelligenceOpenAIAnalyzer:
        return DocumentIntelligenceOpenAIAnalyzer(self.ocr(), self.llm())


def configure(monkeypatch, provider: str = "document_intelligence_openai", azure: bool = True) -> None:
    """Configuracion de la IA con hosts de prueba (nunca la del .env)."""
    from app.core.config import settings

    values = {
        "ai_enabled": True,
        "document_ai_provider": provider,
        "azure_document_intelligence_endpoint": f"https://{DI_HOST}",
        "azure_document_intelligence_key": SecretStr(DI_KEY),
        "azure_document_intelligence_model": "prebuilt-invoice",
        "azure_document_intelligence_api_version": "2024-11-30",
        "azure_document_intelligence_timeout": 25,
        "azure_openai_endpoint": f"https://{OPENAI_HOST}" if azure else "",
        "azure_openai_api_key": SecretStr(OPENAI_KEY if azure else ""),
        "azure_openai_deployment": "gpt-prueba" if azure else "",
        "azure_openai_api_version": "2025-04-01-preview",
        "openai_api_key": SecretStr("" if azure else OPENAI_KEY),
        "openai_model": "" if azure else "gpt-prueba",
        "openai_base_url": f"https://{OPENAI_HOST}/v1",
        "openai_reasoning_effort": "minimal",
        "openai_timeout": 25,
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
