"""Confirmaciones en modales y errores de validacion junto al campo (interfaz-sin-dialogos-nativos)."""

import re

from tests.conftest import ROOT, login
from tests.test_cambio_estatus import PROVIDER_EMAIL, sent_invoice

NATIVE_DIALOG = re.compile(r"\b(alert|confirm|prompt)\s*\(")


def own_sources():
    """JavaScript y plantillas del portal, sin las librerias de terceros de app/static/vendor."""
    yield from (ROOT / "app" / "static" / "js").glob("*.js")
    yield from (ROOT / "app" / "templates").rglob("*.html")


def test_sin_dialogos_nativos_en_el_codigo():
    for source in own_sources():
        assert not NATIVE_DIALOG.search(source.read_text(encoding="utf-8")), source.name


def test_validacion_junto_al_campo_en_todas_las_paginas(client):
    login(client, "admin@poc.local")
    page = client.get("/").text
    bootstrap = page.index("/static/vendor/bootstrap.bundle.min.js")
    assert bootstrap < page.index("/static/js/form_validation.js") < page.index("/static/js/app.js")
    assert client.get("/static/js/form_validation.js").status_code == 200


def test_autorizar_pide_confirmacion_en_un_modal(client):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    page = client.get(f"/invoices/{invoice.id}").text
    assert 'id="decision-confirm"' in page and 'id="decision-confirm-accept"' in page
    question = f"¿Autorizar la factura {invoice.invoice_number} para su pago? Se notificará a Recepción de Facturas."
    assert f'value="ACCEPTED" class="btn btn-success" data-confirm="{question}"' in page
    assert 'data-error-required="Capture las observaciones."' in page


def test_sin_modal_de_decision_para_el_proveedor(client):
    invoice = sent_invoice()
    login(client, PROVIDER_EMAIL)
    assert 'id="decision-confirm"' not in client.get(f"/invoices/{invoice.id}").text


def test_mensaje_del_formato_del_periodo(client):
    login(client, PROVIDER_EMAIL)
    page = client.get("/invoices/new").text
    assert 'pattern="(0[1-9]|1[0-2])/\\d{4}" data-error-pattern="Use el formato MM/AAAA, por ejemplo 08/2026."' in page
