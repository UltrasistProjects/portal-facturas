"""Ajustes de Ferromex: alta y edicion de ordenes de compra, rol "Analista de cuentas por pagar", identidad del
proveedor en su expediente, reporte resumen en PDF y la plantilla del pago programado (migracion 0024). El flujo de
"Programar pago" lo cubre test_pago_facturas."""

import html
import re
import secrets
import string
from decimal import Decimal
from uuid import uuid4

import fitz
import pytest
from alembic import command
from sqlalchemy import delete, func, select

from app.core.constants import InvoiceStatus, SupplierOrigin
from app.core.database import SessionLocal
from app.models import AuditLog, Invoice, PurchaseOrder, Supplier, User
from scripts import pgtools
from tests.cfdi import EXAMPLE_RFC, MORAL_EMAIL, MORAL_RFC, PHYSICAL_EMAIL, item, new_convenio
from tests.conftest import SUPPLIER_PROFILE_FORM, alembic_config, csrf, login, supplier_by_email
from tests.test_factura_internacional import INTERNATIONAL
from tests.test_migraciones import execute, query

PMO = "pmo@poc.local"
ADMIN = "admin@poc.local"
ANALYST = "Analista de cuentas por pagar"


# --- Ordenes de compra: alta y edicion ------------------------------------------------------------------------------


@pytest.fixture()
def created_orders():
    """Convenios que la prueba da de alta por el formulario; al terminar se borran los que no quedaron ligados."""
    convenios: list[int] = []
    yield convenios
    with SessionLocal() as db:
        linked = select(Invoice.purchase_order_id).where(Invoice.purchase_order_id.is_not(None))
        db.execute(delete(PurchaseOrder).where(PurchaseOrder.convenio.in_(convenios), PurchaseOrder.id.not_in(linked)))
        db.commit()


def order_form(convenio, supplier_id, rows=None, **header) -> dict:
    """Datos del formulario: cada columna de partidas como lista (item-<etiqueta de SAP>)."""
    rows = rows or [
        {
            "Material": "E20080",
            "Txt.brv": "LTH TIPO L-31 T-900 AR",
            "Ctd.Pedido": "2",
            "Unidad.Pedido": "PZA",
            "Fe.Entrega": "2025-12-30",
            "Prc.Neto": "1500.50",
            "Moneda": "MXN",
            "Grupo.Art": "ELECTRICO",
            "Almacen": "GUADALAJARA_1 STATION 1",
            "Docto Material": "5000527117",
            "Fecha Conta": "2025-12-16",
        }
    ]
    data = {
        "convenio": str(convenio),
        "supplier_id": str(supplier_id),
        "order_date": "2025-12-09",
        "total": "3001.00",
        "taxes": "480.16",
        **header,
    }
    keys = ["Material", "Txt.brv", "Ctd.Pedido", "Unidad.Pedido", "Fe.Entrega", "Prc.Neto", "Moneda"]
    keys += ["Grupo.Art", "Almacen", "Docto Material", "Fecha Conta"]
    for key in keys:
        data[f"item-{key}"] = [row.get(key, "") for row in rows]
    return data


def post_order(client, data: dict, path: str = "/purchase-orders/new"):
    data = {**data, "csrf_token": csrf(client, "/purchase-orders")}
    return client.post(path, data=data, follow_redirects=False)


def order_by_convenio(convenio: int) -> PurchaseOrder | None:
    with SessionLocal() as db:
        return db.scalar(select(PurchaseOrder).where(PurchaseOrder.convenio == convenio))


def order_audits(order_id: int, action: str) -> list[AuditLog]:
    with SessionLocal() as db:
        stmt = select(AuditLog).where(
            AuditLog.entity == "PurchaseOrder", AuditLog.entity_id == str(order_id), AuditLog.action == action
        )
        return list(db.scalars(stmt.order_by(AuditLog.id)))


