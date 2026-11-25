"""Registro de la factura nacional por sus archivos, revision junto a la imagen y reemplazo del PDF o del XML (HU-24,
spec registro-factura-extraccion)."""

from decimal import Decimal

import fitz
import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import AuditLog, Document
from tests.cfdi import (
    EXAMPLE_RFC,
    MORAL_EMAIL,
    PHYSICAL_EMAIL,
    PLAIN_PDF,
    SUPPORT,
    example_cfdi,
    example_order,
    moral_cfdi,
    number_of,
    pdf_of,
    ready_invoice,
    register,
    register_cfdi,
    reload,
    results,
    submit,
    upload,
    xml_of,
)
from tests.conftest import invoice_by_number, login


@pytest.fixture()
def provider(client):
    login(client, MORAL_EMAIL)
    return client


@pytest.fixture()
def example_provider(client):
    login(client, PHYSICAL_EMAIL)
    return client


def documents(invoice) -> dict[str, Document]:
    with SessionLocal() as db:
        rows = db.scalars(select(Document).where(Document.invoice_id == invoice.id, Document.is_current.is_(True)))
        return {row.document_type: row for row in rows}


def blank_pdf() -> bytes:
    document = fitz.open()
    document.new_page()
    content = document.tobytes()
    document.close()
    return content


# --- Paso 1 · Archivos ------------------------------------------------------------------------------------------------


def test_paso_1_pide_pdf_y_xml(provider):
    page = provider.get("/invoices/new").text
    assert 'name="pdf"' in page and 'accept=".pdf"' in page and 'name="xml"' in page
    assert '<span class="active">1 <small>Archivos</small></span>' in page
    assert "Revisión" in page and "Envío" in page


def test_solo_pdf(example_provider, purchase_orders):
    order = example_order(purchase_orders)
    data = example_cfdi(order.convenio)
    response = register(example_provider, pdf_of(data))
    assert response.status_code == 303
    invoice = invoice_by_number(number_of(data))
    assert response.headers["location"] == f"/invoices/{invoice.id}/data"
    assert (invoice.status, invoice.service_period, invoice.uuid, invoice.currency) == (
        "DRAFT",
        "01/2026",
        data["uuid"],
        "MXN",
    )
    assert invoice.purchase_order_number == str(order.convenio)
    stored = documents(invoice)
    assert set(stored) == {"INVOICE_PDF"}
    assert stored["INVOICE_PDF"].metadata_json["invoice"]["source"] == "pdf_text"
    assert stored["INVOICE_PDF"].page_count == 1


def test_pdf_y_xml(provider, purchase_orders):
    data = moral_cfdi(purchase_orders().convenio)
    response, invoice = register_cfdi(provider, data)
    assert response.status_code == 303
    stored = documents(invoice)
    assert set(stored) == {"INVOICE_PDF", "INVOICE_XML"}
    assert stored["INVOICE_XML"].metadata_json["source"] == "xml"
    assert (invoice.invoice_number, invoice.subtotal, invoice.tax) == (
        f"A-{data['folio']}",
        Decimal("100000.00"),
        Decimal("16000.00"),
    )


def test_pdf_sin_datos_acompanado_del_xml(provider):
    data = moral_cfdi()
    assert register(provider, PLAIN_PDF, xml_of(data)).status_code == 303
    assert invoice_by_number(number_of(data)).uuid == data["uuid"]


def test_pdf_y_xml_de_facturas_distintas(provider):
    data, other = moral_cfdi(), moral_cfdi()
    response = register(provider, pdf_of(data), xml_of(other))
    assert response.status_code == 409
    assert "El PDF y el XML no corresponden a la misma factura" in response.text
    assert invoice_by_number(number_of(data)) is None and invoice_by_number(number_of(other)) is None


def test_sin_pdf(provider):
    data = moral_cfdi()
    response = register(provider, None, xml_of(data))
    assert response.status_code == 400
    assert "Adjunte el PDF de la factura" in response.text
    assert invoice_by_number(number_of(data)) is None


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("factura.png", b"\x89PNG\r\n\x1a\n", "Formato no admitido para PDF del CFDI. Formatos admitidos: PDF"),
        ("factura.pdf", b"no es un pdf", "El contenido no corresponde a un PDF"),
    ],
)
def test_archivo_que_no_es_pdf(provider, filename, content, message):
    data = moral_cfdi()
    response = register(provider, content, xml_of(data), pdf_name=filename)
    assert response.status_code == 400
    assert message in response.text
    assert invoice_by_number(number_of(data)) is None


