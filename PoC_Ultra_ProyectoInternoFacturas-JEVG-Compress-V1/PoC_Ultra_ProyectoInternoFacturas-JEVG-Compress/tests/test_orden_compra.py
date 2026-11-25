"""Orden de compra (HU-24, spec orden-compra): entidad, reglas OC-001 a OC-012 y PRV-001 a PRV-003, consulta y
retiro de los contratos del portal."""

import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import String, cast, select, text, update
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models import AuditLog, Invoice, PurchaseOrder, Supplier, User
from app.rules.purchase_order_rules import (
    InvoiceFacts,
    OrderItem,
    OrderView,
    captured_reference,
    detect_order_number,
    international_facts,
    match_items,
    national_facts,
    purchase_order_rules,
    units_match,
)
from app.rules.supplier_identity_rules import supplier_identity_rules
from app.services import purchase_order_service
from app.services.submission_service import SubmissionOutcome, submit_invoice
from app.services.xml_service import parse_cfdi
from tests.cfdi import (
    EXAMPLE_NAME,
    EXAMPLE_PDF,
    EXAMPLE_RFC,
    EXAMPLE_TEXT,
    EXAMPLE_XML,
    MORAL_EMAIL,
    PHYSICAL_EMAIL,
    SUPPORT,
    example_cfdi,
    example_order,
    item,
    new_convenio,
    ready_invoice,
    register,
    reload,
    results,
    submit,
    upload,
    verify,
    xml_of,
)
from tests.conftest import ROOT, invoice_by_number, login, supplier_by_email

ALL = [f"OC-{n:03d}" for n in range(1, 13)]


def example_view(**changes) -> OrderView:
    items = changes.pop("items", None) or [item(EXAMPLE_TEXT, "3559.05", unit="PZA", material="E20080")]
    values = {
        "id": 1,
        "convenio": 25704872,
        "rfc": EXAMPLE_RFC,
        "supplier_name": EXAMPLE_NAME,
        "order_date": date(2025, 12, 9),
        "total": Decimal("3559.05"),
        "taxes": Decimal("569.45"),
        **changes,
    }
    return OrderView(items=tuple(OrderItem(i, values_) for i, values_ in enumerate(items, 1)), **values)


def example_data(**concept) -> dict:
    data = parse_cfdi(EXAMPLE_XML)
    data["concepts"][0].update(concept)
    return data


def evaluate(data=None, order=None, invoiced=(), **kwargs) -> dict:
    data = example_data() if data is None else data
    reference = detect_order_number(c.get("description") for c in data["concepts"])
    order = example_view() if order is None else order
    rows = purchase_order_rules(national_facts(data), reference, order or None, invoiced, **kwargs)
    return by_code(rows)


def by_code(rows) -> dict:
    grouped = {}
    for row in rows:
        grouped.setdefault(row.rule_code, []).append(row)
    return grouped


def statuses(grouped) -> dict:
    return {code: [row.status for row in rows] for code, rows in grouped.items()}


# --- Reglas puras: numero, partidas y unidades ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "description",
    ["LTH TIPO L-31T-900 AR BATERIA (OC/25704872)", "Bateria OC-25704872", "OC: 25704872", "oc 25704872 bateria"],
)
def test_numero_de_orden_en_la_descripcion(description):
    assert detect_order_number([description]).number == "25704872"


@pytest.mark.parametrize("description", ["Bateria sin orden", "OC/12345", "PROC 25704872", "OC/12345678901"])
def test_sin_numero_de_orden(description):
    assert detect_order_number([description]).number is None


def test_ordenes_distintas_en_los_conceptos():
    reference = detect_order_number(["Bateria (OC/25704872)", "Cable (OC/25704873)", "Sin orden"])
    assert reference.conflict and reference.cited == ("25704872", "25704873") and reference.number is None


def test_partida_mas_especifica_y_uso_unico():
    items = [OrderItem(1, item("BATERIA")), OrderItem(2, item("BATERIA LTH 900"))]
    concepts = [{"description": "BATERIA LTH 900 REFORZADA"}, {"description": "Bateria LTH 900 de repuesto"}]
    matches = match_items(concepts, items)
    assert [m.item.position if m.item else None for m in matches] == [2, 1]