def test_formulario_de_alta(client):
    login(client, PMO)
    page = client.get("/purchase-orders").text
    assert 'href="/purchase-orders/new"' in page and "Nueva orden de compra" in page
    form = client.get("/purchase-orders/new")
    assert form.status_code == 200
    assert 'action="/purchase-orders/new"' in form.text and 'id="po-item-template"' in form.text
    assert supplier_by_email(MORAL_EMAIL).business_name in form.text and "Agregar partida" in form.text


def test_alta_de_orden_de_compra(client, created_orders):
    convenio = new_convenio()
    created_orders.append(convenio)
    supplier = supplier_by_email(MORAL_EMAIL)
    login(client, PMO)
    response = post_order(client, order_form(convenio, supplier.id))
    assert response.status_code == 303
    order = order_by_convenio(convenio)
    assert response.headers["location"] == f"/purchase-orders/{order.id}?notice=created"
    assert (order.rfc, order.supplier_name, order.supplier_id) == (MORAL_RFC, supplier.business_name, supplier.id)
    assert (order.total, order.taxes) == (Decimal("3001.00"), Decimal("480.16"))
    [saved] = order.data["items"]
    # Las fechas del formulario se guardan como las escribe SAP.
    assert (saved["Fe.Entrega"], saved["Fecha Conta"]) == ("30.12.2025", "16.12.2025")
    assert (saved["Ctd.Pedido"], saved["Prc.Neto"], saved["Unidad.Pedido"]) == ("2", "1500.50", "PZA")
    [entry] = order_audits(order.id, "PURCHASE_ORDER_CREATED")
    assert entry.new_value["convenio"] == convenio and entry.new_value["items"] == 1
    detail = client.get(response.headers["location"]).text
    assert "Orden de compra creada" in detail and f'href="/purchase-orders/{order.id}/edit"' in detail
    assert "LTH TIPO L-31 T-900 AR" in detail and "30.12.2025" in detail


def test_alta_de_orden_internacional(client, created_orders):
    convenio = new_convenio()
    created_orders.append(convenio)
    supplier = supplier_by_email(INTERNATIONAL)
    row = {
        "Txt.brv": "DATA ANALYTICS CONSULTING",
        "Ctd.Pedido": "1",
        "Unidad.Pedido": "SER",
        "Prc.Neto": "1000.00",
        "Moneda": "USD",
    }
    login(client, ADMIN)
    response = post_order(client, order_form(convenio, supplier.id, [row], total="1000.00", taxes="0"))
    assert response.status_code == 303
    order = order_by_convenio(convenio)
    assert (order.rfc, order.supplier_id) == ("XEXX010101000", supplier.id)
    assert order.data["items"][0]["Fe.Entrega"] == "" and order.data["items"][0]["Moneda"] == "USD"


@pytest.mark.parametrize(
    ("changes", "rows", "message"),
    [
        ({"convenio": "12345"}, None, "El convenio debe tener de 6 a 10 dígitos"),
        ({"supplier_id": ""}, None, "Seleccione el proveedor de la orden"),
        ({"supplier_id": "999999999"}, None, "Seleccione el proveedor de la orden"),
        ({"order_date": ""}, None, "Capture la fecha de la orden"),
        ({"total": "0"}, None, "El total debe ser un importe mayor que cero"),
        ({"taxes": "-1"}, None, "Los impuestos deben ser un importe mayor o igual a cero"),
        ({}, [{"Material": "X", "Moneda": "MXN"}], "Partida 1: faltan Txt.brv, Ctd.Pedido, Unidad.Pedido, Prc.Neto"),
        ({}, [], "La orden de compra debe tener al menos una partida"),
        (
            {},
            [{"Txt.brv": "A", "Ctd.Pedido": "1", "Unidad.Pedido": "PZA", "Prc.Neto": "-3", "Moneda": "MXN"}],
            "Partida 1: Prc.Neto debe ser un decimal positivo",
        ),
        (
            {},
            [
                {
                    "Txt.brv": "A",
                    "Ctd.Pedido": "1",
                    "Unidad.Pedido": "PZA",
                    "Prc.Neto": "3",
                    "Moneda": "MXN",
                    "Fecha Conta": "16/12/2025",
                }
            ],
            "Partida 1: Fecha contab. debe ser una fecha válida",
        ),
    ],
    ids=[
        "convenio",
        "sin-proveedor",
        "proveedor-inexistente",
        "sin-fecha",
        "total",
        "impuestos",
        "partida-incompleta",
        "sin-partidas",
        "precio",
        "fecha-partida",
    ],
)
def test_alta_rechazada_conserva_lo_capturado(client, changes, rows, message):
    convenio = new_convenio()
    supplier = supplier_by_email(MORAL_EMAIL)
    # Sin partidas: una fila con solo la moneda que propone el formulario cuenta como vacia.
    data = order_form(convenio, supplier.id, None if rows is None else (rows or [{"Moneda": "MXN"}]))
    data.update(changes)
    login(client, PMO)
    response = post_order(client, data)
    assert response.status_code == 400
    assert message in response.text
    assert order_by_convenio(convenio) is None
    assert f'value="{data["convenio"]}"' in response.text


