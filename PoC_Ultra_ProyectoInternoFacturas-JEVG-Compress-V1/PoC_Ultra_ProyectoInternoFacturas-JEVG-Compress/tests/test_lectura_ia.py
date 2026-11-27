"""Lectura de la factura con IA: Azure Document Intelligence (OCR) y OpenAI (estructura), simulados sin red.

Cubre el mapeo de campos, los null, la normalizacion, la comparacion con el parser deterministico, cada falla con su
retroceso al flujo sin IA y los tiempos agotados. La prueba contra los servicios reales esta en
test_integracion_ia.py (marcada `integration`, se salta sin llaves).
"""

from __future__ import annotations

import html
import json
import logging
from decimal import Decimal

import fitz
import httpx
import pytest

from app.core.config import settings
from app.core.constants import InvoiceStatus
from app.core.errors import BusinessRuleError
from app.services import invoice_extraction_service as extraction
from app.services.ai import PROVIDERS, get_document_analyzer, normalize
from app.services.ai.base import (
    AUTH,
    FAILED,
    INVALID_RESPONSE,
    NETWORK,
    NO_TEXT,
    NOT_CONFIGURED,
    NOT_FOUND,
    QUOTA,
    SERVICE,
    TIMEOUT,
    AnalyzerUnavailable,
)
from app.services.ai.content_understanding import AzureContentUnderstandingAnalyzer
from app.services.ai.document_intelligence import AzureDocumentIntelligenceAnalyzer, field_value, summarize
from app.services.ai.http import Deadline, reason_for_status
from app.services.ai.mock_analyzer import LocalMockAnalyzer
from app.services.ai.openai_analyzer import INVOICE_SCHEMA, OpenAIInvoiceAnalyzer, output_text, parse_output
from app.services.ai.pipeline import DocumentIntelligenceOpenAIAnalyzer
from app.services.xml_service import parse_cfdi
from scripts.rasterize_pdf import rasterize
from tests.ai_fakes import (
    DI_KEY,
    EXPECTED_3668,
    OPENAI_HOST,
    OPENAI_KEY,
    PDF_3668,
    FakeAI,
    configure,
    di_result,
    responses_body,
)
from tests.cfdi import EXAMPLE_XML, register, reload, results, submit, upload
from tests.conftest import invoice_by_number, login
from tests.test_set_factura_3668 import PROVEEDORA, factura_3668_libre, orden  # noqa: F401 - fixture


class Clock:
    """Reloj controlado: cada lectura avanza `step` segundos (el plazo se agota sin esperar de verdad)."""

    def __init__(self, step: float = 0.0):
        self.now, self.step = 0.0, step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


@pytest.fixture()
def fake(monkeypatch):
    configure(monkeypatch)
    ai = FakeAI()
    monkeypatch.setattr(extraction, "get_document_analyzer", ai.pipeline)
    return ai


@pytest.fixture(scope="module")
def scanned_3668(tmp_path_factory):
    return rasterize(PDF_3668, tmp_path_factory.mktemp("ia") / "3668-escaneado.pdf")


def assert_3668(data):
    for key, value in EXPECTED_3668.items():
        assert data[key] == value, key
    assert "OC/25704872" in data["concepts"][0]["description"]


# --- Normalizacion deterministica ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("$ 3,559.05", Decimal("3559.05")),
        ("4128.5", Decimal("4128.5")),
        (12, Decimal("12")),
        ("", None),
        (None, None),
        ("tres", None),
        (True, None),
        ("NaN", None),
    ],
)
def test_importes_como_decimal(value, expected):
    assert normalize.amount(value) == expected


def test_rfc_uuid_y_claves_del_sat():
    assert normalize.rfc(" gohs-600317-45a ") == "GOHS60031745A"
    assert normalize.rfc("GOHS6003174") is None and normalize.rfc(None) is None
    assert normalize.uuid("a328f91a-dddd-4624-89ac-877819f5b540") == "A328F91A-DDDD-4624-89AC-877819F5B540"
    assert normalize.uuid("A328F91A-DDDD") is None and normalize.uuid("") is None
    assert normalize.code("99 - Por definir", r"\d{2}") == "99"
    assert normalize.code("PPD - Pago en parcialidades", "PUE|PPD") == "PPD"
    assert normalize.code("G03 - Gastos en general.", r"[A-Z]{1,2}\d{2}") == "G03"
    assert normalize.code("MXN - Peso Mexicano", "[A-Z]{3}") == "MXN"
    assert normalize.code("PPDX", "PUE|PPD") is None and normalize.code(None, r"\d") is None
    assert normalize.rate("0.16") == "0.160000" and normalize.rate("16") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-01-03T14:24:46", "2026-01-03T14:24:46"),
        ("2026-01-03 14:24:46", "2026-01-03T14:24:46"),
        ("2026-01-03T14:24:46-06:00", "2026-01-03T14:24:46"),
        ("2026-01-03", "2026-01-03"),
        ("03/01/2026", None),
        (None, None),
    ],
)
def test_fecha_de_emision_iso(value, expected):
    assert normalize.issued_at(value) == expected