def test_empate_de_partidas_es_ambiguo():
    items = [OrderItem(1, item("BATERIA")), OrderItem(2, item("BATERÍA"))]
    (match,) = match_items([{"description": "Bateria nueva"}], items)
    assert match.item is None and match.ambiguous


@pytest.mark.parametrize(
    ("unit_key", "unit", "sap", "expected"),
    [
        ("H87", "PZ", "PZA", True),
        ("E48", "Servicio", "SER", True),
        ("KGM", None, "KG", True),
        ("H87", "PZ", "SER", False),
    ],
)
def test_equivalencias_de_unidad(unit_key, unit, sap, expected):
    assert units_match(unit_key, unit, sap) is expected


# --- Reglas puras: OC-001 a OC-012 nacional (seccion 6.4) -------------------------------------------------------------


def test_factura_del_ejemplo_pasa_todas_las_reglas():
    grouped = evaluate()
    assert set(grouped) == set(ALL)
    assert all(status == "PASS" for rows in statuses(grouped).values() for status in rows)
    evidence = grouped["OC-009"][0].evidence
    assert evidence["convenio"] == 25704872 and evidence["item"]["Docto Material"] == "5000599999"
    assert grouped["OC-007"][0].source_reference == "Concepto 1"


def test_sin_numero_de_orden_de_compra():
    grouped = evaluate(example_data(description="LTH TIPO L-31T-900 AR BATERIA"))
    assert grouped["OC-001"][0].message == "No se encontró el número de orden de compra en los conceptos"
    assert {code: rows[0].status for code, rows in grouped.items() if code != "OC-001"} == dict.fromkeys(
        ALL[1:], "NOT_APPLICABLE"
    )
    assert grouped["OC-002"][0].message == "Sin orden de compra"


def test_orden_inexistente_para_el_proveedor():
    grouped = evaluate(order=False)
    assert grouped["OC-002"][0].status == "FAIL"
    assert grouped["OC-002"][0].message == "La orden de compra 25704872 no existe para el proveedor"
    assert all(grouped[code][0].status == "NOT_APPLICABLE" for code in ALL[2:])


def test_rfc_y_nombre_distintos_de_la_orden():
    grouped = evaluate(order=example_view(rfc="XAXX010101000", supplier_name="Otro proveedor"))
    assert (grouped["OC-003"][0].status, grouped["OC-003"][0].severity) == ("FAIL", "CRITICAL")
    assert grouped["OC-004"][0].message == "Nombre no coincide con la orden de compra"


def test_subtotal_distinto():
    data = example_data()
    data["subtotal"] = Decimal("3600.00")
    rule = evaluate(data)["OC-005"][0]
    assert (rule.status, rule.expected_value, rule.detected_value) == ("FAIL", "3559.05", "3600.00")
    assert rule.message == "Subtotal 3600.00 distinto del total de la orden de compra 3559.05"


def test_iva_distinto():
    data = example_data()
    data["concepts"][0]["taxes"][0]["amount"] = Decimal("570.00")
    assert evaluate(data)["OC-006"][0].status == "FAIL"


def test_iva_del_comprobante_sin_detalle_por_concepto():
    data = example_data(taxes=[])
    data["tax"] = Decimal("569.45")
    assert evaluate(data)["OC-006"][0].status == "PASS"


def test_concepto_sin_partida():
    grouped = evaluate(example_data(description="BATERIA LTH L-40 (OC/25704872)", identification=None))
    assert grouped["OC-007"][0].message == "Concepto 1: sin partida en la orden de compra"
    assert [grouped[code][0].status for code in ("OC-008", "OC-009", "OC-011")] == ["NOT_APPLICABLE"] * 3


def test_txt_brv_con_espacios_distintos():
    grouped = evaluate(example_data(description="LTH TIPO L-31T-900 AR BATERIA (OC/25704872)", identification=None))
    assert grouped["OC-007"][0].status == "PASS"