def test_convenio_repetido(client, purchase_orders):
    existing = purchase_orders()
    supplier = supplier_by_email(MORAL_EMAIL)
    login(client, PMO)
    response = post_order(client, order_form(existing.convenio, supplier.id))
    assert response.status_code == 400 and f"Ya existe la orden de compra {existing.convenio}" in response.text


def test_proveedor_sin_acceso_al_alta(client):
    login(client, MORAL_EMAIL)
    assert client.get("/purchase-orders/new").status_code == 403
    assert client.post("/purchase-orders/new", data={"csrf_token": csrf(client, "/")}).status_code == 403


def test_edicion_de_orden_de_compra(client, purchase_orders):
    order = purchase_orders(items=[item(price="50000.00", quantity="2")])
    login(client, PMO)
    form = client.get(f"/purchase-orders/{order.id}/edit")
    assert form.status_code == 200
    # Las fechas de SAP llegan al formulario en formato ISO.
    assert 'value="2026-07-31"' in form.text and f'value="{order.convenio}"' in form.text
    supplier = supplier_by_email(MORAL_EMAIL)
    rows = [
        {**item(price="50000.00", quantity="2"), "Fe.Entrega": "2026-07-31", "Fecha Conta": "2026-07-31"},
        {"Txt.brv": "SOPORTE ADICIONAL", "Ctd.Pedido": "1", "Unidad.Pedido": "SER", "Prc.Neto": "500", "Moneda": "MXN"},
    ]
    data = order_form(order.convenio, supplier.id, rows, order_date="2026-07-20", total="100500.00", taxes="16080")
    response = post_order(client, data, f"/purchase-orders/{order.id}/edit")
    assert response.status_code == 303
    assert response.headers["location"] == f"/purchase-orders/{order.id}?notice=updated"
    with SessionLocal() as db:
        stored = db.get(PurchaseOrder, order.id)
        assert stored.total == Decimal("100500.00") and stored.taxes == Decimal("16080.00")
        assert [row["Txt.brv"] for row in stored.data["items"]] == [item()["Txt.brv"], "SOPORTE ADICIONAL"]
        assert stored.data["items"][0]["Fecha Conta"] == "31.07.2026"
    [entry] = order_audits(order.id, "PURCHASE_ORDER_UPDATED")
    assert entry.old_value["items"] == 1 and entry.new_value["items"] == 2
    assert entry.old_value["total"] == "100000.00" and entry.new_value["total"] == "100500.00"
    assert "Orden de compra actualizada" in client.get(response.headers["location"]).text
    # Volver a guardar lo mismo no cambia nada ni se audita.
    unchanged = post_order(client, data, f"/purchase-orders/{order.id}/edit")
    assert unchanged.headers["location"] == f"/purchase-orders/{order.id}?notice=unchanged"
    assert len(order_audits(order.id, "PURCHASE_ORDER_UPDATED")) == 1


