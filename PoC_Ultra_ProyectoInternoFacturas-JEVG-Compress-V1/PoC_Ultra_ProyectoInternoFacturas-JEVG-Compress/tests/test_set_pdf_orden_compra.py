"""Set de prueba de data/pruebas-pdf-orden-compra (HU-24): el recorrido de su INSTRUCTIVO.md con sus mismos archivos
y valores, de punta a punta. Si esta prueba falla, el instructivo ya no describe lo que hace el portal."""

import html
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import PurchaseOrder
from app.services.invoice_extraction_service import MSG_UNREADABLE
from tests.cfdi import register, reload, results, submit, upload
from tests.conftest import csrf, invoice_by_number, load_requirements, login, supplier_by_email

SET = Path(__file__).resolve().parents[1] / "data" / "pruebas-pdf-orden-compra"
RFC = "MFB140325AB1"

pytestmark = [
    pytest.mark.usefixtures("restore_validation_rules"),
    pytest.mark.skipif(not SET.is_dir(), reason="sin el set de prueba del PDF"),
]

# Seccion 2 del instructivo: alta del proveedor (Administrador > Proveedores > + Agregar proveedor).
ALTA = {
    "origin": "NATIONAL",
    "business_name": "Mantenimiento Ferroviario del Bajío",
    "rfc": RFC,
    "supplier_type": "PERSONA_MORAL",
    "email": "facturacion@mfbajio.example",
    "phone": "442 218 7740",
    "classification": "EXTERNAL",
    "main_activity": "81",
    "incorporation_date": "2014-03-25",
    "website": "https://www.mfbajio.example",
    "contact_name": "Laura Méndez Ocampo",
    "contact_phone": "442 218 7741",
    "legal_rep_name": "Arturo Villaseñor Pacheco",
    "legal_rep_phone": "442 218 7742",
    "bank_information": "Banco Demo, S.A. - Cuenta 0213458790 - CLABE 000680002134587906",
    "confidentiality_agreement": "true",
}


def archivo(carpeta: str, nombre: str) -> bytes:
    return (SET / carpeta / nombre).read_bytes()


def registrar(client, carpeta: str, folio: str, xml: bool = False):
    """Paso 1 con el PDF del caso (y su XML si se pide); devuelve la respuesta y la factura F-<folio>."""
    pdf = next((SET / carpeta).glob(f"CFDI-F{folio}-{RFC}*.pdf")).name
    response = register(
        client,
        archivo(carpeta, pdf),
        archivo(carpeta, f"CFDI-F{folio}-{RFC}.xml") if xml else None,
        pdf_name=pdf,
        xml_name=f"CFDI-F{folio}-{RFC}.xml",
    )
    return response, invoice_by_number(f"F-{folio}")


def enviar(client, carpeta: str, folio: str, xml: bool = False):
    """Paso 1, Vo.Bo. desde la Revision y "Enviar a validacion"; devuelve la factura, el codigo y las reglas en FAIL."""
    response, invoice = registrar(client, carpeta, folio, xml)
    assert response.status_code == 303 and response.headers["location"] == f"/invoices/{invoice.id}/data"
    vobo = upload(client, invoice, "APPROVAL", f"VoBo-F{folio}.pdf", archivo(carpeta, f"VoBo-F{folio}.pdf"), "data")
    assert vobo.status_code == 303 and reload(invoice).status == "UPLOADED"
    code = submit(client, invoice).status_code
    fails = {rule: row.message for rule, row in results(invoice).items() if row.status == "FAIL"}
    return reload(invoice), code, fails


def convenio(invoice) -> int | None:
    with SessionLocal() as db:
        order = db.get(PurchaseOrder, invoice.purchase_order_id) if invoice.purchase_order_id else None
        return order.convenio if order else None