def test_cantidad_distinta():
    rule = evaluate(example_data(quantity=Decimal("2")))["OC-008"][0]
    assert (rule.status, rule.message) == ("FAIL", "Concepto 1: cantidad 2 vs 1")


def test_unidad_distinta():
    rule = evaluate(example_data(unit_key="E48", unit="Servicio"))["OC-008"][0]
    assert rule.status == "FAIL" and "unidad E48 - Servicio vs PZA" in rule.message


def test_importe_distinto():
    rule = evaluate(example_data(amount=Decimal("3600.00"), unit_value=Decimal("3600.00")))["OC-009"][0]
    assert (rule.status, rule.message) == ("FAIL", "Concepto 1: importe 3600.00 vs 3559.05")


def test_diferencia_de_redondeo():
    assert evaluate(example_data(amount=Decimal("3559.06")))["OC-009"][0].status == "PASS"


def test_precio_unitario_distinto():
    rule = evaluate(example_data(unit_value=Decimal("3500.00")))["OC-009"][0]
    assert (rule.status, rule.message) == ("FAIL", "Concepto 1: precio unitario 3500.00 vs 3559.05")


def test_moneda_distinta():
    data = example_data()
    data["currency"] = "USD"
    assert evaluate(data)["OC-010"][0].status == "FAIL"


def test_mercancia_no_entregada():
    order = example_view(items=[item(EXAMPLE_TEXT, "3559.05", unit="PZA", delivered=False)])
    rule = evaluate(order=order)["OC-011"][0]
    assert (rule.status, rule.message) == ("FAIL", "Concepto 1: la partida no tiene entrada de mercancía")


def test_orden_ya_facturada():
    rule = evaluate(invoiced=["FAC-2026-00001"])["OC-012"][0]
    assert (rule.status, rule.severity, rule.message) == (
        "FAIL",
        "CRITICAL",
        "La orden de compra ya tiene la factura FAC-2026-00001",
    )


def test_dos_conceptos_contra_dos_partidas():
    data = example_data()
    second = {**data["concepts"][0], "description": "CABLE PUENTE 2M (OC/25704872)", "identification": None}
    data["concepts"].append(second)
    order = example_view(
        items=[item(EXAMPLE_TEXT, "3559.05", unit="PZA"), item("CABLE PUENTE 2M", "3559.05", unit="PZA")]
    )
    grouped = evaluate(data, order)
    assert [row.source_reference for row in grouped["OC-007"]] == ["Concepto 1", "Concepto 2"]
    assert statuses(grouped)["OC-007"] == ["PASS", "PASS"]


# --- Reglas puras: internacional (seccion 6.7) y PRV --------------------------------------------------------------


def foreign_invoice(**changes):
    values = {"subtotal": Decimal("18000.00"), "tax": Decimal("0.00"), "currency": "USD"}
    return SimpleNamespace(**{**values, **changes})


def foreign_order(**changes) -> OrderView:
    return example_view(
        rfc="XEXX010101000",
        supplier_name="Global Data Services Inc. (DEMO)",
        total=Decimal("18000.00"),
        taxes=Decimal("0.00"),
        items=[item("DATA ANALYTICS CONSULTING", "18000.00", currency="USD")],
        **changes,
    )


def test_invoice_internacional_que_cuadra():
    supplier = SimpleNamespace(business_name="Global Data Services Inc. (DEMO)")
    rows = purchase_order_rules(
        international_facts(foreign_invoice(), supplier),
        captured_reference("45009042"),
        foreign_order(),
        international=True,
    )
    result = {row.rule_code: row.status for row in rows}
    assert result == {
        **dict.fromkeys(["OC-001", "OC-002", "OC-004", "OC-005", "OC-006", "OC-010", "OC-011", "OC-012"], "PASS"),
        **dict.fromkeys(["OC-003", "OC-007", "OC-008", "OC-009"], "NOT_APPLICABLE"),
    }


def test_invoice_internacional_con_otro_nombre_es_advertencia():
    supplier = SimpleNamespace(business_name="Otra razon social")
    rows = purchase_order_rules(
        international_facts(foreign_invoice(), supplier),
        captured_reference("45009042"),
        foreign_order(),
        international=True,
    )
    rule = next(row for row in rows if row.rule_code == "OC-004")
    assert (rule.status, rule.severity) == ("WARNING", "WARNING")