def test_normaliza_el_json_del_modelo_con_los_tipos_de_parse_cfdi():
    raw = json.loads(json.dumps(INVOICE := {**json.loads(json.dumps(FakeAI().invoice))}))
    raw.update({"tax": None, "total": "$ 4,128.50", "currency": "mxn", "payment_method": "ppd - pago"})
    raw["concepts"][0]["taxes"][0].update({"tax": "IVA", "kind": "traslados", "rate": "0.16"})
    raw["concepts"].append({key: None for key in INVOICE["concepts"][0]} | {"taxes": []})  # concepto vacio
    data = normalize.finish(normalize.invoice(raw))
    assert data["total"] == Decimal("4128.50") and data["currency"] == "MXN" and data["payment_method"] == "PPD"
    # Sin el IVA del documento, como parse_cfdi: la suma de los traslados de los conceptos.
    assert data["tax"] == Decimal("569.45")
    assert data["concepts"][0]["taxes"] == [
        {"kind": "Traslado", "tax": "002", "rate": "0.160000", "base": Decimal("3559.05"), "amount": Decimal("569.45")}
    ]
    assert len(data["concepts"]) == 1 and set(data) == set(INVOICE)


def test_los_null_quedan_en_none_y_no_se_inventan():
    raw = {key: None for key in INVOICE_SCHEMA["properties"]} | {"concepts": [], "folio": "3668"}
    data = normalize.finish(normalize.invoice(raw))
    assert data["uuid"] is None and data["issuer_rfc"] is None and data["total"] is None
    assert data["tax"] == Decimal("0") and data["concepts"] == []
    assert not extraction.is_complete(data)
    assert normalize.tax_line("no es un objeto") is None and normalize.concept(None) is None
    assert normalize.tax_line({"kind": "X"}) is None


def test_lo_que_no_aparece_en_el_documento_se_deja_vacio():
    data = normalize.finish(normalize.invoice(FakeAI().invoice))
    content = FakeAI().content.replace("A328F91A-DDDD-4624-89AC-877819F5B540", "").replace("4,128.50", "")
    assert normalize.ground(data, content) == ["uuid", "total"]
    assert data["uuid"] is None and data["total"] is None and data["issuer_rfc"] == "GOHS60031745A"


def test_esquema_estricto_con_las_claves_de_parse_cfdi():
    assert set(INVOICE_SCHEMA["required"]) == set(INVOICE_SCHEMA["properties"]) == set(parse_cfdi(EXAMPLE_XML))
    assert INVOICE_SCHEMA["additionalProperties"] is False
    concept = INVOICE_SCHEMA["properties"]["concepts"]["items"]
    assert set(concept["required"]) == set(concept["properties"]) and concept["additionalProperties"] is False


# --- Document Intelligence -------------------------------------------------------------------------------------------


def test_mapeo_de_los_campos_del_modelo_de_facturas():
    summary = summarize(di_result("contenido"))
    assert summary["fields"]["total"] == {"value": 4128.5, "confidence": 0.936}
    assert summary["fields"]["currency"]["value"] == "MXN"
    assert summary["fields"]["date"]["value"] == "2026-01-03T14:24:46"  # el texto leido conserva la hora
    assert summary["items"][0]["description"].endswith("(OC/25704872)") and summary["pages"] == 1
    assert field_value(None) is None and field_value({"type": "x", "content": "c"}) == "c"
    assert summarize({})["fields"] == {} and summarize({})["doc_type"] is None


def test_document_intelligence_envia_consulta_y_respeta_el_plazo(monkeypatch):
    configure(monkeypatch)
    ai = FakeAI(polls_before_ready=2)
    analysis = ai.ocr().analyze_document(PDF_3668)
    post, *polls = ai.calls("di.test")
    assert post.method == "POST" and post.url.path.endswith("/documentModels/prebuilt-invoice:analyze")
    assert post.url.params["api-version"] == "2024-11-30" and post.headers["Content-Type"] == "application/pdf"
    assert post.headers["Ocp-Apim-Subscription-Key"] == DI_KEY and post.content == PDF_3668.read_bytes()
    assert len(polls) == 3 and all(p.method == "GET" for p in polls)
    assert analysis["model"] == "prebuilt-invoice" and analysis["fields"]["subtotal"]["confidence"] == 0.941


