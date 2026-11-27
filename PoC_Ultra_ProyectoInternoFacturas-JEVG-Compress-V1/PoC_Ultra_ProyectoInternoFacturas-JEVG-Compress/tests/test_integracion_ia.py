"""Integracion real con Azure Document Intelligence y OpenAI (Azure OpenAI o la API de OpenAI) con la factura 3668.

Sale a la red y cuesta: esta marcada `integration`, la suite normal la excluye (addopts) y se salta sin llaves.

    python -m pytest -m integration --no-cov -s tests/test_integracion_ia.py

Usa las llaves del .env (nunca las imprime) y mide la latencia de cada servicio y del registro completo.
"""

from __future__ import annotations

import html
import time
from decimal import Decimal

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.core.constants import InvoiceStatus
from app.services import invoice_extraction_service as extraction
from app.services.ai.document_intelligence import AzureDocumentIntelligenceAnalyzer
from app.services.ai.openai_analyzer import OpenAIInvoiceAnalyzer, target
from app.services.ai.pipeline import DocumentIntelligenceOpenAIAnalyzer
from scripts.rasterize_pdf import rasterize
from tests.ai_fakes import EXPECTED_3668, PDF_3668
from tests.cfdi import register, reload, results, submit, upload
from tests.conftest import invoice_by_number, login
from tests.test_set_factura_3668 import PROVEEDORA, factura_3668_libre, orden  # noqa: F401 - fixture

VERCEL_LIMIT = 60

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (
            settings.azure_document_intelligence_endpoint
            and settings.azure_document_intelligence_key.get_secret_value()
            and target() is not None
        ),
        reason="sin llaves de Azure Document Intelligence y OpenAI en el .env",
    ),
]


@pytest.fixture(scope="module")
def scanned(tmp_path_factory):
    return rasterize(PDF_3668, tmp_path_factory.mktemp("ia-real") / "CFDI-3668-escaneado.pdf")


@pytest.fixture()
def real_ai(monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "document_ai_provider", "document_intelligence_openai")


def check(data):
    for key, value in EXPECTED_3668.items():
        assert data[key] == value, key
    assert data["date"].startswith("2026-01-03")
    assert any("OC/25704872" in (c["description"] or "") for c in data["concepts"])


def test_servicios_responden():
    assert AzureDocumentIntelligenceAnalyzer().health_check()["available"] is True
    assert OpenAIInvoiceAnalyzer().health_check()["available"] is True


@pytest.mark.parametrize("version", ["texto", "escaneado"])
def test_cadena_real_lee_la_3668(version, scanned):
    pdf = PDF_3668 if version == "texto" else scanned
    started = time.monotonic()
    reading = DocumentIntelligenceOpenAIAnalyzer().read_invoice(pdf)
    elapsed = time.monotonic() - started
    check(reading.data)
    ocr, llm = reading.evidence["steps"]
    print(
        f"\n[{version}] Document Intelligence {ocr['duration_ms']} ms · OpenAI {llm['duration_ms']} ms · "
        f"cadena {reading.evidence['duration_ms']} ms"
    )
    assert elapsed < VERCEL_LIMIT / 2


@pytest.mark.usefixtures("real_ai", "restore_validation_rules", "factura_3668_libre")
def test_registro_real_de_la_3668_escaneada_y_envio(client, scanned):
    login(client, PROVEEDORA)
    started = time.monotonic()
    response = register(client, scanned.read_bytes(), pdf_name=scanned.name)
    elapsed = time.monotonic() - started
    print(f"\n[registro] POST /invoices/new {elapsed * 1000:.0f} ms")
    assert response.status_code == 303 and elapsed < VERCEL_LIMIT
    invoice = invoice_by_number("3668")
    assert (invoice.uuid, invoice.total, invoice.purchase_order_number) == (
        EXPECTED_3668["uuid"],
        Decimal("4128.50"),
        "25704872",
    )
    review = html.unescape(client.get(f"/invoices/{invoice.id}/data").text)
    assert "Datos tomados de: <strong>OCR + IA (Azure Document Intelligence + OpenAI)</strong>" in review
    vobo = (PDF_3668.parent / "VoBo-3668-v2-corregido.pdf").read_bytes()
    assert upload(client, invoice, "APPROVAL", "VoBo-3668-v2-corregido.pdf", vobo, "data").status_code == 303
    assert submit(client, invoice).status_code == 303
    assert [code for code, row in results(invoice).items() if row.status == "FAIL"] == []
    sent = reload(invoice)
    assert sent.status == InvoiceStatus.UNDER_REVIEW and sent.purchase_order_id == orden().id


@pytest.mark.usefixtures("real_ai")
def test_llave_invalida_real_vuelve_al_parser(monkeypatch):
    monkeypatch.setattr(settings, "azure_document_intelligence_key", SecretStr("llave-invalida-" + "0" * 20))
    started = time.monotonic()
    result = extraction.extract(PDF_3668, None)
    print(f"\n[llave invalida] retroceso en {(time.monotonic() - started) * 1000:.0f} ms")
    assert result.source == extraction.SOURCE_PDF_TEXT
    assert result.pdf_analysis["ai"] | {"duration_ms": 0} == {
        "provider": "document_intelligence_openai",
        "outcome": "error",
        "reason": "auth",
        "duration_ms": 0,
    }


@pytest.mark.usefixtures("real_ai")
def test_endpoint_invalido_real_vuelve_al_parser(monkeypatch):
    monkeypatch.setattr(settings, "azure_openai_deployment", "deployment-que-no-existe")
    result = extraction.extract(PDF_3668, None)
    assert result.source == extraction.SOURCE_PDF_TEXT and result.pdf_analysis["ai"]["reason"] == "not_found"