def test_invoice_internacional_sin_numero_de_orden():
    rows = purchase_order_rules(InvoiceFacts(None, None, None), captured_reference("PO-42"), None, international=True)
    assert rows[0].message == "Capture el número de orden de compra" and rows[0].status == "FAIL"


SUPPLIER = SimpleNamespace(rfc=EXAMPLE_RFC, business_name=EXAMPLE_NAME)
REGIMES = {"601", "612"}


def prv(data, regimes=REGIMES):
    return {row.rule_code: row for row in supplier_identity_rules(data, SUPPLIER, regimes)}


def test_datos_del_proveedor_correctos():
    assert {code: row.status for code, row in prv(parse_cfdi(EXAMPLE_XML)).items()} == dict.fromkeys(
        ("PRV-001", "PRV-002", "PRV-003"), "PASS"
    )


def test_rfc_emisor_de_otro_proveedor():
    rule = prv({**parse_cfdi(EXAMPLE_XML), "issuer_rfc": "TIC210101ABC"})["PRV-001"]
    assert (rule.status, rule.severity) == ("FAIL", "CRITICAL")
    assert rule.message == "El RFC emisor TIC210101ABC no corresponde al proveedor GOHS60031745A"


@pytest.mark.parametrize("name", ["Socorro Patricia González Hernández", "SOCORRO PATRICIA, GONZALEZ HERNANDEZ."])
def test_nombre_con_acentos_mayusculas_y_signos(name):
    assert prv({**parse_cfdi(EXAMPLE_XML), "issuer_name": name})["PRV-002"].status == "PASS"


def test_razon_social_con_signos():
    supplier = SimpleNamespace(rfc="TIC210101ABC", business_name="Tecnologia Integral del Centro SA de CV")
    data = {
        "issuer_rfc": "TIC210101ABC",
        "issuer_name": "TECNOLOGIA INTEGRAL DEL CENTRO, S.A. DE C.V.",
        "issuer_regime": "601",
    }
    rows = {row.rule_code: row.status for row in supplier_identity_rules(data, supplier, REGIMES)}
    assert rows["PRV-002"] == "PASS"


def test_sin_regimen_y_regimen_inactivo():
    assert (
        prv({**parse_cfdi(EXAMPLE_XML), "issuer_regime": None})["PRV-003"].message
        == "Falta el régimen fiscal del emisor"
    )
    assert prv(parse_cfdi(EXAMPLE_XML), {"601"})["PRV-003"].message == "Régimen fiscal 612 no válido"


def test_prv_no_aplica_al_internacional():
    rows = supplier_identity_rules(None, SUPPLIER, REGIMES, international=True)
    assert [row.status for row in rows] == ["NOT_APPLICABLE"] * 3


# --- Entidad e integridad -----------------------------------------------------------------------------------------


def insert_order(db, **changes):
    values = {
        "convenio": new_convenio(),
        "rfc": EXAMPLE_RFC,
        "supplier_name": EXAMPLE_NAME,
        "order_date": date(2026, 1, 1),
        "total": Decimal("1.00"),
        "taxes": Decimal("0.00"),
        "data": {"items": [item()]},
        **changes,
    }
    db.add(PurchaseOrder(**values))
    db.flush()


@pytest.mark.parametrize(
    "changes",
    [
        {"convenio": 25704872},
        {"total": Decimal("0.00")},
        {"taxes": Decimal("-1.00")},
        {"convenio": 0},
        {"rfc": "ABC123"},
        {"data": {"items": []}},
        {"data": {"partidas": [1]}},
    ],
)
def test_integridad_de_la_orden_de_compra(changes):
    with SessionLocal() as db, pytest.raises(IntegrityError):
        insert_order(db, **changes)


def test_borrado_de_una_orden_facturada():
    order_id = invoice_by_number("REVISION-001").purchase_order_id
    assert order_id is not None
    with SessionLocal() as db, pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM purchase_orders WHERE id = :id"), {"id": order_id})