def test_document_intelligence_solo_completa_con_el_texto_del_ocr(monkeypatch, scanned_3668):
    configure(monkeypatch, provider="document_intelligence")
    ai = FakeAI()
    reading = ai.ocr().read_invoice(scanned_3668)
    assert reading.source == extraction.SOURCE_OCR_DI
    assert_3668(reading.data)
    assert {"uuid", "issuer_rfc", "receiver_rfc"} <= set(reading.evidence["from_ocr_text"])
    assert reading.evidence["confidence"]["total"] == 0.936
    assert ai.ocr().extract_invoice(scanned_3668)["uuid"] == EXPECTED_3668["uuid"]


def test_document_intelligence_sin_conceptos_del_modelo_usa_los_del_texto(monkeypatch):
    configure(monkeypatch, provider="document_intelligence")
    ai = FakeAI()
    original = ai._di

    def without_items(request):
        response = original(request)
        if request.method == "GET" and response.status_code == 200 and b"succeeded" in response.content:
            body = response.json()
            del body["analyzeResult"]["documents"][0]["fields"]["Items"]
            return httpx.Response(200, json=body)
        return response

    monkeypatch.setattr(ai, "_di", without_items)
    reading = ai.ocr().read_invoice(PDF_3668)
    assert "OC/25704872" in reading.data["concepts"][0]["description"]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"di_submit_status": 401}, AUTH),
        ({"di_submit_status": 404}, NOT_FOUND),
        ({"di_submit_status": 429}, QUOTA),
        ({"di_submit_status": 500}, SERVICE),
        ({"di_submit_status": 400}, INVALID_RESPONSE),
        ({"di_submit_status": 200}, INVALID_RESPONSE),  # sin 202 ni Operation-Location
        ({"di_poll_status": 503}, SERVICE),
        ({"di_state": "failed"}, FAILED),
        ({"di_state": "desconocido"}, INVALID_RESPONSE),
        ({"di_error": httpx.ConnectError("sin red")}, NETWORK),
        ({"di_error": httpx.ReadTimeout("lento")}, TIMEOUT),
    ],
)
def test_fallas_de_document_intelligence(monkeypatch, changes, reason):
    configure(monkeypatch)
    ai = FakeAI(**changes)
    with pytest.raises(AnalyzerUnavailable) as error:
        ai.ocr().analyze_document(PDF_3668)
    assert error.value.reason == reason
    assert DI_KEY not in str(error.value)


def test_document_intelligence_resultado_sin_analyze_result(monkeypatch):
    configure(monkeypatch)
    ai = FakeAI()
    monkeypatch.setattr(
        ai,
        "_di",
        lambda request: httpx.Response(
            202 if request.method == "POST" else 200,
            headers={"Operation-Location": "https://di.test/op"} if request.method == "POST" else {},
            json={"status": "succeeded"} if request.method == "GET" else None,
        ),
    )
    with pytest.raises(AnalyzerUnavailable) as error:
        ai.ocr().analyze_document(PDF_3668)
    assert error.value.reason == INVALID_RESPONSE


def test_document_intelligence_no_envia_la_llave_a_otro_host(monkeypatch):
    configure(monkeypatch)
    ai = FakeAI()
    original = ai._di

    def elsewhere(request):
        if request.method == "POST":
            return httpx.Response(202, headers={"Operation-Location": "https://otro.test/op"})
        return original(request)  # pragma: no cover - no debe consultarse

    monkeypatch.setattr(ai, "_di", elsewhere)
    with pytest.raises(AnalyzerUnavailable) as error:
        ai.ocr().analyze_document(PDF_3668)
    assert error.value.reason == INVALID_RESPONSE and len(ai.requests) == 1


def test_document_intelligence_respuesta_que_no_es_json(monkeypatch):
    configure(monkeypatch)
    ai = FakeAI()
    original = ai._di
    monkeypatch.setattr(ai, "_di", lambda r: original(r) if r.method == "POST" else httpx.Response(200, text="<x>"))
    with pytest.raises(AnalyzerUnavailable) as error:
        ai.ocr().analyze_document(PDF_3668)
    assert error.value.reason == INVALID_RESPONSE


