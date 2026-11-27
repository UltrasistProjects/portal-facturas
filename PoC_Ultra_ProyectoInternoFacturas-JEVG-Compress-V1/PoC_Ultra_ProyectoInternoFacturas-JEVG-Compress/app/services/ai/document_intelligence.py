"""Azure Document Intelligence: OCR y layout del PDF y campos del modelo de facturas, con su confianza.

El analisis es asincrono: POST .../documentModels/{modelo}:analyze responde 202 con Operation-Location y esa URL se
consulta (respetando Retry-After) hasta "succeeded" o "failed", dentro del plazo AZURE_DOCUMENT_INTELLIGENCE_TIMEOUT.
El contenido se pide en Markdown, que conserva las tablas, en los modelos que lo admiten (prebuilt-layout); los
demas lo devuelven como texto.

Por si solo (DOCUMENT_AI_PROVIDER=document_intelligence), los datos salen de los campos del modelo y, para lo que el
modelo no trae (UUID, RFC, claves del SAT), del parser deterministico aplicado al texto del OCR.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.services.ai import normalize
from app.services.ai.base import (
    FAILED,
    INVALID_RESPONSE,
    NOT_CONFIGURED,
    AnalyzerUnavailable,
    DocumentAnalyzer,
    InvoiceReading,
)
from app.services.ai.http import Deadline, client, json_body, log_call, ms, send

PROVIDER = "azure_document_intelligence"
SERVICE = "Azure Document Intelligence"
SOURCE = "ocr_di"
HEALTH_TIMEOUT = 10
DEFAULT_POLL = 1.0
MAX_POLL = 5.0
# Campo del modelo prebuilt-invoice -> clave de parse_cfdi.
FIELD_MAP = {
    "InvoiceId": "folio",
    "VendorName": "issuer_name",
    "VendorTaxId": "issuer_rfc",
    "CustomerName": "receiver_name",
    "CustomerTaxId": "receiver_rfc",
    "InvoiceDate": "date",
    "SubTotal": "subtotal",
    "TotalTax": "tax",
    "InvoiceTotal": "total",
}
ITEM_MAP = {
    "Description": "description",
    "Quantity": "quantity",
    "Unit": "unit",
    "UnitPrice": "unit_value",
    "ProductCode": "identification",
    "Amount": "amount",
}


def field_value(field: dict[str, Any] | None) -> Any:
    """Valor de un campo del analisis: el importe de una moneda, el texto leido de una fecha (conserva la hora que
    valueDate pierde) o el valor tipado."""
    if not isinstance(field, dict):
        return None
    kind = field.get("type")
    if kind == "currency":
        return (field.get("valueCurrency") or {}).get("amount")
    if kind == "date":
        return field.get("content") or field.get("valueDate")
    for key in ("valueString", "valueNumber", "valueInteger", "valueDate", "valueTime"):
        if key in field:
            return field[key]
    return field.get("content")


def _currency(field: dict[str, Any] | None) -> str | None:
    return ((field or {}).get("valueCurrency") or {}).get("currencyCode")


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    """Contenido, paginas y campos (valor y confianza, con las claves de parse_cfdi) del resultado del analisis."""
    documents = result.get("documents") or []
    fields = (documents[0].get("fields") or {}) if documents else {}
    mapped = {}
    for name, key in FIELD_MAP.items():
        if name in fields:
            mapped[key] = {"value": field_value(fields[name]), "confidence": fields[name].get("confidence")}
    currency = _currency(fields.get("InvoiceTotal"))
    if currency:
        mapped["currency"] = {"value": currency, "confidence": fields["InvoiceTotal"].get("confidence")}
    items = []
    for entry in (fields.get("Items") or {}).get("valueArray") or []:
        values = (entry or {}).get("valueObject") or {}
        items.append({key: field_value(values.get(name)) for name, key in ITEM_MAP.items()})
    return {
        "content": result.get("content") or "",
        "content_format": result.get("contentFormat"),
        "pages": len(result.get("pages") or []),
        "doc_type": documents[0].get("docType") if documents else None,
        "doc_confidence": documents[0].get("confidence") if documents else None,
        "fields": mapped,
        "items": items,
    }


class AzureDocumentIntelligenceAnalyzer(DocumentAnalyzer):
    reads_all_pdfs = True
    source = SOURCE
    provider = PROVIDER

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.transport, self.sleep, self.clock = transport, sleep, clock

    @property
    def model(self) -> str:
        return settings.azure_document_intelligence_model

    @property
    def api_version(self) -> str:
        return settings.azure_document_intelligence_api_version

    def _ready(self) -> bool:
        return bool(
            settings.azure_document_intelligence_endpoint
            and settings.azure_document_intelligence_key.get_secret_value()
        )

    def ensure_configured(self) -> None:
        if not self._ready():
            raise AnalyzerUnavailable(f"{SERVICE} no esta configurado", NOT_CONFIGURED)

    def _client(self) -> httpx.Client:
        self.ensure_configured()
        key = settings.azure_document_intelligence_key.get_secret_value()
        return client(self.transport, {"Ocp-Apim-Subscription-Key": key})

    def _url(self, path: str) -> str:
        return f"{settings.azure_document_intelligence_endpoint}/documentintelligence/{path}"

    def evidence(self) -> dict[str, Any]:
        return {"service": PROVIDER, "model": self.model, "api_version": self.api_version}

    def health_check(self) -> dict[str, Any]:
        status = {"available": False, **self.evidence(), "provider": PROVIDER}
        started = self.clock()
        try:
            with self._client() as http:
                send(
                    http,
                    "GET",
                    self._url("info"),
                    Deadline(HEALTH_TIMEOUT, self.clock),
                    SERVICE,
                    params={"api-version": self.api_version},
                )
        except AnalyzerUnavailable as exc:
            status["reason"] = exc.reason
        else:
            status["available"] = True
        status["duration_ms"] = ms(self.clock() - started)
        return status

    def _poll(self, http: httpx.Client, url: str, deadline: Deadline, wait: float) -> dict[str, Any]:
        while True:
            deadline.check(SERVICE)
            self.sleep(min(min(max(wait, 0.25), MAX_POLL), max(deadline.remaining(), 0)))
            response = send(http, "GET", url, deadline, SERVICE)
            body = json_body(response, SERVICE)
            state = body.get("status")
            if state == "succeeded":
                result = body.get("analyzeResult")
                if not isinstance(result, dict):
                    raise AnalyzerUnavailable(f"{SERVICE}: resultado sin analyzeResult", INVALID_RESPONSE)
                return result
            if state in ("failed", "canceled"):
                code = (body.get("error") or {}).get("code") or state
                raise AnalyzerUnavailable(f"{SERVICE}: el analisis termino en {code}", FAILED)
            if state not in ("notStarted", "running"):
                raise AnalyzerUnavailable(f"{SERVICE}: estado desconocido", INVALID_RESPONSE)
            wait = _retry_after(response.headers.get("Retry-After"))

    def analyze_document(self, path: Path) -> dict[str, Any]:
        """OCR, layout y campos del modelo configurado. Lanza AnalyzerUnavailable si no esta configurado, si falla o
        si no termina dentro del plazo."""
        started = self.clock()
        deadline = Deadline(settings.azure_document_intelligence_timeout, self.clock)
        try:
            content = Path(path).read_bytes()
            with self._client() as http:
                response = send(
                    http,
                    "POST",
                    self._url(f"documentModels/{self.model}:analyze"),
                    deadline,
                    SERVICE,
                    params={"api-version": self.api_version, "outputContentFormat": "markdown"},
                    headers={"Content-Type": "application/pdf"},
                    content=content,
                )
                operation = response.headers.get("Operation-Location")
                if response.status_code != 202 or not operation:
                    raise AnalyzerUnavailable(f"{SERVICE}: no devolvio la operacion", INVALID_RESPONSE)
                if httpx.URL(operation).host != httpx.URL(settings.azure_document_intelligence_endpoint).host:
                    # La llave solo viaja al endpoint configurado.
                    raise AnalyzerUnavailable(f"{SERVICE}: operacion en otro host", INVALID_RESPONSE)
                wait = _retry_after(response.headers.get("Retry-After"))
                result = self._poll(http, operation, deadline, wait)
        except AnalyzerUnavailable as exc:
            log_call(
                "ai.document_intelligence", PROVIDER, started, "error", self.clock, reason=exc.reason, model=self.model
            )
            raise
        summary = summarize(result)
        duration = log_call(
            "ai.document_intelligence", PROVIDER, started, "ok", self.clock, model=self.model, pages=summary["pages"]
        )
        return {"status": "PROCESSED", **self.evidence(), "provider": PROVIDER, "duration_ms": duration, **summary}

    def read_invoice(self, path: Path) -> InvoiceReading:
        analysis = self.analyze_document(path)
        data, evidence = reading_from_analysis(analysis)
        return InvoiceReading(data, SOURCE, evidence)

    def extract_invoice(self, path: Path) -> dict[str, Any]:
        return self.read_invoice(path).data


def _retry_after(value: str | None) -> float:
    try:
        return float(value) if value else DEFAULT_POLL
    except ValueError:
        return DEFAULT_POLL


def step_evidence(analysis: dict[str, Any]) -> dict[str, Any]:
    keys = ("service", "model", "api_version", "duration_ms", "pages", "doc_type", "doc_confidence", "content_format")
    return {**{key: analysis.get(key) for key in keys}, "content_chars": len(analysis.get("content") or "")}


def field_confidence(analysis: dict[str, Any]) -> dict[str, float]:
    return {
        key: round(field["confidence"], 3)
        for key, field in analysis["fields"].items()
        if isinstance(field.get("confidence"), int | float)
    }


def reading_from_analysis(analysis: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Datos de Document Intelligence solo: los campos del modelo y, donde faltan, el parser sobre el texto OCR."""
    from app.services.invoice_extraction_service import parse_printed_cfdi  # evita el import circular

    content = analysis["content"]
    raw = {key: field["value"] for key, field in analysis["fields"].items()}
    raw["concepts"] = analysis["items"]
    data = normalize.invoice(raw)
    parsed = parse_printed_cfdi(content)
    filled = []
    for key, value in parsed.items():
        empty = data.get(key) in (None, []) or (key == "concepts" and not data["concepts"])
        if empty and value not in (None, []):
            data[key] = value
            filled.append(key)
    if not data["concepts"]:
        data["concepts"] = parsed["concepts"]
    ungrounded = normalize.ground(data, content)
    normalize.finish(data)
    evidence = {
        "pipeline": "document_intelligence",
        "steps": [step_evidence(analysis)],
        "confidence": field_confidence(analysis),
        "from_ocr_text": filled,
        "ungrounded": ungrounded,
    }
    return data, evidence