def test_partida_sin_txt_brv():
    broken = {key: value for key, value in item().items() if key != "Txt.brv"}
    with pytest.raises(ValueError, match="Txt.brv"):
        purchase_order_service.validate_items({"items": [broken]})


# --- Datos demo ---------------------------------------------------------------------------------------------------


def test_orden_del_ejemplo_sembrada():
    with SessionLocal() as db:
        order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.convenio == 25704872))
        assert (order.rfc, order.total, order.taxes) == (EXAMPLE_RFC, Decimal("3559.05"), Decimal("569.45"))
        (sap_item,) = order.data["items"]
        assert sap_item["Docto Material"] == "5000527117" and sap_item["Txt.brv"] == EXAMPLE_TEXT
        assert order.supplier_id == supplier_by_email(PHYSICAL_EMAIL).id
        foreign = db.scalar(select(PurchaseOrder).where(PurchaseOrder.convenio == 45009042))
        assert foreign.supplier_id == supplier_by_email("proveedor3@poc.local").id
        assert {i["Moneda"] for i in foreign.data["items"]} == {"USD"}
        delivered = [all(i["Docto Material"] for i in o.data["items"]) for o in db.scalars(select(PurchaseOrder))]
        assert False in delivered
        assert any(len(o.data["items"]) == 2 for o in db.scalars(select(PurchaseOrder)))


def test_proveedor_fisico_demo_es_el_del_ejemplo():
    supplier = supplier_by_email(PHYSICAL_EMAIL)
    assert (supplier.rfc, supplier.business_name) == (EXAMPLE_RFC, EXAMPLE_NAME)


def test_facturas_demo_sin_contrato_y_ligadas_a_su_orden():
    # Las que sembro seed_db (las demas pruebas de la sesion tambien crean facturas con folios FAC-2026-000xx).
    seeded = select(AuditLog.entity_id).where(AuditLog.action == "DEMO_SEEDED", AuditLog.entity == "Invoice")
    with SessionLocal() as db:
        demo = list(db.scalars(select(Invoice).where(cast(Invoice.id, String).in_(seeded))))
        assert demo and all(invoice.contract_id is None for invoice in demo)
        sent = [invoice for invoice in demo if invoice.submitted_at is not None]
        assert sent and all(invoice.purchase_order_id for invoice in sent)


# --- Consulta para PMO y Administrador ----------------------------------------------------------------------------


def test_busqueda_por_convenio(client):
    login(client, "pmo@poc.local")
    page = client.get("/purchase-orders", params={"q": "25704872"}).text
    assert re.findall(r'href="/purchase-orders/(\d+)"><strong>(\d+)</strong>', page)[0][1] == "25704872"
    assert len(set(re.findall(r'href="/purchase-orders/(\d+)"><strong>', page))) == 1


def test_busqueda_por_nombre(client):
    login(client, "pmo@poc.local")
    page = client.get("/purchase-orders", params={"q": "gonzalez"}).text
    assert "25704872" in page and "45001001" not in page


def test_detalle_con_partidas(client):
    login(client, "admin@poc.local")
    with SessionLocal() as db:
        order_id = db.scalar(select(PurchaseOrder.id).where(PurchaseOrder.convenio == 25704872))
    page = client.get(f"/purchase-orders/{order_id}")
    assert page.status_code == 200
    for value in (
        "E20080",
        EXAMPLE_TEXT,
        "PZA",
        "30.12.2025",
        "3559.05",
        "MXN",
        "ELECTRICO",
        "GUADALAJARA_1 STATION 1",
        "5000527117",
        "16.12.2025",
        "Facturas ligadas",
    ):
        assert value in page.text, value


def test_proveedor_sin_acceso_a_ordenes_de_compra(client):
    login(client, MORAL_EMAIL)
    assert client.get("/purchase-orders").status_code == 403
    assert client.get("/purchase-orders/1").status_code == 403


def test_orden_inexistente(client):
    login(client, "pmo@poc.local")
    assert client.get("/purchase-orders/999999").status_code == 404