@pytest.fixture()
def link_invoice():
    """Liga a una orden una factura "Rechazada" de proveedor2 (no entra a la bandeja ni carga a proveedor1). Al
    terminar se borra: test_flujo cuenta las facturas de proveedor2. Se declara despues de purchase_orders en la
    prueba, asi se borra antes de que esa fixture limpie sus ordenes."""
    created: list[int] = []

    def make(order: PurchaseOrder) -> None:
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == PHYSICAL_EMAIL))
            invoice = Invoice(
                internal_folio=f"FAC-OC-{uuid4().hex[:10]}",
                supplier_id=user.supplier_id,
                uploaded_by=user.id,
                invoice_number=f"OC-{uuid4().hex[:8].upper()}",
                service_period="07/2026",
                subtotal=Decimal("100000.00"),
                tax=Decimal("16000.00"),
                total=Decimal("116000.00"),
                currency="MXN",
                status=InvoiceStatus.REJECTED,
                purchase_order_number=str(order.convenio),
                purchase_order_id=order.id,
            )
            db.add(invoice)
            db.commit()
            created.append(invoice.id)

    yield make
    with SessionLocal() as db:
        db.execute(delete(Invoice).where(Invoice.id.in_(created)), execution_options={"synchronize_session": False})
        db.commit()


def test_orden_con_facturas_conserva_convenio_y_proveedor(client, purchase_orders, link_invoice):
    order = purchase_orders()
    link_invoice(order)
    moral = supplier_by_email(MORAL_EMAIL)
    login(client, ADMIN)
    form = client.get(f"/purchase-orders/{order.id}/edit").text
    assert "La orden tiene 1 factura ligada" in form and 'name="convenio"' in form and " readonly" in form
    row = {**item(), "Fe.Entrega": "2026-07-31", "Fecha Conta": "2026-07-31"}
    other = order_form(new_convenio(), moral.id, [row], total="100000.00", taxes="16000.00")
    response = post_order(client, other, f"/purchase-orders/{order.id}/edit")
    assert response.status_code == 400
    assert f"La orden {order.convenio} ya tiene facturas ligadas" in response.text
    physical = supplier_by_email(PHYSICAL_EMAIL)
    moved = order_form(order.convenio, physical.id, [row], total="100000.00", taxes="16000.00")
    assert post_order(client, moved, f"/purchase-orders/{order.id}/edit").status_code == 400
    # Montos y partidas si cambian.
    taxes = order_form(order.convenio, moral.id, [row], total="100000.00", taxes="15000.00")
    assert post_order(client, taxes, f"/purchase-orders/{order.id}/edit").status_code == 303
    stored = order_by_convenio(order.convenio)
    assert stored.taxes == Decimal("15000.00") and stored.rfc == MORAL_RFC


def test_orden_sin_proveedor_registrado_conserva_su_rfc(client, purchase_orders):
    order = purchase_orders(rfc="AAA010101AAA", supplier_name="PROVEEDOR SOLO EN SAP")
    login(client, PMO)
    form = client.get(f"/purchase-orders/{order.id}/edit").text
    assert "AAA010101AAA · PROVEEDOR SOLO EN SAP (sin proveedor en el portal)" in form
    row = {**item(), "Fe.Entrega": "2026-07-31", "Fecha Conta": "2026-07-31"}
    data = order_form(order.convenio, "", [row], total="100000.00", taxes="16000.00", order_date="2026-07-21")
    assert post_order(client, data, f"/purchase-orders/{order.id}/edit").status_code == 303
    stored = order_by_convenio(order.convenio)
    assert (stored.rfc, stored.supplier_name, stored.supplier_id) == ("AAA010101AAA", "PROVEEDOR SOLO EN SAP", None)
    assert stored.order_date.isoformat() == "2026-07-21"


def test_editar_orden_inexistente(client):
    login(client, PMO)
    assert client.get("/purchase-orders/999999999/edit").status_code == 404


# --- Rol "Analista de cuentas por pagar" ----------------------------------------------------------------------------


def test_rol_del_pmo_con_su_nombre_visible(client):
    login(client, PMO)
    page = client.get("/").text
    assert f'<span class="role-pill">{ANALYST}</span>' in page and "En validación de cuentas por pagar" in page
    login(client, ADMIN)
    users = client.get("/admin/users", params={"q": "pmo@poc.local"}).text
    assert f'<span class="role-pill">{ANALYST}</span>' in users
    assert f'<option value="PMO">{ANALYST}</option>' in users