def test_document_intelligence_tiempo_agotado_mientras_analiza(monkeypatch):
    """El analisis nunca termina: el plazo se agota sin esperar de verdad (reloj controlado)."""
    configure(monkeypatch)
    monkeypatch.setattr(settings, "azure_document_intelligence_timeout", 5)
    ai = FakeAI(di_state="running")
    waits = []
    analyzer = AzureDocumentIntelligenceAnalyzer(transport=ai.transport, sleep=waits.append, clock=Clock(step=0.5))
    with pytest.raises(AnalyzerUnavailable) as error:
        analyzer.analyze_document(PDF_3668)
    assert error.value.reason == TIMEOUT
    assert waits and all(0 <= wait <= 5 for wait in waits)


def test_document_intelligence_sin_configurar(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(settings, "azure_document_intelligence_endpoint", "")
    analyzer = FakeAI().ocr()
    with pytest.raises(AnalyzerUnavailable) as error:
        analyzer.analyze_document(PDF_3668)
    assert error.value.reason == NOT_CONFIGURED
    assert analyzer.health_check() | {"duration_ms": 0} == {
        "available": False,
        "service": "azure_document_intelligence",
        "model": "prebuilt-invoice",
        "api_version": "2024-11-30",
        "provider": "azure_document_intelligence",
        "reason": NOT_CONFIGURED,
        "duration_ms": 0,
    }


def test_health_check_de_document_intelligence(monkeypatch):
    configure(monkeypatch)
    assert FakeAI().ocr().health_check()["available"] is True
    rejected = FakeAI(di_poll_status=401).ocr().health_check()
    assert (rejected["available"], rejected["reason"]) == (False, AUTH)


def test_reintento_y_motivos():
    from app.services.ai.document_intelligence import _retry_after

    assert _retry_after("2") == 2 and _retry_after("x") == 1.0 and _retry_after(None) == 1.0
    assert [reason_for_status(code) for code in (401, 403, 404, 429, 422, 502)] == [
        AUTH,
        AUTH,
        NOT_FOUND,
        QUOTA,
        INVALID_RESPONSE,
        SERVICE,
    ]
    deadline = Deadline(1, Clock(step=2))
    with pytest.raises(AnalyzerUnavailable) as error:
        deadline.check("X")
    assert error.value.reason == TIMEOUT


# --- OpenAI ----------------------------------------------------------------------------------------------------------


def test_openai_pide_salida_estructurada_con_el_deployment_configurado(monkeypatch):
    configure(monkeypatch)
    ai = FakeAI()
    raw, step = ai.llm().structure("contenido de la factura")
    (request,) = ai.calls(OPENAI_HOST)
    body = json.loads(request.content)
    assert request.url.path == "/openai/responses" and request.url.params["api-version"] == "2025-04-01-preview"
    assert request.headers["api-key"] == OPENAI_KEY and "authorization" not in request.headers
    assert body["model"] == "gpt-prueba" and body["store"] is False and body["reasoning"] == {"effort": "minimal"}
    assert body["text"]["format"]["type"] == "json_schema" and body["text"]["format"]["strict"] is True
    assert body["input"][0]["content"][0]["text"] == "contenido de la factura"
    assert raw["uuid"] == EXPECTED_3668["uuid"]
    assert step == {
        "service": "azure_openai",
        "deployment": "gpt-prueba",
        "api_version": "2025-04-01-preview",
        "duration_ms": step["duration_ms"],
        "input_tokens": 1900,
        "output_tokens": 300,
        "truncated": False,
    }


def test_openai_api_v1_de_azure_sin_version(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(settings, "azure_openai_api_version", "")
    monkeypatch.setattr(settings, "openai_reasoning_effort", "")
    ai = FakeAI()
    ai.llm().structure("x")
    (request,) = ai.calls(OPENAI_HOST)
    assert request.url.path == "/openai/v1/responses" and "api-version" not in request.url.params
    assert "reasoning" not in json.loads(request.content)


def test_api_de_openai_cuando_azure_no_esta_configurado(monkeypatch):
    configure(monkeypatch, azure=False)
    ai = FakeAI()
    analyzer = ai.llm()
    assert analyzer.provider == "openai"
    raw, step = analyzer.structure("x")
    (request,) = ai.calls(OPENAI_HOST)
    assert request.url.path == "/v1/responses" and request.headers["authorization"] == f"Bearer {OPENAI_KEY}"
    assert step["model"] == "gpt-prueba" and "deployment" not in step


def test_openai_solo_lee_la_capa_de_texto(monkeypatch, scanned_3668):
    configure(monkeypatch, provider="openai")
    ai = FakeAI()
    reading = ai.llm().read_invoice(PDF_3668)
    assert reading.source == extraction.SOURCE_AI_TEXT and reading.evidence["pipeline"] == "openai"
    assert_3668(reading.data)
    assert ai.llm().extract_invoice(PDF_3668)["folio"] == "3668"
    assert ai.llm().analyze_document(PDF_3668)["data"]["folio"] == "3668"
    with pytest.raises(AnalyzerUnavailable) as error:
        ai.llm().read_invoice(scanned_3668)
    assert error.value.reason == NO_TEXT


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (responses_body("no es json"), INVALID_RESPONSE),
        (responses_body(["lista"]), INVALID_RESPONSE),
        (responses_body({"uuid": "x"}), INVALID_RESPONSE),  # sin concepts: no sigue el esquema
        (
            responses_body({}, status="incomplete") | {"incomplete_details": {"reason": "max_output_tokens"}},
            INVALID_RESPONSE,
        ),
        ({"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]}, INVALID_RESPONSE),
        ({"status": "completed", "output": ["x", {"type": "message", "content": []}]}, INVALID_RESPONSE),
    ],
)
def test_respuestas_invalidas_de_openai(monkeypatch, body, reason):
    configure(monkeypatch)
    with pytest.raises(AnalyzerUnavailable) as error:
        FakeAI(openai_body=body).llm().structure("x")
    assert error.value.reason == reason


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"openai_status": 401}, AUTH),
        ({"openai_status": 404}, NOT_FOUND),
        ({"openai_status": 429}, QUOTA),
        ({"openai_status": 500}, SERVICE),
        ({"openai_error": httpx.ReadTimeout("lento")}, TIMEOUT),
        ({"openai_error": httpx.ConnectError("sin red")}, NETWORK),
    ],
)
def test_fallas_de_openai(monkeypatch, changes, reason):
    configure(monkeypatch)
    with pytest.raises(AnalyzerUnavailable) as error:
        FakeAI(**changes).llm().structure("x")
    assert error.value.reason == reason
    assert OPENAI_KEY not in str(error.value)


