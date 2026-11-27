"""Pantalla "Consumo de IA" y registro de cada lectura con IA (tabla ai_usage), con los servicios simulados."""

from __future__ import annotations

import html
import logging
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import AiUsage
from app.services import ai_usage_service as ai_usage
from app.services import invoice_extraction_service as extraction
from app.services.ai import document_intelligence, openai_analyzer
from tests.ai_fakes import DI_KEY, OPENAI_KEY, PDF_3668, FakeAI, configure
from tests.conftest import csrf, login


@pytest.fixture(autouse=True)
def empty_usage():
    with SessionLocal() as db:
        db.execute(delete(AiUsage))
        db.commit()
    yield


def rows() -> list[AiUsage]:
    with SessionLocal() as db:
        return list(db.scalars(select(AiUsage).order_by(AiUsage.id)))


def read_with(monkeypatch, **changes) -> FakeAI:
    configure(monkeypatch)
    ai = FakeAI(**changes)
    monkeypatch.setattr(extraction, "get_document_analyzer", ai.pipeline)
    extraction.read_pdf(PDF_3668)
    return ai


def test_cada_lectura_exitosa_queda_registrada(monkeypatch):
    read_with(monkeypatch)
    (row,) = rows()
    assert (row.provider, row.outcome, row.reason, row.has_text, row.source) == (
        "document_intelligence_openai",
        "ok",
        None,
        True,
        extraction.SOURCE_AI,
    )
    assert (row.ocr_model, row.ocr_pages, row.llm_service, row.llm_model) == (
        "prebuilt-invoice",
        1,
        "azure_openai",
        "gpt-prueba",
    )
    assert (row.input_tokens, row.output_tokens, row.discrepancies) == (1900, 300, 0)
    assert row.duration_ms >= 0 and row.ocr_duration_ms is not None and row.llm_duration_ms is not None


def test_si_openai_falla_el_ocr_consumido_cuenta(monkeypatch):
    read_with(monkeypatch, openai_status=429)
    (row,) = rows()
    assert (row.outcome, row.reason, row.source, row.ocr_pages, row.llm_model) == (
        "error",
        "quota",
        extraction.SOURCE_PDF_TEXT,
        1,
        None,
    )


def test_si_document_intelligence_falla_no_hay_paginas(monkeypatch):
    read_with(monkeypatch, di_submit_status=401)
    (row,) = rows()
    assert (row.outcome, row.reason, row.ocr_pages, row.input_tokens) == ("error", "auth", None, None)


def test_lectura_incompleta_y_error_inesperado(monkeypatch):
    read_with(monkeypatch, invoice={"concepts": []})
    assert rows()[0].outcome == "incomplete"

    class Broken(FakeAI().pipeline().__class__):
        def read_invoice(self, path):
            raise KeyError("x")

    monkeypatch.setattr(extraction, "get_document_analyzer", Broken)
    extraction.read_pdf(PDF_3668)
    assert (rows()[1].outcome, rows()[1].reason) == ("error", "error")


def test_sin_ia_no_se_registra_consumo(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(settings, "ai_enabled", False)
    extraction.read_pdf(PDF_3668)
    assert rows() == []


def test_registrar_el_consumo_nunca_impide_leer(monkeypatch, caplog):
    def broken_session():
        raise RuntimeError("sin base")

    monkeypatch.setattr(ai_usage, "SessionLocal", broken_session)
    with caplog.at_level(logging.WARNING):
        read_with(monkeypatch)
    assert any(getattr(r, "event", None) == "ai.usage_not_recorded" for r in caplog.records)


def test_resumen_y_costo_estimado(monkeypatch):
    for _ in range(2):
        read_with(monkeypatch)
    read_with(monkeypatch, di_submit_status=401)
    with SessionLocal() as db:
        total = ai_usage.summary(db)
        days = ai_usage.daily(db)
    assert (total.readings, total.ok, total.failed, total.pages, total.input_tokens, total.output_tokens) == (
        3,
        2,
        1,
        2,
        3800,
        600,
    )
    assert total.tokens == 4400 and total.cost is None
    assert len(days) == 1 and days[0][1].readings == 3
    monkeypatch.setattr(settings, "ai_price_ocr_1k_pages_usd", Decimal("10"))
    monkeypatch.setattr(settings, "ai_price_input_1m_tokens_usd", Decimal("0.25"))
    monkeypatch.setattr(settings, "ai_price_output_1m_tokens_usd", None)
    # 2 paginas a 10 USD por mil + 3800 tokens de entrada a 0.25 USD por millon.
    assert total.cost == Decimal("0.0210")


def test_precio_vacio_en_el_env_es_none():
    assert type(settings).optional_price("  ") is None and type(settings).optional_price("1.5") == "1.5"


def test_pantalla_de_consumo(client, monkeypatch):
    read_with(monkeypatch)
    read_with(monkeypatch, openai_status=401)
    login(client, "admin@poc.local")
    page = html.unescape(client.get("/admin/ai-usage").text)
    assert "<h1>Consumo de IA</h1>" in page and 'href="/admin/ai-usage"' in page
    assert 'id="ai-total"' in page and "<strong>2</strong>" in page and "1 leídas · 1 sin datos" in page
    assert "Llave inválida" in page and "Document Intelligence + OpenAI" in page
    assert "1,900 / 300 tokens" in page and "prebuilt-invoice" in page and "gpt-prueba" in page
    assert "AI_PRICE_OCR_1K_PAGES_USD" in page  # sin precios, la pista para configurarlos
    assert "Definida" in page and DI_KEY not in page and OPENAI_KEY not in page
    monkeypatch.setattr(settings, "ai_price_ocr_1k_pages_usd", Decimal("10"))
    assert "US$ 0.0200" in client.get("/admin/ai-usage").text


def test_pantalla_sin_lecturas(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", False)
    login(client, "admin@poc.local")
    page = html.unescape(client.get("/admin/ai-usage").text)
    assert "Aún no hay lecturas con IA" in page and "No (el portal lee el PDF sin IA)" in page


@pytest.mark.parametrize("email", ["pmo@poc.local", "proveedor1@poc.local"])
def test_solo_el_administrador_ve_el_consumo(client, email):
    login(client, email)
    assert client.get("/admin/ai-usage", follow_redirects=False).status_code in (302, 303, 403)


def test_probar_conexion(client, monkeypatch):
    configure(monkeypatch)
    good, bad = FakeAI(), FakeAI(openai_status=401)
    monkeypatch.setattr(document_intelligence, "AzureDocumentIntelligenceAnalyzer", lambda: good.ocr())
    monkeypatch.setattr(openai_analyzer, "OpenAIInvoiceAnalyzer", lambda: bad.llm())
    login(client, "admin@poc.local")
    token = csrf(client, "/admin/ai-usage")
    page = html.unescape(client.post("/admin/ai-usage/check", data={"csrf_token": token}).text)
    assert 'id="ai-checks"' in page and "Responde" in page and "No responde: Llave inválida" in page
    assert [r.method for r in good.requests] == ["GET"] and len(bad.requests) == 1
    assert client.post("/admin/ai-usage/check", data={}).status_code in (400, 403)


def test_probar_conexion_sin_configurar(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(settings, "azure_document_intelligence_endpoint", "")
    monkeypatch.setattr(settings, "azure_openai_deployment", "")
    results = ai_usage.check_services()
    assert [(r["label"], r["available"], r["reason_label"]) for r in results] == [
        ("Document Intelligence", False, "Sin configurar"),
        ("OpenAI", False, "Sin configurar"),
    ]
