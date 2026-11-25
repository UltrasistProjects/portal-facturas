"""Moneda de las facturas del catalogo de monedas (ajustes-finales-configuracion; specs catalogos-referencia,
motor-validacion y flujo-facturas). Los contratos se retiraron del portal (HU-24)."""

import html

import pytest
from sqlalchemy import update

from app.core.database import SessionLocal
from app.models import CatalogEntry
from tests.cfdi import moral_cfdi, register_cfdi, reload, results, verify
from tests.conftest import csrf, invoice_by_number, login

pytestmark = pytest.mark.usefixtures("restore_validation_rules")


def test_selector_de_monedas_en_el_registro_internacional(client):
    login(client, "proveedor3@poc.local")
    page = client.get("/invoices/new").text
    assert '<select id="currency" name="currency"' in page
    assert 'value="MXN"' in page and 'value="USD"' in page


@pytest.mark.parametrize("currency", ["XYZ", "EUR"])
def test_factura_internacional_con_moneda_invalida_por_peticion_directa(client, currency):
    with SessionLocal() as db:
        db.execute(update(CatalogEntry).where(CatalogEntry.code == "EUR").values(is_active=False))
        db.commit()
    login(client, "proveedor3@poc.local")
    number = f"MON-{currency}"
    data = {
        "invoice_number": number,
        "purchase_order_number": "45009042",
        "invoice_date": "2026-08-31",
        "subtotal": "100.00",
        "tax": "0.00",
        "currency": currency,
        "csrf_token": csrf(client, "/invoices/new"),
    }
    response = client.post("/invoices/new", data=data, follow_redirects=False)
    assert response.status_code == 400 and invoice_by_number(number) is None
    assert "Moneda: la clave no está activa en el catálogo" in html.unescape(response.text)


def test_factura_nacional_nace_con_la_moneda_del_comprobante(client):
    login(client, "proveedor1@poc.local")
    response, invoice = register_cfdi(client, moral_cfdi(currency="USD"))
    assert response.status_code == 303 and invoice.currency == "USD"


def test_moneda_del_cfdi_fuera_del_catalogo_no_se_guarda(client):
    login(client, "proveedor1@poc.local")
    response, invoice = register_cfdi(client, moral_cfdi(currency="GBP"))
    assert response.status_code == 303 and invoice.currency == "MXN"
    assert verify(client, invoice).status_code == 303
    xml007 = results(invoice)["XML-007"]
    assert (xml007.status, xml007.detected_value) == ("FAIL", "GBP")
    assert reload(invoice).currency == "MXN"


def test_moneda_del_cfdi_del_catalogo_se_guarda(client):
    login(client, "proveedor1@poc.local")
    _, invoice = register_cfdi(client, moral_cfdi(currency="USD"))
    assert verify(client, invoice).status_code == 303
    assert reload(invoice).currency == "USD" and results(invoice)["XML-007"].status == "PASS"


def test_reporte_de_monedas(capsys):
    """El reporte lista, sin modificar nada, las facturas cuya moneda no es una clave del catalogo."""
    from scripts import reporte_monedas

    invoice = invoice_by_number("A-CORRECTA")
    with SessionLocal() as db:
        db.execute(update(type(invoice)).where(type(invoice).id == invoice.id).values(currency="PES"))
        db.commit()
    try:
        assert reporte_monedas.main() == 0
        output = capsys.readouterr().out
        assert f"{invoice.internal_folio} · " in output and "moneda 'PES'" in output
    finally:
        with SessionLocal() as db:
            db.execute(update(type(invoice)).where(type(invoice).id == invoice.id).values(currency=invoice.currency))
            db.commit()