def test_openai_respuesta_que_no_es_json(monkeypatch):
    configure(monkeypatch)
    ai = FakeAI()
    monkeypatch.setattr(ai, "_openai", lambda request: httpx.Response(200, text="<html>"))
    with pytest.raises(AnalyzerUnavailable) as error:
        ai.llm().structure("x")
    assert error.value.reason == INVALID_RESPONSE
    monkeypatch.setattr(ai, "_openai", lambda request: httpx.Response(200, json=[1]))
    with pytest.raises(AnalyzerUnavailable):
        ai.llm().structure("x")


def test_openai_sin_configurar_y_health_check(monkeypatch):
    configure(monkeypatch)
    assert FakeAI().llm().health_check()["available"] is True
    rejected = FakeAI(openai_status=401).llm().health_check()
    assert (rejected["available"], rejected["reason"], rejected["deployment"]) == (False, AUTH, "gpt-prueba")
    monkeypatch.setattr(settings, "azure_openai_deployment", "")
    analyzer = FakeAI().llm()
    assert analyzer.health_check() == {"available": False, "provider": "openai", "reason": NOT_CONFIGURED}
    with pytest.raises(AnalyzerUnavailable) as error:
        analyzer.structure("x")
    assert error.value.reason == NOT_CONFIGURED


def test_salida_de_responses():
    assert output_text(responses_body({"a": 1})) == '{"a": 1}'
    assert parse_output('{"concepts": []}') == {"concepts": []}


# --- Cadena Document Intelligence + OpenAI --------------------------------------------------------------------------


def test_cadena_lee_la_factura_escaneada(monkeypatch, scanned_3668):
    configure(monkeypatch)
    ai = FakeAI()
    reading = ai.pipeline().read_invoice(scanned_3668)
    assert reading.source == extraction.SOURCE_AI
    assert_3668(reading.data)
    evidence = reading.evidence
    assert [step["service"] for step in evidence["steps"]] == ["azure_document_intelligence", "azure_openai"]
    assert evidence["steps"][1]["deployment"] == "gpt-prueba" and evidence["steps"][0]["model"] == "prebuilt-invoice"
    assert evidence["confidence"]["date"] == 0.414 and all(evidence["agreement"].values())
    assert evidence["ungrounded"] == [] and evidence["duration_ms"] >= 0
    # OpenAI recibe el texto del OCR, no el PDF.
    assert json.loads(ai.calls(OPENAI_HOST)[0].content)["input"][0]["content"][0]["text"] == ai.content


