"""Cadena de la prueba de concepto: Document Intelligence (OCR, layout y campos con su confianza), luego OpenAI
(estructura el contenido en las claves de parse_cfdi) y al final la normalizacion deterministica.

La confianza por campo es la del modelo de facturas de Document Intelligence; `agreement` dice si su valor coincide
con el final. La IA solo extrae: el motor de validacion decide la prevalidacion y una persona decide.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.services.ai import normalize
from app.services.ai.base import AnalyzerUnavailable, DocumentAnalyzer, InvoiceReading
from app.services.ai.document_intelligence import (
    AzureDocumentIntelligenceAnalyzer,
    field_confidence,
    step_evidence,
)
from app.services.ai.http import ms
from app.services.ai.openai_analyzer import OpenAIInvoiceAnalyzer

PIPELINE = "document_intelligence_openai"
SOURCE = "ai_ocr"


def agreement(analysis: dict[str, Any], data: dict[str, Any]) -> dict[str, bool]:
    """Por cada campo que leyo el modelo de facturas, si coincide con el valor final (ya normalizado)."""
    checks = {}
    reference = normalize.invoice({key: field["value"] for key, field in analysis["fields"].items()})
    for key in analysis["fields"]:
        if reference.get(key) is not None:
            final = data.get(key)
            same = final == reference[key] or (key == "date" and str(final or "")[:10] == reference[key][:10])
            checks[key] = same
    return checks


class DocumentIntelligenceOpenAIAnalyzer(DocumentAnalyzer):
    reads_all_pdfs = True
    source = SOURCE
    provider = PIPELINE

    def __init__(
        self,
        ocr: AzureDocumentIntelligenceAnalyzer | None = None,
        llm: OpenAIInvoiceAnalyzer | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.ocr = ocr or AzureDocumentIntelligenceAnalyzer()
        self.llm = llm or OpenAIInvoiceAnalyzer()
        self.clock = clock

    def health_check(self) -> dict[str, Any]:
        ocr, llm = self.ocr.health_check(), self.llm.health_check()
        return {"available": ocr["available"] and llm["available"], "provider": PIPELINE, "services": [ocr, llm]}

    def _ensure_configured(self) -> None:
        # Antes de gastar la llamada de OCR: sin OpenAI configurado la cadena no puede terminar.
        self.llm.ensure_configured()
        self.ocr.ensure_configured()

    def analyze_document(self, path: Path) -> dict[str, Any]:
        self._ensure_configured()
        analysis = self.ocr.analyze_document(path)
        raw, step = self.llm.structure(analysis["content"])
        return {"status": "PROCESSED", "provider": PIPELINE, "ocr": analysis, "llm": step, "data": raw}

    def read_invoice(self, path: Path) -> InvoiceReading:
        started = self.clock()
        self._ensure_configured()
        analysis = self.ocr.analyze_document(path)
        if not analysis["content"].strip():
            raise AnalyzerUnavailable("Azure Document Intelligence no encontro texto en el PDF", "no_text")
        raw, step = self.llm.structure(analysis["content"])
        data = normalize.invoice(raw)
        ungrounded = normalize.ground(data, analysis["content"])
        normalize.finish(data)
        evidence = {
            "pipeline": PIPELINE,
            "steps": [step_evidence(analysis), step],
            "confidence": field_confidence(analysis),
            "agreement": agreement(analysis, data),
            "ungrounded": ungrounded,
            "duration_ms": ms(self.clock() - started),
        }
        return InvoiceReading(data, SOURCE, evidence)

    def extract_invoice(self, path: Path) -> dict[str, Any]:
        return self.read_invoice(path).data