def test_xml_que_no_es_cfdi(provider):
    response = register(provider, PLAIN_PDF, b"<otro/>")
    assert response.status_code == 400
    assert "El nodo raiz no es Comprobante" in response.text


def test_pdf_ilegible(provider):
    response = register(provider, blank_pdf())
    assert response.status_code == 422
    assert "No pudimos leer los datos de la factura en el PDF. Adjunte el XML." in response.text


def test_numero_de_factura_repetido(provider):
    data = moral_cfdi()
    assert register(provider, PLAIN_PDF, xml_of(data)).status_code == 303
    repeated = moral_cfdi(folio=data["folio"])
    response = register(provider, PLAIN_PDF, xml_of(repeated))
    assert response.status_code == 409
    assert "Ya existe una factura con ese número para el proveedor" in response.text


# --- Paso 2 · Revision ------------------------------------------------------------------------------------------------


def test_revision_con_la_imagen_y_la_validacion_1(provider, purchase_orders):
    invoice, order = ready_invoice(provider, purchase_orders)
    page = provider.get(f"/invoices/{invoice.id}/data")
    assert page.status_code == 200
    pdf = documents(invoice)["INVOICE_PDF"]
    assert f'src="/invoices/{invoice.id}/documents/{pdf.id}/pages/1"' in page.text
    assert (
        '<span class="done">✓ <small>Archivos</small></span><span class="active">2 <small>Revisión</small>' in page.text
    )
    for code in ("PRV-001", "PRV-002", "PRV-003", "XML-002", "XML-005", "XML-009", "XML-010", "XML-011"):
        assert f'class="data-check ok" data-rule="{code}"' in page.text, code
    assert f"Orden de compra detectada: <strong>{order.convenio}</strong>" in page.text
    assert "Datos tomados de: <strong>XML</strong>" in page.text
    # La revision no cambia el estatus ni guarda resultados.
    assert reload(invoice).status == "UPLOADED" and results(invoice) == {}


def test_factura_emitida_a_otro_cliente(provider):
    data = moral_cfdi(receiver={"rfc": "ULT940623AG0"})
    assert register(provider, PLAIN_PDF, xml_of(data)).status_code == 303
    page = provider.get(f"/invoices/{invoice_by_number(number_of(data)).id}/data").text
    assert 'class="data-check fail" data-rule="XML-002"' in page
    assert "XML-002 · Esperado: IME010718PU3" in page


def test_revision_sin_numero_de_orden(provider):
    data = moral_cfdi(concept={"description": "Servicio sin orden de compra"})
    assert register(provider, PLAIN_PDF, xml_of(data)).status_code == 303
    page = provider.get(f"/invoices/{invoice_by_number(number_of(data)).id}/data").text
    assert "No se encontró el número de orden de compra en los conceptos" in page


def test_revision_de_otro_proveedor(client):
    login(client, PHYSICAL_EMAIL)
    assert client.get(f"/invoices/{invoice_by_number('A-CORRECTA').id}/data").status_code == 404


def test_revision_de_una_factura_enviada(provider):
    invoice = invoice_by_number("REVISION-001")
    response = provider.get(f"/invoices/{invoice.id}/data", follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, f"/invoices/{invoice.id}")


def test_revision_de_una_factura_internacional(client):
    login(client, "proveedor3@poc.local")
    invoice = invoice_by_number("INV-2026-0042")
    response = client.get(f"/invoices/{invoice.id}/data", follow_redirects=False)
    assert response.headers["location"] == f"/invoices/{invoice.id}/documents"


# --- Reemplazo del PDF o del XML (RD-04) ------------------------------------------------------------------------------


def test_xml_agregado_despues_del_pdf(example_provider, purchase_orders):
    data = example_cfdi(example_order(purchase_orders).convenio)
    assert register(example_provider, pdf_of(data)).status_code == 303
    invoice = invoice_by_number(number_of(data))
    response = upload(example_provider, invoice, "INVOICE_XML", "cfdi.xml", xml_of(data), next_step="data")
    assert (response.status_code, response.headers["location"]) == (303, f"/invoices/{invoice.id}/data")
    assert documents(invoice)["INVOICE_XML"].metadata_json["source"] == "xml"
    assert "Datos tomados de: <strong>XML</strong>" in example_provider.get(f"/invoices/{invoice.id}/data").text


