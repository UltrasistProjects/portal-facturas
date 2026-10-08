"""Moneda de contratos y facturas del catalogo de monedas (ajustes-finales-configuracion; specs catalogos-referencia,
motor-validacion y flujo-facturas)."""

import html
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models import CatalogEntry, Contract
from tests.conftest import csrf, invoice_by_number, login, supplier_by_email
from tests.test_registro_envio import cfdi, create_invoice, load, reload, results, verify

pytestmark = pytest.mark.usefixtures("restore_validation_rules")


def create_contract(client, currency: str):
    name = f"Moneda {uuid4().hex[:8]}"
    data = {
        "supplier_id": supplier_by_email("proveedor2@poc.local").id,
        "project_name": name,
        "project_leader": "Lider",
        "authorized_technology": "Python",
        "authorized_amount": "100000.00",
        "currency": currency,
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "csrf_token": csrf(client, "/contracts"),
    }
    response = client.post("/contracts", data=data, follow_redirects=False)
    with SessionLocal() as db:
        return response, db.scalar(select(Contract).where(Contract.project_name == name))


def test_selector_de_monedas_en_el_alta_de_contrato(client):
    login(client)
    page = client.get("/contracts").text
    assert '<select id="contract-currency" name="currency"' in page
    assert '<option value="MXN" selected>MXN · Peso mexicano</option>' in page and 'value="USD"' in page


def test_contrato_con_moneda_del_catalogo(client):
    login(client)
    response, contract = create_contract(client, "usd")
    assert response.status_code == 303 and contract.currency == "USD"


@pytest.mark.parametrize("currency", ["XYZ", "EUR"])
def test_contrato_con_moneda_invalida_por_peticion_directa(client, currency):
    with SessionLocal() as db:
        db.execute(update(CatalogEntry).where(CatalogEntry.code == "EUR").values(is_active=False))
        db.commit()
    login(client)
    response, contract = create_contract(client, currency)
    assert response.status_code == 400 and contract is None
    assert "Moneda: la clave no está activa en el catálogo" in html.unescape(response.text)


def test_factura_nacional_nace_con_la_moneda_de_su_contrato(client):
    login(client, "proveedor1@poc.local")
    invoice = create_invoice(client)
    with SessionLocal() as db:
        assert invoice.currency == db.get(Contract, invoice.contract_id).currency


def test_moneda_del_cfdi_fuera_del_catalogo_no_se_guarda(client):
    login(client, "proveedor1@poc.local")
    invoice = load(client, create_invoice(client), cfdi(Moneda="GBP"))
    assert verify(client, invoice).status_code == 303
    xml007 = results(invoice)["XML-007"]
    assert (xml007.status, xml007.detected_value) == ("FAIL", "GBP")
    assert reload(invoice).currency == "MXN"


def test_moneda_del_cfdi_del_catalogo_se_guarda(client):
    login(client, "proveedor1@poc.local")
    invoice = load(client, create_invoice(client), cfdi(Moneda="USD"))
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