def test_pagina_fuera_de_rango(client, purchase_orders):
    for _ in range(10):
        purchase_orders()
    login(client, "admin@poc.local")
    page = client.get("/purchase-orders", params={"page": 99}).text
    assert re.search(r"Página 2 de 2 · \d+ registros", page)


@pytest.mark.parametrize(
    ("email", "visible", "hidden"),
    [
        ("pmo@poc.local", ["Órdenes de compra"], ["Contratos", "Alta de contrato", "Requisitos mínimos"]),
        ("admin@poc.local", ["Órdenes de compra", "Archivos de factura", "Alta de proveedor"], ["Alta de contrato"]),
        (MORAL_EMAIL, [], ["Órdenes de compra", "Proveedores", "Contratos"]),
    ],
)
def test_menu_por_rol(client, email, visible, hidden):
    login(client, email)
    nav = client.get("/").text.split("<nav>")[1].split("</nav>")[0]
    assert all(text in nav for text in visible) and not any(text in nav for text in hidden)


# --- Envio de la factura del ejemplo y orden ya facturada ------------------------------------------------------------


@pytest.fixture()
def example_provider(client):
    login(client, PHYSICAL_EMAIL)
    return client


def test_factura_del_ejemplo_solo_con_pdf(example_provider):
    response = register(example_provider, EXAMPLE_PDF)
    assert response.status_code == 303
    invoice = invoice_by_number("3668")
    assert response.headers["location"] == f"/invoices/{invoice.id}/data"
    assert (invoice.status, invoice.service_period, invoice.uuid, invoice.currency) == (
        "DRAFT",
        "01/2026",
        "A328F91A-DDDD-4624-89AC-877819F5B540",
        "MXN",
    )
    assert (invoice.subtotal, invoice.tax, invoice.total) == (Decimal("3559.05"), Decimal("569.45"), Decimal("4128.50"))
    assert invoice.purchase_order_number == "25704872"
    review = example_provider.get(f"/invoices/{invoice.id}/data").text
    assert 'src="/invoices/{}/documents/'.format(invoice.id) in review and "/pages/1" in review
    for code in ("PRV-001", "PRV-002", "PRV-003", "XML-002", "XML-005", "XML-009", "XML-011"):
        assert f'class="data-check ok" data-rule="{code}"' in review, code
    assert "Orden de compra detectada: <strong>25704872</strong>" in review
    assert upload(example_provider, invoice, "APPROVAL", "vobo.txt", SUPPORT).status_code == 303
    assert submit(example_provider, invoice).status_code == 303
    stored = results(invoice)
    assert {code: stored[code].status for code in ALL} == dict.fromkeys(ALL, "PASS")
    assert stored["XML-001"].status == "NOT_APPLICABLE"
    sent = reload(invoice)
    with SessionLocal() as db:
        assert sent.status == "UNDER_REVIEW" and db.get(PurchaseOrder, sent.purchase_order_id).convenio == 25704872
    login(example_provider, "pmo@poc.local")
    detail = example_provider.get(f"/invoices/{invoice.id}").text
    assert f'href="/purchase-orders/{sent.purchase_order_id}">25704872</a>' in detail and EXAMPLE_TEXT in detail
    assert "Contrato" not in detail and "Conciliacion contractual" not in detail


def test_orden_de_otro_proveedor(client, purchase_orders):
    login(client, MORAL_EMAIL)
    order = example_order(purchase_orders)
    invoice, _ = ready_invoice(client, purchase_orders, order=order)
    assert submit(client, invoice).status_code == 409
    rule = results(invoice)["OC-002"]
    assert (rule.status, rule.message) == ("FAIL", f"La orden de compra {order.convenio} no existe para el proveedor")