def test_cadena_analyze_document_y_health_check(monkeypatch):
    configure(monkeypatch)
    ai = FakeAI()
    analysis = ai.pipeline().analyze_document(PDF_3668)
    assert analysis["ocr"]["pages"] == 1 and analysis["data"]["folio"] == "3668"
    assert ai.pipeline().extract_invoice(PDF_3668)["folio"] == "3668"
    health = ai.pipeline().health_check()
    assert health["available"] is True and [s["available"] for s in health["services"]] == [True, True]


def test_cadena_sin_openai_no_gasta_el_ocr(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(settings, "azure_openai_api_key", type(settings.azure_openai_api_key)(""))
    ai = FakeAI()
    with pytest.raises(AnalyzerUnavailable) as error:
        ai.pipeline().read_invoice(PDF_3668)
    assert error.value.reason == NOT_CONFIGURED and ai.requests == []


def test_cadena_sin_texto_del_ocr(monkeypatch):
    configure(monkeypatch)
    with pytest.raises(AnalyzerUnavailable) as error:
        FakeAI(content="  ").pipeline().read_invoice(PDF_3668)
    assert error.value.reason == NO_TEXT


def test_desacuerdo_con_el_modelo_de_facturas(monkeypatch):
    configure(monkeypatch)
    ai = FakeAI()
    ai.invoice["subtotal"] = "3559.50"
    ai.content += "\n3559.50"
    reading = ai.pipeline().read_invoice(PDF_3668)
    assert reading.evidence["agreement"]["subtotal"] is False and reading.evidence["agreement"]["total"] is True


def test_seleccion_del_analizador(monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", False)
    assert isinstance(get_document_analyzer(), LocalMockAnalyzer)
    monkeypatch.setattr(settings, "ai_enabled", True)
    for provider, cls in PROVIDERS.items():
        monkeypatch.setattr(settings, "document_ai_provider", provider)
        assert type(get_document_analyzer()) is cls
    monkeypatch.setattr(settings, "document_ai_provider", "desconocido")
    assert isinstance(get_document_analyzer(), LocalMockAnalyzer)
    assert get_document_analyzer().reads_all_pdfs is False
    assert AzureContentUnderstandingAnalyzer.reads_all_pdfs is False


# --- Integracion al flujo de extraccion -----------------------------------------------------------------------------


def test_pdf_escaneado_se_registra_con_la_ia(fake, scanned_3668):
    result = extraction.extract(scanned_3668, None)
    assert result.source == extraction.SOURCE_AI and result.number == "3668"
    assert_3668(result.data)
    metadata = result.pdf_metadata()
    assert metadata["invoice"]["source"] == extraction.SOURCE_AI and metadata["invoice"]["total"] == "4128.50"
    evidence = metadata["ai"]
    assert evidence["outcome"] == "ok" and evidence["provider"] == "document_intelligence_openai"
    assert "compared_with" not in evidence  # sin texto no hay con que comparar
    stored = json.dumps(metadata)
    assert DI_KEY not in stored and OPENAI_KEY not in stored


def test_pdf_con_texto_se_compara_con_el_parser(fake):
    result = extraction.extract(PDF_3668, None)
    assert result.source == extraction.SOURCE_AI
    assert result.pdf_metadata()["ai"]["compared_with"] == extraction.SOURCE_PDF_TEXT
    assert result.pdf_metadata()["ai"]["discrepancies"] == []


def test_campos_que_no_coinciden_con_el_parser(fake):
    fake.invoice["concepts"][0]["description"] = "LTH TIPO L-31T-900 AR BATERIA (OC/25704827)"
    fake.invoice["payment_form"] = "03"
    fake.content += "\n03 OC/25704827"
    result = extraction.extract(PDF_3668, None)
    differences = {d["field"]: d for d in result.pdf_analysis["ai"]["discrepancies"]}
    assert set(differences) == {"payment_form", "purchase_order"}
    assert differences["purchase_order"] | {} == {
        "field": "purchase_order",
        "label": "Orden de compra",
        "ai": "25704827",
        "parser": "25704872",
    }
    assert differences["payment_form"]["ai"] == "03" and differences["payment_form"]["parser"] == "99"
    assert result.data["payment_form"] == "03"  # los datos son los de la IA; la revision senala la diferencia


def test_comparacion_de_importes_y_valores_vacios():
    parsed = {"total": Decimal("4128.50"), "series": "", "concepts": []}
    ai = {"total": Decimal("4128.5"), "series": None, "concepts": [], "uuid": "X"}
    differences = extraction.compare(ai, parsed)
    assert [d["field"] for d in differences] == ["uuid"] and differences[0]["parser"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"di_submit_status": 401},  # llave invalida
        {"di_submit_status": 404},  # endpoint o modelo inexistente
        {"di_submit_status": 429},  # cuota
        {"di_error": httpx.ReadTimeout("lento")},
        {"openai_status": 401},
        {"openai_status": 429},
        {"openai_error": httpx.ReadTimeout("lento")},
        {"openai_body": responses_body("no es json")},
        {"invoice": {"concepts": []} | {key: None for key in INVOICE_SCHEMA["properties"] if key != "concepts"}},
    ],
)
def test_si_la_ia_falla_el_pdf_con_texto_se_lee_como_hoy(monkeypatch, changes, scanned_3668, caplog):
    configure(monkeypatch)
    ai = FakeAI(**changes)
    monkeypatch.setattr(extraction, "get_document_analyzer", ai.pipeline)
    with caplog.at_level(logging.INFO):
        result = extraction.extract(PDF_3668, None)
    assert result.source == extraction.SOURCE_PDF_TEXT and result.number == "3668"
    assert_3668(result.data)
    assert result.pdf_metadata()["ai"]["outcome"] in ("error", "incomplete")
    (event,) = [r for r in caplog.records if getattr(r, "event", None) == "ai.invoice_read"]
    assert event.outcome == "fallback" and event.fallback == extraction.SOURCE_PDF_TEXT
    # Sin texto, como hoy: se pide el XML (422).
    ai.requests.clear()
    with pytest.raises(extraction.UnreadableInvoiceError) as error:
        extraction.extract(scanned_3668, None)
    assert error.value.status_code == 422