def test_recorrido_del_instructivo(client):
    # Las ordenes del set ya estan en el portal antes del alta del proveedor: se ligan por su RFC.
    with SessionLocal() as db:
        orders = db.scalars(select(PurchaseOrder).where(PurchaseOrder.rfc == RFC)).all()
    assert sorted(o.convenio for o in orders) == [45000611, 45000612, 45000613, 45000614, 45000615, 45000616]
    assert all(o.supplier_id is None for o in orders)

    # Alta, expediente y autorizacion (Administrador); el expediente se da por cargado.
    login(client)
    form = {**ALTA, "csrf_token": csrf(client, "/suppliers")}
    response = client.post("/suppliers", data=form, follow_redirects=False)
    assert response.status_code == 303, html.unescape(response.text)
    supplier = supplier_by_email(ALTA["email"])
    load_requirements(supplier.id)
    data = {"supplier_ids": [str(supplier.id)], "csrf_token": csrf(client, "/suppliers")}
    assert client.post("/suppliers/authorize", data=data, follow_redirects=False).status_code == 303
    login(client, ALTA["email"])

    # Caso 1: factura correcta, solo PDF. Los datos salen del texto del PDF y todas las reglas pasan.
    _, draft = registrar(client, "1-factura-correcta", "2101")
    review = html.unescape(client.get(f"/invoices/{draft.id}/data").text)
    assert "Datos tomados de: <strong>Texto del PDF</strong>" in review
    assert "Orden de compra detectada: <strong>45000611</strong>" in review
    for rule in ("PRV-001", "PRV-002", "PRV-003", "XML-002", "XML-009", "XML-010", "XML-011"):
        assert f'class="data-check ok" data-rule="{rule}"' in review, rule
    assert (draft.service_period, draft.subtotal, draft.tax, draft.total) == ("11/2026", 123000, 19680, 142680)
    vobo = archivo("1-factura-correcta", "VoBo-F2101.pdf")
    assert upload(client, draft, "APPROVAL", "VoBo-F2101.pdf", vobo, "data").status_code == 303
    assert submit(client, draft).status_code == 303
    correcta = reload(draft)
    stored = results(correcta)
    assert correcta.status == "UNDER_REVIEW" and convenio(correcta) == 45000611
    assert {stored[f"OC-{n:03d}"].status for n in range(1, 13)} == {"PASS"}

    # Casos 2 a 6: el envio no procede; la factura sigue "Cargada" y sin orden ligada.
    blocked = {
        ("2-monto-distinto", "2102"): {"OC-005", "OC-006", "OC-009"},
        ("3-sin-entrada-de-mercancia", "2103"): {"OC-011"},
        ("4-orden-ya-facturada", "2104"): {"OC-012"},
        ("5-orden-de-otro-proveedor", "2105"): {"OC-002"},
        ("6-sin-orden-en-el-concepto", "2106"): {"OC-001"},
    }
    messages = {}
    for (carpeta, folio), expected in blocked.items():
        invoice, code, fails = enviar(client, carpeta, folio)
        assert (code, invoice.status, invoice.purchase_order_id) == (409, "UPLOADED", None), carpeta
        assert set(fails) == expected, (carpeta, fails)
        messages.update(fails)
    assert messages["OC-005"] == "Subtotal 68500.00 distinto del total de la orden de compra 60000.00"
    assert messages["OC-006"] == "IVA 10960.00 distinto de los impuestos de la orden de compra 9600.00"
    assert messages["OC-009"] == "Concepto 1: importe 68500.00 vs 60000.00"
    assert messages["OC-011"] == "Concepto 1: la partida no tiene entrada de mercancía"
    assert messages["OC-012"] == f"La orden de compra ya tiene la factura {correcta.internal_folio}"
    assert messages["OC-002"] == "La orden de compra 45000451 no existe para el proveedor"
    assert messages["OC-001"] == "No se encontró el número de orden de compra en los conceptos"

    # Caso 7: factura emitida a otro cliente. La Revision ya marca el receptor y el envio no procede.
    _, draft = registrar(client, "7-receptor-incorrecto", "2107")
    review = client.get(f"/invoices/{draft.id}/data").text
    for rule in ("XML-002", "XML-009", "XML-010"):
        assert f'class="data-check fail" data-rule="{rule}"' in review, rule
    vobo = archivo("7-receptor-incorrecto", "VoBo-F2107.pdf")
    assert upload(client, draft, "APPROVAL", "VoBo-F2107.pdf", vobo, "data").status_code == 303
    assert submit(client, draft).status_code == 409
    fails = {rule: (row.message, row.expected_value) for rule, row in results(draft).items() if row.status == "FAIL"}
    assert fails == {
        "XML-002": ("RFC receptor incorrecto", "IME010718PU3"),
        "XML-009": ("Razón social del receptor incorrecta", "INTERMODAL MEXICO"),
        "XML-010": ("Código postal del receptor incorrecto", "11700"),
    }
    assert reload(draft).status == "UPLOADED"

    # Caso 8: PDF escaneado. Solo con el PDF no se registra; con su XML, los datos salen del XML y se envia.
    response, invoice = registrar(client, "8-pdf-escaneado", "2108")
    assert response.status_code == 422 and MSG_UNREADABLE in html.unescape(response.text) and invoice is None
    escaneada, code, fails = enviar(client, "8-pdf-escaneado", "2108", xml=True)
    assert (code, fails, escaneada.status, convenio(escaneada)) == (303, {}, "UNDER_REVIEW", 45000615)

    # PMO: la orden 45000611 muestra la factura del caso 1 ligada.
    login(client, "pmo@poc.local")
    with SessionLocal() as db:
        order_id = db.scalar(select(PurchaseOrder.id).where(PurchaseOrder.convenio == 45000611))
    page = client.get(f"/purchase-orders/{order_id}").text
    assert correcta.internal_folio in page and "F-2101" in page