# --- Expediente del proveedor -----------------------------------------------------------------------------------------


def test_expediente_con_rfc_origen_y_tipo_de_persona(client):
    physical = supplier_by_email(PHYSICAL_EMAIL)
    login(client, PMO)
    page = client.get(f"/suppliers/{physical.id}").text
    general = re.search(r'<dl class="data-list supplier-identity">.*?</dl>', page, re.S).group(0)
    assert f'<dt>RFC</dt><dd class="mono">{EXAMPLE_RFC}</dd>' in general
    assert "<dt>Origen</dt><dd>Nacional</dd>" in general
    assert "<dt>Tipo de persona</dt><dd>Persona física (con actividad empresarial)</dd>" in general


def test_expediente_internacional_con_identificador_y_pais(client):
    foreign = supplier_by_email(INTERNATIONAL)
    login(client, ADMIN)
    page = client.get(f"/suppliers/{foreign.id}").text
    general = re.search(r'<dl class="data-list supplier-identity">.*?</dl>', page, re.S).group(0)
    assert f'<dt>Identificador fiscal</dt><dd class="mono">{foreign.foreign_tax_id}</dd>' in general
    assert "<dt>País</dt><dd>Estados Unidos</dd>" in general and "<dt>Origen</dt><dd>Internacional</dd>" in general
    assert "<dt>RFC</dt>" not in general


# --- Reporte resumen en PDF -------------------------------------------------------------------------------------------


def pdf_text(response) -> str:
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    with fitz.open("pdf", response.content) as document:
        assert document.page_count == 1
        return document[0].get_text()


def test_boton_del_reporte_con_los_filtros(client):
    login(client, PMO)
    page = client.get("/invoices", params={"status": "", "origin": "NATIONAL", "q": "FAC"}).text
    # Solo con "Todos los estados": lleva la busqueda y el origen, no el estatus.
    button = 'class="btn btn-outline-danger report-link" id="invoice-report"'
    assert f'{button} href="/invoices/report.pdf?q=FAC&amp;origin=NATIONAL"' in page


@pytest.mark.parametrize("params", [{}, {"status": "REJECTED"}], ids=["bandeja-enviadas", "un-estatus"])
def test_boton_del_reporte_inactivo_con_un_estatus(client, params):
    login(client, ADMIN)
    page = client.get("/invoices", params=params).text
    button = re.search(r'<a class="btn btn-outline-danger report-link disabled"[^>]*>', page).group(0)
    assert 'aria-disabled="true"' in button and "href=" not in button
    assert 'title="Disponible con &quot;Todos los estados&quot;"' in page


def test_reporte_resumen_en_pdf(client):
    login(client, PMO)
    response = client.get("/invoices/report.pdf", params={"status": ""})
    disposition = response.headers["content-disposition"]
    assert re.fullmatch(r'attachment; filename="reporte-facturas-\d{8}-\d{4}\.pdf"', disposition)
    text = pdf_text(response)
    assert "Reporte resumen de facturas" in text and "Resumen por estatus" in text and "Resumen por origen" in text
    assert f"Analista CxP Demo ({ANALYST})" in text
    assert "Estatus: Todos" in text
    with SessionLocal() as db:
        total = len(list(db.scalars(select(Invoice.id))))
    assert re.search(rf"Total\s+{total}\s+100\.0 %", text)


def test_reporte_siempre_con_todos_los_estatus(client):
    """Un estatus en la direccion se ignora: el pie compara todos; el origen si se aplica."""
    login(client, ADMIN)
    text = pdf_text(client.get("/invoices/report.pdf", params={"status": "REJECTED", "origin": "NATIONAL"}))
    assert "Estatus: Todos" in text and "Origen: Nacional" in text
    with SessionLocal() as db:
        national = db.scalar(
            select(func.count(Invoice.id)).join(Invoice.supplier).where(Supplier.origin == SupplierOrigin.NATIONAL)
        )
    assert re.search(rf"Total\s+{national}\s+100\.0 %", text)