def test_un_defecto_del_analizador_no_impide_registrar(monkeypatch, caplog):
    class Broken(LocalMockAnalyzer):
        reads_all_pdfs = True

        def read_invoice(self, path):
            raise KeyError("campo")

    monkeypatch.setattr(extraction, "get_document_analyzer", Broken)
    with caplog.at_level(logging.INFO):
        result = extraction.extract(PDF_3668, None)
    assert result.source == extraction.SOURCE_PDF_TEXT
    (event,) = [r for r in caplog.records if getattr(r, "event", None) == "ai.invoice_read"]
    assert (event.reason, event.error_type, event.provider) == ("error", "KeyError", "Broken")


def test_el_xml_sigue_mandando_y_se_compara_el_uuid(fake, scanned_3668, tmp_path):
    xml = tmp_path / "factura.xml"
    xml.write_bytes(EXAMPLE_XML)
    result = extraction.extract(scanned_3668, xml)
    assert result.source == extraction.SOURCE_XML and result.pdf_source == extraction.SOURCE_AI
    fake.invoice["uuid"] = "B328F91A-DDDD-4624-89AC-877819F5B540"
    fake.content += "\nB328F91A-DDDD-4624-89AC-877819F5B540"
    with pytest.raises(BusinessRuleError) as error:
        extraction.extract(scanned_3668, xml)
    assert (error.value.status_code, error.value.message) == (409, extraction.MSG_MISMATCH)


def test_logs_sin_secretos_ni_datos_fiscales(fake, scanned_3668, caplog):
    with caplog.at_level(logging.DEBUG):
        extraction.extract(scanned_3668, None)
    events = {getattr(r, "event", None) for r in caplog.records}
    assert {"ai.document_intelligence", "ai.openai", "ai.invoice_read"} <= events
    dumped = json.dumps([r.__dict__ for r in caplog.records], default=str)
    for secret in (DI_KEY, OPENAI_KEY, "GOHS60031745A", "A328F91A", "4128.50", "INTERMODAL", "OC/25704872"):
        assert secret not in dumped, secret
    (event,) = [r for r in caplog.records if getattr(r, "event", None) == "ai.invoice_read"]
    assert event.outcome == "ok" and event.provider == "document_intelligence_openai" and event.duration_ms >= 0


def test_ia_desactivada_lee_como_hoy(monkeypatch, scanned_3668):
    configure(monkeypatch)
    monkeypatch.setattr(settings, "ai_enabled", False)
    result = extraction.extract(PDF_3668, None)
    assert result.source == extraction.SOURCE_PDF_TEXT and "ai" not in result.pdf_metadata()
    with pytest.raises(extraction.UnreadableInvoiceError):
        extraction.extract(scanned_3668, None)


def test_pdf_escaneado_en_blanco_con_ia(fake, tmp_path):
    document = fitz.open()
    document.new_page()
    blank = tmp_path / "blanco.pdf"
    document.save(blank)
    fake.content = ""
    with pytest.raises(extraction.UnreadableInvoiceError):
        extraction.extract(blank, None)