def test_xml_de_otra_factura(example_provider, purchase_orders):
    data = example_cfdi(example_order(purchase_orders).convenio)
    assert register(example_provider, pdf_of(data)).status_code == 303
    invoice = invoice_by_number(number_of(data))
    response = upload(example_provider, invoice, "INVOICE_XML", "otro.xml", xml_of(example_cfdi()), next_step="data")
    assert response.status_code == 409
    assert "El PDF y el XML no corresponden a la misma factura" in response.text
    assert set(documents(invoice)) == {"INVOICE_PDF"}
    assert reload(invoice).uuid == data["uuid"]


def test_reemplazo_actualiza_los_datos_y_se_audita(provider, purchase_orders):
    invoice, order = ready_invoice(provider, purchase_orders)
    changed = moral_cfdi(order.convenio, uuid=invoice.uuid, folio=invoice.invoice_number.split("-")[1])
    changed["concepts"][0]["unit_value"] = "90000.00"
    assert upload(provider, invoice, "INVOICE_XML", "nuevo.xml", xml_of(changed)).status_code == 303
    assert reload(invoice).subtotal == Decimal("90000.00")
    with SessionLocal() as db:
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "INVOICE_DATA_EXTRACTED", AuditLog.entity_id == str(invoice.id))
        )
    assert audit.old_value["subtotal"] == "100000.00" and audit.new_value["subtotal"] == "90000.00"


def test_reemplazo_con_numero_de_otra_factura(provider, purchase_orders):
    taken, _ = ready_invoice(provider, purchase_orders)
    invoice, order = ready_invoice(provider, purchase_orders)
    clash = moral_cfdi(order.convenio, uuid=invoice.uuid, folio=taken.invoice_number.split("-")[1])
    response = upload(provider, invoice, "INVOICE_XML", "clash.xml", xml_of(clash))
    assert response.status_code == 409
    assert "Ya existe una factura con ese número para el proveedor" in response.text
    assert reload(invoice).invoice_number != taken.invoice_number


def test_pdf_ilegible_como_reemplazo_sin_xml(example_provider, purchase_orders):
    data = example_cfdi(example_order(purchase_orders).convenio)
    assert register(example_provider, pdf_of(data)).status_code == 303
    invoice = invoice_by_number(number_of(data))
    response = upload(example_provider, invoice, "INVOICE_PDF", "escaneado.pdf", blank_pdf())
    assert response.status_code == 422
    assert documents(invoice)["INVOICE_PDF"].metadata_json["invoice"]["uuid"] == data["uuid"]


# --- Validacion 1 del proveedor al enviar ----------------------------------------------------------------------------


def test_rfc_emisor_de_otro_proveedor_no_se_envia(provider, purchase_orders):
    invoice, _ = ready_invoice(provider, purchase_orders, issuer={"rfc": EXAMPLE_RFC})
    assert submit(provider, invoice).status_code == 409
    rule = results(invoice)["PRV-001"]
    assert (rule.status, rule.severity) == ("FAIL", "CRITICAL")
    assert reload(invoice).status == "UPLOADED"


def test_factura_sin_xml_evalua_las_reglas_del_cfdi_con_el_pdf(example_provider, purchase_orders):
    data = example_cfdi(example_order(purchase_orders).convenio)
    assert register(example_provider, pdf_of(data)).status_code == 303
    invoice = invoice_by_number(number_of(data))
    assert upload(example_provider, invoice, "APPROVAL", "vobo.txt", SUPPORT).status_code == 303
    assert submit(example_provider, invoice).status_code == 303
    stored = results(invoice)
    assert (
        stored["XML-001"].status == "NOT_APPLICABLE" and stored["XML-001"].message == "Sin XML: datos tomados del PDF"
    )
    assert stored["XML-002"].status == "PASS" and stored["XML-002"].source_document == "CFDI.pdf"
    assert stored["DOC-001"].status == "NOT_APPLICABLE"