def test_reporte_del_proveedor_solo_con_sus_facturas(client):
    login(client, MORAL_EMAIL)
    text = pdf_text(client.get("/invoices/report.pdf"))
    supplier = supplier_by_email(MORAL_EMAIL)
    with SessionLocal() as db:
        own = len(list(db.scalars(select(Invoice.id).where(Invoice.supplier_id == supplier.id))))
    assert re.search(rf"Total\s+{own}\s+", text)


def test_reporte_sin_facturas(client):
    login(client, PMO)
    text = pdf_text(client.get("/invoices/report.pdf", params={"q": "no-existe-ninguna-factura"}))
    assert "Sin facturas" in text and "No hay facturas con los filtros aplicados." in text


# --- Migracion 0024: texto del correo del pago programado ------------------------------------------------------------

PAYMENT = "0024_ferromex_programar_pago"


@pytest.fixture()
def empty_db():
    """Base PostgreSQL vacia, adicional a la de la sesion (como en test_migraciones)."""
    with pgtools.temporary_database("portal_test_mig_") as url:
        yield pgtools.url_string(url)


PREVIOUS = "0023_ferromex_purchase_orders"
SUBJECT = "SELECT subject FROM notification_templates WHERE event = 'INVOICE_PAID'"


def test_migracion_del_texto_del_pago_programado(empty_db):
    config = alembic_config(empty_db)
    command.upgrade(config, PREVIOUS)
    assert query(empty_db, SUBJECT) == [("Factura {{numero_factura}} pagada",)]
    command.upgrade(config, PAYMENT)
    assert query(empty_db, SUBJECT) == [("Factura {{numero_factura}} programada para pago",)]
    command.downgrade(config, PREVIOUS)
    assert query(empty_db, SUBJECT) == [("Factura {{numero_factura}} pagada",)]


def test_migracion_conserva_la_plantilla_personalizada(empty_db):
    config = alembic_config(empty_db)
    command.upgrade(config, PREVIOUS)
    execute(
        empty_db,
        "UPDATE notification_templates SET subject = 'Pago {{numero_factura}}', version = 2, updated_by = NULL"
        " WHERE event = 'INVOICE_PAID'",
    )
    command.upgrade(config, PAYMENT)
    assert query(empty_db, SUBJECT) == [("Pago {{numero_factura}}",)]


# --- Migracion 0025: sin seguimiento del Complemento de Pago --------------------------------------------------------

WITHOUT_COMPLEMENT = "0025_ferromex_sin_complemento"
COMPLEMENT_TYPES = (
    "SELECT code, is_active, deleted_at IS NOT NULL, deleted_by FROM invoice_document_types"
    " WHERE code LIKE 'PAYMENT_COMPLEMENT_%' ORDER BY code"
)


def test_migracion_da_de_baja_los_tipos_del_complemento(empty_db):
    config = alembic_config(empty_db)
    command.upgrade(config, PAYMENT)
    active = [("PAYMENT_COMPLEMENT_PDF", True, False, None), ("PAYMENT_COMPLEMENT_XML", True, False, None)]
    assert query(empty_db, COMPLEMENT_TYPES) == active
    command.upgrade(config, WITHOUT_COMPLEMENT)
    assert query(empty_db, COMPLEMENT_TYPES) == [
        ("PAYMENT_COMPLEMENT_PDF", False, True, None),
        ("PAYMENT_COMPLEMENT_XML", False, True, None),
    ]
    command.downgrade(config, PAYMENT)
    assert query(empty_db, COMPLEMENT_TYPES) == active


# --- RFC editable del proveedor -----------------------------------------------------------------------------------


def new_rfc(length: int = 12) -> str:
    """RFC con formato valido y letras al azar (unico en la prueba): moral de 12, fisica de 13."""
    letters = "".join(secrets.choice(string.ascii_uppercase) for _ in range(length - 9))
    return f"{letters}260101{secrets.choice(string.ascii_uppercase)}{secrets.randbelow(90) + 10}"


