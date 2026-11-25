"""Set de prueba de data/pruebas-factura-3668 (HU-24): el flujo completo de la factura 3668 del documento de negocio
con su proveedora, la cuenta demo proveedor2@poc.local, como lo recorre su INSTRUCTIVO.md, con sus mismos archivos y
valores. Si esta prueba falla, el instructivo ya no describe lo que hace el portal."""

import html
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import and_, func, or_, select, update

from app.core.constants import InvoiceStatus
from app.core.database import SessionLocal
from app.models import Invoice, PurchaseOrder
from tests.cfdi import register, reload, results, submit, upload
from tests.conftest import csrf, invoice_by_number, login, supplier_by_email

SET = Path(__file__).resolve().parents[1] / "data" / "pruebas-factura-3668"
PROVEEDORA = "proveedor2@poc.local"
UUID = "A328F91A-DDDD-4624-89AC-877819F5B540"
ORDEN = 25704872
PDF = "CFDI-3668-GOHS60031745A.pdf"
VOBO_ERRONEO, VOBO_CORREGIDO = "VoBo-3668-v1-orden-equivocada.pdf", "VoBo-3668-v2-corregido.pdf"
REP = "REP-P-3701-GOHS60031745A"
# Seccion 5 del instructivo.
OBSERVACIONES = "El Vo.Bo. cita la orden de compra 25704827; la factura es de la 25704872. Adjunte el Vo.Bo. corregido."

pytestmark = [
    pytest.mark.usefixtures("restore_validation_rules"),
    pytest.mark.skipif(not SET.is_dir(), reason="sin el set de la factura 3668"),
]


def archivo(carpeta: str, nombre: str) -> bytes:
    return (SET / carpeta / nombre).read_bytes()


@pytest.fixture()
def factura_3668_libre():
    """La 3668 tiene UUID y numero fijos, y otras pruebas de la sesion tambien la registran con la proveedora del
    ejemplo (test_orden_compra). Antes y despues de esta prueba se aparta la que exista: sin UUID, con otro numero y
    sin orden ligada. Tampoco queda un complemento pendiente que bloquee los envios de la proveedora."""

    def apartar():
        supplier_id = supplier_by_email(PROVEEDORA).id
        mine = Invoice.supplier_id == supplier_id
        with SessionLocal() as db:
            db.execute(
                update(Invoice)
                .where(or_(Invoice.uuid == UUID, and_(mine, Invoice.invoice_number == "3668")))
                .values(uuid=None, invoice_number=func.concat("3668-APARTADA-", Invoice.id), purchase_order_id=None)
            )
            db.execute(
                update(Invoice)
                .where(
                    mine,
                    Invoice.status == InvoiceStatus.PAID,
                    Invoice.payment_complement_due_at.is_not(None),
                    Invoice.payment_complement_received_at.is_(None),
                )
                .values(payment_complement_received_at=Invoice.paid_at)
            )
            db.commit()

    apartar()
    yield
    apartar()


def orden() -> PurchaseOrder:
    with SessionLocal() as db:
        return db.scalar(select(PurchaseOrder).where(PurchaseOrder.convenio == ORDEN))


def decidir(client, invoice, decision: str, comments: str = ""):
    data = {"decision": decision, "comments": comments, "csrf_token": csrf(client, f"/invoices/{invoice.id}")}
    return client.post(f"/invoices/{invoice.id}/review", data=data, follow_redirects=False)