def test_orden_ya_facturada_y_liberada_al_cancelar(client, purchase_orders):
    login(client, MORAL_EMAIL)
    first, order = ready_invoice(client, purchase_orders)
    assert submit(client, first).status_code == 303
    second, _ = ready_invoice(client, purchase_orders, order=order)
    assert submit(client, second).status_code == 409
    rule = results(second)["OC-012"]
    assert rule.status == "FAIL" and reload(first).internal_folio in rule.message
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.execute(
            update(Invoice)
            .where(Invoice.id == first.id)
            .values(
                status="CANCELLED",
                cancelled_at=now,
                cancelled_by=db.scalar(select(User.id).where(User.email == MORAL_EMAIL)),
                cancellation_deadline=now + timedelta(hours=72),
            )
        )
        db.commit()
    assert submit(client, second).status_code == 303
    assert results(second)["OC-012"].status == "PASS"


def test_verificar_no_liga_la_orden(client, purchase_orders):
    login(client, MORAL_EMAIL)
    invoice, _ = ready_invoice(client, purchase_orders)
    assert verify(client, invoice).status_code == 303
    assert results(invoice)["OC-012"].status == "PASS"
    assert reload(invoice).purchase_order_id is None


def test_envios_simultaneos_contra_la_misma_orden(client, purchase_orders):
    """El FOR UPDATE sobre la orden serializa los envios: el segundo espera al primero y ve su liga (RD-16)."""
    login(client, MORAL_EMAIL)
    first, order = ready_invoice(client, purchase_orders)
    second, _ = ready_invoice(client, purchase_orders, order=order)
    user_id = supplier_user_id()
    outcome = {}

    def send_second():
        with SessionLocal() as db:
            outcome["second"] = submit_invoice(db, db.get(Invoice, second.id), user_id)
            db.commit()

    with SessionLocal() as db:
        assert submit_invoice(db, db.get(Invoice, first.id), user_id).outcome == SubmissionOutcome.SUBMITTED
        worker = threading.Thread(target=send_second)
        worker.start()
        time.sleep(1)
        assert worker.is_alive(), "el segundo envio debe esperar el bloqueo de la orden"
        db.commit()
    worker.join(30)
    assert outcome["second"].outcome == SubmissionOutcome.RULES_FAILED
    assert "OC-012" in {failure.rule_code for failure in outcome["second"].failures}
    assert reload(first).purchase_order_id == order.id and reload(second).purchase_order_id is None


def supplier_user_id() -> int:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == MORAL_EMAIL))


# --- Contratos conservados sin uso ------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/contracts", "/contracts/1", "/admin/contract-requirements"])
def test_rutas_de_contratos_retiradas(client, path):
    login(client, "admin@poc.local")
    assert client.get(path).status_code == 404


def test_factura_nueva_sin_contrato(client, purchase_orders):
    login(client, MORAL_EMAIL)
    invoice, _ = ready_invoice(client, purchase_orders)
    assert invoice.contract_id is None


def test_ningun_modulo_usa_los_modelos_de_contratos():
    """Los modelos se conservan solo para el esquema (P-02): ni el portal, ni los scripts, ni las pruebas los usan."""
    # El nombre como identificador; como texto (p. ej. la entidad "Contract" de una auditoria historica) no cuenta.
    pattern = re.compile(r"(?<![\"'])\b(Contract|ContractAmendment|ContractDocumentType)\b(?![\"'])")
    offenders = []
    for folder in ("app", "scripts", "tests"):
        for path in (ROOT / folder).rglob("*.py"):
            relative = path.relative_to(ROOT)
            if relative.parts[:2] == ("app", "models") or path == Path(__file__):
                continue
            if pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(str(relative))
    assert offenders == []


def test_registro_del_ejemplo_con_xml_de_otra_factura(client):
    login(client, PHYSICAL_EMAIL)
    other = example_cfdi()
    response = register(client, EXAMPLE_PDF, xml_of(other))
    assert response.status_code == 409
    assert "El PDF y el XML no corresponden a la misma factura" in response.text
    assert invoice_by_number(other["folio"]) is None


def test_orden_del_recorrido_sin_proveedor_dado_de_alta():
    """Una orden nacional sembrada antes del alta de su proveedor se encuentra por su RFC (recorrido manual)."""
    with SessionLocal() as db:
        order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.convenio == 45000451))
        assert order.rfc == "GAVH810417Q42" and order.supplier_id is None
        assert db.scalar(select(Supplier.id).where(Supplier.rfc == "GAVH810417Q42")) is None