def edit_profile(client, supplier, **changes):
    form = {"business_name": supplier.business_name, **SUPPLIER_PROFILE_FORM, **changes}
    data = {**form, "csrf_token": csrf(client, "/")}
    return client.post(f"/suppliers/{supplier.id}/profile", data=data, follow_redirects=False)


def stored_supplier(supplier_id: int) -> Supplier:
    with SessionLocal() as db:
        return db.get(Supplier, supplier_id)


def test_edicion_del_rfc_con_sus_ordenes_de_compra(client, registered_suppliers, purchase_orders):
    old = new_rfc()
    (supplier,) = registered_suppliers(rfc=old)
    order = purchase_orders(rfc=old, supplier_name=supplier.business_name, supplier_id=supplier.id)
    login(client, ADMIN)
    form = client.get(f"/suppliers/{supplier.id}").text
    assert f'name="rfc" value="{old}"' in form and 'minlength="12" maxlength="12"' in form
    assert "El origen, el tipo de persona y el correo no se editan." in form
    rfc = new_rfc()
    assert edit_profile(client, supplier, rfc=f" {rfc.lower()} ").status_code == 303
    assert stored_supplier(supplier.id).rfc == rfc
    assert order_by_convenio(order.convenio).rfc == rfc
    with SessionLocal() as db:
        stmt = select(AuditLog).where(AuditLog.action == "SUPPLIER_UPDATED", AuditLog.entity_id == str(supplier.id))
        [entry] = db.scalars(stmt)
    assert entry.old_value["rfc"] == old and entry.new_value["rfc"] == rfc
    assert entry.new_value["purchase_orders"] == 1
    assert f'<dt>RFC</dt><dd class="mono">{rfc}</dd>' in client.get(f"/suppliers/{supplier.id}").text


@pytest.mark.parametrize(
    ("rfc", "message"),
    [
        ("ABC12", "RFC: tiene un formato inválido"),
        ("ABC261301AB1", "RFC: tiene un formato inválido"),  # mes 13
        ("XAXX010101000", "RFC: no se permite un RFC genérico"),
        ("ABCD260101AB1", "RFC: una persona moral debe tener un RFC de 12 caracteres"),
    ],
    ids=["formato", "fecha", "generico", "longitud"],
)
def test_rfc_invalido_conserva_lo_capturado(client, registered_suppliers, rfc, message):
    old = new_rfc()
    (supplier,) = registered_suppliers(rfc=old)
    login(client, ADMIN)
    response = edit_profile(client, supplier, rfc=rfc, contact_name="Contacto Capturado")
    assert response.status_code == 400
    page = html.unescape(response.text)
    assert message in page and f'value="{rfc}"' in page and 'value="Contacto Capturado"' in page
    assert stored_supplier(supplier.id).rfc == old


def test_rfc_de_otro_proveedor(client, registered_suppliers):
    (supplier,) = registered_suppliers(rfc=new_rfc())
    login(client, ADMIN)
    response = edit_profile(client, supplier, rfc=MORAL_RFC)
    assert response.status_code == 409 and "Ya existe un proveedor con ese RFC." in html.unescape(response.text)
    assert stored_supplier(supplier.id).rfc == supplier.rfc


def test_rfc_sin_cambios_no_se_valida(client, registered_suppliers):
    """Un RFC previo a estas reglas (el de la fabrica no tiene fecha valida) no impide editar lo demas."""
    (supplier,) = registered_suppliers()
    login(client, ADMIN)
    assert edit_profile(client, supplier, rfc=supplier.rfc, business_name="Nombre Nuevo SA de CV").status_code == 303
    saved = stored_supplier(supplier.id)
    assert (saved.rfc, saved.business_name) == (supplier.rfc, "Nombre Nuevo SA de CV")


def test_proveedor_internacional_sin_rfc_editable(client):
    foreign = supplier_by_email(INTERNATIONAL)
    login(client, ADMIN)
    page = client.get(f"/suppliers/{foreign.id}").text
    assert 'name="rfc"' not in page
    assert "El identificador fiscal, el país, el origen, el tipo de persona y el correo no se editan." in page