def test_etiquetas_de_las_fuentes_nuevas():
    assert extraction.SOURCE_LABELS[extraction.SOURCE_AI] == "OCR + IA (Azure Document Intelligence + OpenAI)"
    assert DocumentIntelligenceOpenAIAnalyzer.source == extraction.SOURCE_AI
    assert AzureDocumentIntelligenceAnalyzer.source == extraction.SOURCE_OCR_DI
    assert OpenAIInvoiceAnalyzer.source == extraction.SOURCE_AI_TEXT


# --- Flujo del portal (criterios de aceptacion con los servicios simulados) ------------------------------------------


def _register_3668(client, pdf: bytes, name: str):
    login(client, PROVEEDORA)
    response = register(client, pdf, pdf_name=name)
    return response, invoice_by_number("3668")


@pytest.mark.usefixtures("restore_validation_rules", "factura_3668_libre")
def test_registro_de_la_3668_escaneada_con_ia_y_envio(client, fake, scanned_3668):
    response, invoice = _register_3668(client, scanned_3668.read_bytes(), "CFDI-3668-escaneado.pdf")
    assert response.status_code == 303 and response.headers["location"] == f"/invoices/{invoice.id}/data"
    assert (invoice.uuid, invoice.currency, invoice.service_period) == (EXPECTED_3668["uuid"], "MXN", "01/2026")
    assert (invoice.subtotal, invoice.tax, invoice.total) == (Decimal("3559.05"), Decimal("569.45"), Decimal("4128.50"))
    assert invoice.purchase_order_number == "25704872"
    review = html.unescape(client.get(f"/invoices/{invoice.id}/data").text)
    assert "Datos tomados de: <strong>OCR + IA (Azure Document Intelligence + OpenAI)</strong>" in review
    assert 'id="ai-reading"' in review and "Confianza baja del OCR: Fecha (41 %)" in review
    assert 'id="ai-discrepancies"' not in review  # sin texto no hay con que comparar
    for rule in ("PRV-001", "XML-002", "XML-005"):
        assert f'class="data-check ok" data-rule="{rule}"' in review, rule
    vobo = (PDF_3668.parent / "VoBo-3668-v2-corregido.pdf").read_bytes()
    assert upload(client, invoice, "APPROVAL", "VoBo-3668-v2-corregido.pdf", vobo, "data").status_code == 303
    assert submit(client, invoice).status_code == 303
    stored = results(invoice)
    assert [code for code, row in stored.items() if row.status == "FAIL"] == []
    sent = reload(invoice)
    assert sent.status == InvoiceStatus.UNDER_REVIEW and sent.purchase_order_id == orden().id


@pytest.mark.usefixtures("factura_3668_libre")
def test_la_revision_senala_lo_que_no_coincide_con_el_texto(client, fake):
    fake.invoice["payment_form"] = "03"
    response, invoice = _register_3668(client, PDF_3668.read_bytes(), PDF_3668.name)
    assert response.status_code == 303
    review = html.unescape(client.get(f"/invoices/{invoice.id}/data").text)
    assert "no coinciden en 1 dato" in review
    assert '<tr data-field="payment_form"><td>Forma de pago</td><td>03</td><td>99</td></tr>' in review


@pytest.mark.usefixtures("factura_3668_libre")
def test_con_la_llave_invalida_el_registro_sigue_como_hoy(client, monkeypatch, scanned_3668, caplog):
    configure(monkeypatch)
    ai = FakeAI(di_submit_status=401)
    monkeypatch.setattr(extraction, "get_document_analyzer", ai.pipeline)
    with caplog.at_level(logging.INFO):
        response, invoice = _register_3668(client, PDF_3668.read_bytes(), PDF_3668.name)
    assert response.status_code == 303 and invoice.uuid == EXPECTED_3668["uuid"]
    review = html.unescape(client.get(f"/invoices/{invoice.id}/data").text)
    assert "Datos tomados de: <strong>Texto del PDF</strong>" in review and 'id="ai-fallback"' in review
    (event,) = [r for r in caplog.records if getattr(r, "event", None) == "ai.invoice_read"]
    assert (event.outcome, event.reason) == ("fallback", AUTH) and DI_KEY not in caplog.text
    # El escaneado, como hoy: 422 con el mensaje que pide el XML.
    login(client, PROVEEDORA)
    response = register(client, scanned_3668.read_bytes(), pdf_name="escaneado.pdf")
    assert response.status_code == 422 and extraction.MSG_UNREADABLE in html.unescape(response.text)