@pytest.mark.usefixtures("factura_3668_libre")
def test_flujo_completo_del_instructivo(client):
    # Seccion 2: la orden 25704872 ya esta en el portal, ligada a la proveedora y con su entrada de mercancia.
    proveedora = supplier_by_email(PROVEEDORA)
    oc = orden()
    assert (oc.supplier_id, oc.rfc) == (proveedora.id, "GOHS60031745A")
    assert (oc.total, oc.taxes) == (Decimal("3559.05"), Decimal("569.45"))
    login(client, "admin@poc.local")
    page = client.get(f"/purchase-orders/{oc.id}").text
    assert "LTH TIPO L-31 T-900 AR" in page and "5000527117" in page

    # Seccion 3: la proveedora registra solo el PDF. Los datos salen del texto del PDF y la Revision los marca con ✓.
    login(client, PROVEEDORA)
    response = register(client, archivo("1-factura", PDF), pdf_name=PDF)
    factura = invoice_by_number("3668")
    assert response.status_code == 303 and response.headers["location"] == f"/invoices/{factura.id}/data"
    assert (factura.status, factura.service_period, factura.uuid, factura.currency) == ("DRAFT", "01/2026", UUID, "MXN")
    assert (factura.subtotal, factura.tax, factura.total) == (Decimal("3559.05"), Decimal("569.45"), Decimal("4128.50"))
    review = html.unescape(client.get(f"/invoices/{factura.id}/data").text)
    assert "Datos tomados de: <strong>Texto del PDF</strong>" in review
    assert f"Orden de compra detectada: <strong>{ORDEN}</strong>" in review
    for rule in ("PRV-001", "PRV-002", "PRV-003", "XML-002", "XML-005", "XML-009", "XML-010", "XML-011"):
        assert f'class="data-check ok" data-rule="{rule}"' in review, rule
    assert 'class="data-check fail"' not in review

    # Seccion 4: Vo.Bo. (el que trae el error) y envio. OC-001 a OC-012 pasan y la factura queda ligada a la orden.
    vobo = archivo("1-factura", VOBO_ERRONEO)
    assert upload(client, factura, "APPROVAL", VOBO_ERRONEO, vobo, "data").status_code == 303
    assert reload(factura).status == InvoiceStatus.UPLOADED
    assert submit(client, factura).status_code == 303
    stored = results(factura)
    assert {stored[f"OC-{n:03d}"].status for n in range(1, 13)} == {"PASS"}
    assert [code for code, row in stored.items() if row.status == "FAIL"] == []
    enviada = reload(factura)
    assert enviada.status == InvoiceStatus.UNDER_REVIEW and enviada.purchase_order_id == oc.id

    # Seccion 5: el PMO ve la orden en el detalle y devuelve la factura con Observaciones por el Vo.Bo.
    login(client, "pmo@poc.local")
    detail = client.get(f"/invoices/{factura.id}").text
    assert f'href="/purchase-orders/{oc.id}">{ORDEN}</a>' in detail
    assert decidir(client, factura, "REQUIRES_CORRECTION", OBSERVACIONES).status_code == 303
    assert reload(factura).status == InvoiceStatus.REQUIRES_CORRECTION

    # Seccion 6: la proveedora reemplaza el Vo.Bo. y reenvia; la orden sigue siendo suya (OC-012 la excluye).
    login(client, PROVEEDORA)
    assert OBSERVACIONES in html.unescape(client.get(f"/invoices/{factura.id}").text)
    vobo = archivo("1-factura", VOBO_CORREGIDO)
    assert upload(client, factura, "APPROVAL", VOBO_CORREGIDO, vobo).status_code == 303
    assert submit(client, factura).status_code == 303
    assert reload(factura).status == InvoiceStatus.UNDER_REVIEW
    assert results(factura)["OC-012"].status == "PASS"

    # Seccion 7: el PMO autoriza.
    login(client, "pmo@poc.local")
    assert decidir(client, factura, "ACCEPTED").status_code == 303
    assert reload(factura).status == InvoiceStatus.ACCEPTED

    # Seccion 8: el Administrador la marca como pagada. Es PPD: aunque no trae XML, requiere Complemento de Pago.
    login(client, "admin@poc.local")
    data = {"confirm": "1", "csrf_token": csrf(client, f"/invoices/{factura.id}")}
    assert client.post(f"/invoices/{factura.id}/payment", data=data, follow_redirects=False).status_code == 303
    pagada = reload(factura)
    assert pagada.status == InvoiceStatus.PAID and pagada.payment_complement_due_at is not None
    assert pagada.payment_complement_received_at is None

    # Seccion 9: la proveedora adjunta el complemento (XML y PDF), que relaciona el UUID de la 3668.
    login(client, PROVEEDORA)
    for tipo, extension in (("PAYMENT_COMPLEMENT_XML", "xml"), ("PAYMENT_COMPLEMENT_PDF", "pdf")):
        nombre = f"{REP}.{extension}"
        assert upload(client, factura, tipo, nombre, archivo("2-pago", nombre)).status_code == 303
    assert reload(factura).payment_complement_received_at is not None

    # Seccion 10: la orden 25704872 muestra la factura ligada.
    login(client, "pmo@poc.local")
    page = client.get(f"/purchase-orders/{oc.id}").text
    assert pagada.internal_folio in page and "3668" in page
