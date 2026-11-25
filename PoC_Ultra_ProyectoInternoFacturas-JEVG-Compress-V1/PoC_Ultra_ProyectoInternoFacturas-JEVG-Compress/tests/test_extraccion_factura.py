"""Extraccion de los datos de la factura (HU-24, spec registro-factura-extraccion): XML ampliado, representacion
impresa del CFDI 4.0 y analizador documental. Sin base de datos."""

from decimal import Decimal
from pathlib import Path

import fitz
import pytest

from app.core.errors import BusinessRuleError
from app.services import invoice_extraction_service as extraction
from app.services.ai import AnalyzerUnavailable
from app.services.ai.mock_analyzer import LocalMockAnalyzer
from app.services.xml_service import parse_cfdi
from scripts import cfdi_demo
from tests.cfdi import DEMO, EXAMPLE_PDF, EXAMPLE_XML, example_cfdi, moral_cfdi, new_uuid, pdf_of, xml_of

WALKTHROUGH = Path(__file__).resolve().parents[1] / "data" / "pruebas-ferromex"
SET_3668 = WALKTHROUGH.parent / "pruebas-factura-3668" / "1-factura" / "CFDI-3668-GOHS60031745A.pdf"


def write(tmp_path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def printed(content: bytes) -> dict:
    with fitz.open(stream=content, filetype="pdf") as document:
        return extraction.parse_printed_cfdi("\n".join(page.get_text("text") for page in document))


# --- Representacion impresa de la factura 3668 ------------------------------------------------------------------------


def test_conceptos_de_la_factura_3668():
    data = printed(EXAMPLE_PDF)
    assert len(data["concepts"]) == 1
    concept = data["concepts"][0]
    assert concept["quantity"] == Decimal("1.00")
    assert (concept["unit_key"], concept["unit"]) == ("H87", "PZ")
    assert concept["identification"] == "L-31T-900"
    assert concept["description"] == "LTH TIPO L-31T-900 AR BATERIA (OC/25704872)"
    assert concept["unit_value"] == Decimal("3559.05")
    assert concept["tax_object"] == "02"
    assert concept["amount"] == Decimal("3559.05")
    assert concept["taxes"] == [
        {"kind": "Traslado", "tax": "002", "rate": "0.160000", "base": Decimal("3559.05"), "amount": Decimal("569.45")}
    ]


def test_emisor_y_receptor_de_la_factura_3668():
    data = printed(EXAMPLE_PDF)
    assert (data["issuer_rfc"], data["issuer_name"], data["issuer_regime"]) == (
        "GOHS60031745A",
        "SOCORRO PATRICIA GONZALEZ HERNANDEZ",
        "612",
    )
    receiver = (
        data["receiver_rfc"],
        data["receiver_name"],
        data["receiver_regime"],
        data["cfdi_use"],
        data["receiver_postal_code"],
    )
    assert receiver == ("IME010718PU3", "INTERMODAL MEXICO", "601", "G03", "11700")


def test_totales_y_datos_del_comprobante_3668(tmp_path):
    analysis, data, source = extraction.read_pdf(write(tmp_path, "factura.pdf", EXAMPLE_PDF))
    assert source == extraction.SOURCE_PDF_TEXT and analysis["page_count"] == 1
    assert (data["subtotal"], data["tax"], data["total"]) == (Decimal("3559.05"), Decimal("569.45"), Decimal("4128.50"))
    assert (data["currency"], data["payment_form"], data["payment_method"], data["voucher_type"]) == (
        "MXN",
        "99",
        "PPD",
        "I",
    )
    assert data["uuid"] == "A328F91A-DDDD-4624-89AC-877819F5B540"
    assert data["date"] == "2026-01-03T14:24:46"
    assert extraction.is_complete(data)
    assert extraction.invoice_number(data) == "3668" and extraction.service_period(data) == "01/2026"


def test_serie_y_folio_impresos():
    data = printed(pdf_of(moral_cfdi(folio="1234", series="B")))
    assert (data["series"], data["folio"]) == ("B", "1234")
    assert extraction.invoice_number(data) == "B-1234"


def test_varios_conceptos_con_sus_impuestos():
    base = cfdi_demo.DEMO_MORAL["concepts"][0]
    second = {**base, "description": "Soporte mensual (OC/45001001)", "unit_value": "500"}
    data = cfdi_demo.variant(cfdi_demo.DEMO_MORAL, uuid=new_uuid())
    data["concepts"].append(second)
    parsed = printed(pdf_of(data))
    assert [c["description"] for c in parsed["concepts"]] == [
        "08 Servicios desarrollo Power Automate (OC/45001001)",
        "Soporte mensual (OC/45001001)",
    ]
    assert [c["taxes"][0]["amount"] for c in parsed["concepts"]] == [Decimal("16000.00"), Decimal("80.00")]
    assert parsed["subtotal"] == Decimal("100500.00") and parsed["tax"] == Decimal("16080.00")
    # Una descripcion que empieza con un numero no se toma como identificacion.
    assert parsed["concepts"][0]["identification"] is None


def test_pdf_sin_datos_de_un_cfdi():
    with fitz.open(DEMO / "factura_demo.pdf") as document:
        data = extraction.parse_printed_cfdi(document[0].get_text("text"))
    assert not extraction.is_complete(data)
    assert data["concepts"] == [] and data["uuid"] is None


@pytest.mark.skipif(not WALKTHROUGH.is_dir(), reason="sin el recorrido manual")
@pytest.mark.parametrize("folder", ["3-factura-observaciones-autorizada", "4-factura-rechazada"])
def test_pdf_del_recorrido_manual(folder):
    """PDF impresos con Chromium por data/pruebas-ferromex/_generador: otra maqueta de la misma representacion."""
    pdf = next((WALKTHROUGH / folder).glob("CFDI-*.pdf"))
    xml = parse_cfdi(pdf.with_suffix(".xml"))
    data = printed(pdf.read_bytes())
    assert extraction.is_complete(data)
    for key in ("uuid", "issuer_rfc", "issuer_regime", "receiver_rfc", "receiver_postal_code", "cfdi_use", "currency"):
        assert data[key] == xml[key], key
    assert (data["subtotal"], data["total"]) == (xml["subtotal"], xml["total"])
    assert data["issuer_name"] == xml["issuer_name"] and data["receiver_name"] == xml["receiver_name"]
    assert [c["description"] for c in data["concepts"]] == [c["description"] for c in xml["concepts"]]
    assert extraction.invoice_number(data) == f"{xml['series']}-{xml['folio']}"


@pytest.mark.skipif(not SET_3668.is_file(), reason="sin el set de la factura 3668")
def test_maqueta_del_ejemplo_3668():
    """La factura 3668 con la maqueta del documento de negocio (data/pruebas-factura-3668): RFC sin etiqueta, datos del
    timbre junto al cliente, "02 - Sí objeto de impuesto." en el renglon y el detalle del concepto debajo. Del PDF
    salen los mismos datos que de su XML."""
    assert printed(SET_3668.read_bytes()) == parse_cfdi(EXAMPLE_XML)


def test_rfc_sin_etiqueta_no_es_el_del_pac():
    """Si los datos del timbre quedan antes del emisor, el RFC del proveedor de certificacion no se toma por el suyo."""
    data = extraction.parse_printed_cfdi(
        "\n".join(
            [
                "Factura 3668",
                "RFC PROVEEDOR DE CERTIFICACIÓN",
                "STA0903206B9",
                "SOCORRO PATRICIA GONZALEZ HERNANDEZ",
                "GOHS60031745A",
                "RÉGIMEN FISCAL: 612 - Personas Físicas con Actividades Empresariales y Profesionales",
                "CLIENTE",
                "INTERMODAL MEXICO",
                "IME010718PU3",
            ]
        )
    )
    assert (data["issuer_rfc"], data["issuer_name"], data["receiver_rfc"]) == (
        "GOHS60031745A",
        "SOCORRO PATRICIA GONZALEZ HERNANDEZ",
        "IME010718PU3",
    )


# --- XML ampliado -----------------------------------------------------------------------------------------------------


def test_datos_ampliados_del_xml():
    data = parse_cfdi(EXAMPLE_XML)
    assert (data["series"], data["folio"], data["issuer_regime"]) == (None, "3668", "612")
    concept = data["concepts"][0]
    assert (concept["unit_key"], concept["unit"], concept["identification"], concept["tax_object"]) == (
        "H87",
        "PZ",
        "L-31T-900",
        "02",
    )
    assert concept["taxes"][0] == {
        "kind": "Traslado",
        "tax": "002",
        "rate": "0.160000",
        "base": Decimal("3559.05"),
        "amount": Decimal("569.45"),
    }


# --- Extraccion del Paso 1 --------------------------------------------------------------------------------------------


def test_con_xml_los_datos_salen_del_xml(tmp_path):
    data = example_cfdi()
    result = extraction.extract(write(tmp_path, "f.pdf", pdf_of(data)), write(tmp_path, "f.xml", xml_of(data)))
    assert result.source == extraction.SOURCE_XML
    assert result.number == data["folio"] and result.period == "01/2026"
    assert result.pdf_metadata()["invoice"]["source"] == extraction.SOURCE_PDF_TEXT
    assert result.xml_metadata()["source"] == extraction.SOURCE_XML


def test_pdf_y_xml_de_facturas_distintas(tmp_path):
    pdf = write(tmp_path, "f.pdf", pdf_of(example_cfdi()))
    xml = write(tmp_path, "f.xml", xml_of(example_cfdi()))
    with pytest.raises(BusinessRuleError) as error:
        extraction.extract(pdf, xml)
    assert (error.value.status_code, error.value.message) == (409, extraction.MSG_MISMATCH)


def test_pdf_sin_datos_con_xml(tmp_path):
    data = moral_cfdi()
    result = extraction.extract(
        write(tmp_path, "demo.pdf", (DEMO / "factura_demo.pdf").read_bytes()), write(tmp_path, "f.xml", xml_of(data))
    )
    assert result.source == extraction.SOURCE_XML and result.number == f"A-{data['folio']}"


def test_pdf_sin_texto_y_analizador_no_disponible(tmp_path):
    document = fitz.open()
    document.new_page()
    blank = write(tmp_path, "escaneado.pdf", document.tobytes())
    document.close()
    with pytest.raises(extraction.UnreadableInvoiceError) as error:
        extraction.extract(blank, None)
    assert (error.value.status_code, error.value.message) == (422, extraction.MSG_UNREADABLE)


def test_analizador_de_demo_no_inventa_datos(tmp_path):
    with pytest.raises(AnalyzerUnavailable):
        LocalMockAnalyzer().extract_invoice(write(tmp_path, "f.pdf", EXAMPLE_PDF))
    assert LocalMockAnalyzer().health_check()["external_calls"] is False


def test_analizador_disponible_aporta_los_datos(tmp_path, monkeypatch):
    """Con un analizador configurado, un PDF sin texto se lee por OCR."""

    class Analyzer(LocalMockAnalyzer):
        def extract_invoice(self, path):
            return parse_cfdi(EXAMPLE_XML)

    monkeypatch.setattr(extraction, "get_document_analyzer", Analyzer)
    document = fitz.open()
    document.new_page()
    blank = write(tmp_path, "escaneado.pdf", document.tobytes())
    document.close()
    result = extraction.extract(blank, None)
    assert result.source == extraction.SOURCE_OCR and result.number == "3668"
