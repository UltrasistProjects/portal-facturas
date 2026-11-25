"""Factura del proveedor internacional: datos del Invoice con su orden de compra, duplicados por nombre de archivo y
validacion (HU-15, HU-16 y HU-24, specs factura-internacional, motor-validacion y orden-compra)."""

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import fitz
import pytest
from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.constants import InvoiceStatus, Role, SupplierOrigin, SupplierStatus, SupplierType
from app.core.database import SessionLocal
from app.core.timeutils import to_business
from app.models import AuditLog, Document, Invoice, Supplier, User, ValidationResult, ValidationRule, now_utc
from app.services.foreign_invoice_service import MSG_NOT_INTERNATIONAL
from tests.cfdi import item
from tests.conftest import csrf, identity_account, invoice_by_number, login, supplier_by_email

INTERNATIONAL = "proveedor3@poc.local"  # proveedor internacional demo del seed (D11)
# Orden de compra sembrada del proveedor internacional demo (45009042); los envios usan una orden propia.
AMOUNTS = {
    "purchase_order_number": "45009042",
    "invoice_date": "2026-09-15",
    "subtotal": "1,000.00",
    "tax": "0.00",
    "total": "1000",
    "currency": "USD",
}
FOREIGN_NAME = "Global Data Services Inc. (DEMO)"
INVOICE_TEXT = [
    "INVOICE - Global Data Services Inc.",
    "Tax ID: 98-7654321",
    "Bill to: INTERMODAL MEXICO, S.A. de C.V.",
    "Av. Insurgentes Sur 1, Ciudad de Mexico, C.P. 11700",
    "Total USD 1,000.00",
]
TXT = b"Documento de prueba"


# --- Utilidades ---------------------------------------------------------------------------------------------------


def pdf(lines: list[str]) -> bytes:
    """PDF real con esas lineas de texto; sin lineas, una pagina sin capa de texto (como un escaneo)."""
    document = fitz.open()
    page = document.new_page()
    for index, line in enumerate(lines):
        page.insert_text((72, 90 + 20 * index), line, fontsize=11)
    content = document.tobytes()
    document.close()
    return content


def register(client, email: str = INTERNATIONAL, **overrides):
    """Alta de una factura con numero unico; devuelve (respuesta, numero)."""
    number = f"HU15-{uuid4().hex[:10]}"
    data = {"invoice_number": number, **AMOUNTS, **overrides, "csrf_token": csrf(client, "/invoices/new")}
    return client.post("/invoices/new", data=data, follow_redirects=False), number


def new_invoice(client, email: str = INTERNATIONAL, **overrides) -> Invoice:
    response, number = register(client, email, **overrides)
    assert response.status_code == 303, response.text
    return invoice_by_number(number)


def upload(client, invoice_id: int, document_type: str, filename: str, content: bytes):
    return client.post(
        f"/invoices/{invoice_id}/documents",
        data={"document_type": document_type, "csrf_token": csrf(client, f"/invoices/{invoice_id}")},
        files={"upload": (filename, content, "application/octet-stream")},
        follow_redirects=False,
    )


def complete(client, invoice_id: int, invoice_pdf: bytes, filename: str | None = None) -> None:
    """Invoice y Vo.Bo.: los obligatorios iniciales del internacional (la orden de compra ya no es un archivo)."""
    name = filename or f"INV-{uuid4().hex[:8]}.pdf"
    assert upload(client, invoice_id, "FOREIGN_INVOICE", name, invoice_pdf).status_code == 303
    assert upload(client, invoice_id, "APPROVAL", "vobo.txt", TXT).status_code == 303


def foreign_order(purchase_orders, supplier_email: str = INTERNATIONAL, **changes):
    """Orden de compra en USD del proveedor internacional, ligada por supplier_id, que cuadra con AMOUNTS."""
    values = {
        "rfc": "XEXX010101000",
        "supplier_name": FOREIGN_NAME,
        "total": "1000.00",
        "taxes": "0.00",
        "items": [item("DATA ANALYTICS CONSULTING", "1000.00", currency="USD")],
        "supplier_id": supplier_by_email(supplier_email).id,
        **changes,
    }
    return purchase_orders(**values)


def post(client, path: str, data: dict | None = None):
    return client.post(path, data={**(data or {}), "csrf_token": csrf(client, "/")}, follow_redirects=False)


def results(invoice_id: int) -> dict[str, ValidationResult]:
    with SessionLocal() as db:
        rows = db.scalars(select(ValidationResult).where(ValidationResult.invoice_id == invoice_id))
        return {row.rule_code: row for row in rows}


def invoice(invoice_id: int) -> Invoice:
    with SessionLocal() as db:
        return db.get(Invoice, invoice_id)


def set_status(invoice_id: int, status: InvoiceStatus) -> None:
    with SessionLocal() as db:
        db.execute(update(Invoice).where(Invoice.id == invoice_id).values(status=status))
        db.commit()


def stored_files(invoice_id: int) -> list:
    folder = settings.storage_path / "invoices" / str(invoice_id)
    return sorted(folder.iterdir()) if folder.exists() else []


def amount_audits(invoice_id: int) -> list[AuditLog]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(AuditLog).where(
                    AuditLog.action == "INVOICE_AMOUNTS_UPDATED", AuditLog.entity_id == str(invoice_id)
                )
            )
        )


@pytest.fixture()
def other_international():
    """Segundo proveedor internacional autorizado, con usuario; se reutiliza entre pruebas."""
    email = "otro.internacional@poc.local"
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email)) is None:
            supplier = Supplier(
                business_name="Otro Proveedor Internacional LLC",
                supplier_type=SupplierType.PERSONA_MORAL,
                email=email,
                origin=SupplierOrigin.INTERNATIONAL,
                rfc=None,
                foreign_tax_id=f"OT-{uuid4().hex[:8]}",
                country="CA",
                status=SupplierStatus.ACTIVE,
            )
            db.add(supplier)
            db.flush()
            db.add(
                User(
                    name="Otro internacional",
                    email=email,
                    keycloak_sub=identity_account(email, Role.PROVEEDOR),
                    role=Role.PROVEEDOR,
                    supplier_id=supplier.id,
                )
            )
            db.commit()
    return email


# --- Datos del Invoice en el registro -----------------------------------------------------------------------------


def test_formulario_internacional_con_datos_del_invoice(client):
    login(client, INTERNATIONAL)
    page = client.get("/invoices/new").text
    assert "Datos del Invoice" in page and 'name="invoice_date"' in page and 'name="purchase_order_number"' in page
    for field in ("contract_id", "service_period", "project_name", "project_leader"):
        assert f'name="{field}"' not in page


def test_registro_de_un_invoice(client):
    login(client, INTERNATIONAL)
    response, number = register(client)
    created = invoice_by_number(number)
    assert response.headers["location"] == f"/invoices/{created.id}/documents"
    assert created.status == InvoiceStatus.DRAFT
    assert (created.invoice_date, created.subtotal, created.tax, created.total, created.currency) == (
        date(2026, 9, 15),
        Decimal("1000.00"),
        Decimal("0.00"),
        Decimal("1000.00"),
        "USD",
    )
    assert (created.service_period, created.purchase_order_number, created.contract_id) == ("09/2026", "45009042", None)


@pytest.mark.parametrize("number", ["", "PO-42", "12345", "12345678901"])
def test_sin_numero_de_orden_de_compra(client, number):
    login(client, INTERNATIONAL)
    response, created = register(client, purchase_order_number=number)
    assert response.status_code == 400 and "Capture el número de orden de compra" in response.text
    assert invoice_by_number(created) is None


def test_total_manipulado_por_el_cliente(client):
    """El total no se captura: el servidor lo calcula (subtotal + impuestos) e ignora el que envie el cliente."""
    login(client, INTERNATIONAL)
    response, number = register(client, subtotal="1000.00", tax="160.00", total="1.00")
    assert response.status_code == 303
    assert invoice_by_number(number).total == Decimal("1160.00")


def test_total_de_solo_lectura_en_el_formulario(client):
    login(client, INTERNATIONAL)
    page = client.get("/invoices/new").text
    assert re.search(r'<input id="total" class="form-control" value="" readonly', page)
    assert 'name="total"' not in page and "/static/js/invoice_amounts.js" in page


def test_moneda_inexistente_por_peticion_directa(client):
    login(client, INTERNATIONAL)
    response, number = register(client, currency="XYZ")
    assert response.status_code == 400 and "Moneda: la clave no está activa en el catálogo" in response.text
    assert invoice_by_number(number) is None


def test_moneda_inactiva(client):
    login(client, INTERNATIONAL)
    response, number = register(client, currency="JPY")
    assert response.status_code == 400 and "Moneda: la clave no está activa en el catálogo" in response.text
    assert invoice_by_number(number) is None


def test_fecha_futura(client):
    login(client, INTERNATIONAL)
    tomorrow = to_business(datetime.now(timezone.utc)).date() + timedelta(days=1)
    response, number = register(client, invoice_date=tomorrow.isoformat())
    assert response.status_code == 400 and "Fecha de la factura: no puede ser posterior a hoy" in response.text
    assert invoice_by_number(number) is None


def test_varios_errores_juntos(client):
    login(client, INTERNATIONAL)
    response, _ = register(client, subtotal="", tax="-1", currency="US")
    assert response.status_code == 400
    assert "Subtotal: es obligatorio" in response.text and "Impuestos: no puede ser negativo" in response.text
    assert "Moneda: tiene un formato invalido" in response.text


def test_proveedor_nacional_sin_datos_del_invoice(client):
    login(client, "proveedor1@poc.local")
    page = client.get("/invoices/new").text
    assert "Datos del Invoice" not in page and 'name="pdf"' in page
    response, number = register(client, "proveedor1@poc.local")  # sin archivos: el nacional registra por su PDF
    assert response.status_code == 400 and "Adjunte el PDF de la factura" in response.text
    assert invoice_by_number(number) is None


# --- Edicion de los datos del Invoice -----------------------------------------------------------------------------


def edit(client, invoice_id: int, **values):
    return post(client, f"/invoices/{invoice_id}/amounts", {**AMOUNTS, **values})


def test_formulario_en_la_carga_documental(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    page = client.get(f"/invoices/{created.id}/documents").text
    assert 'action="/invoices/' + str(created.id) + '/amounts"' in page
    assert 'value="2026-09-15"' in page and 'value="1000.00"' in page and 'value="45009042"' in page


def test_correccion_de_la_orden_de_compra(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    assert edit(client, created.id, purchase_order_number="45009043").status_code == 303
    assert invoice(created.id).purchase_order_number == "45009043"
    [entry] = amount_audits(created.id)
    assert entry.old_value == {"purchase_order_number": "45009042"}
    assert entry.new_value == {"purchase_order_number": "45009043"}


def test_orden_propuesta_desde_el_invoice(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    with SessionLocal() as db:
        db.execute(update(Invoice).where(Invoice.id == created.id).values(purchase_order_number=None))
        db.commit()
    upload(client, created.id, "FOREIGN_INVOICE", f"INV-{uuid4().hex[:6]}.pdf", pdf([*INVOICE_TEXT, "PO: OC/45009001"]))
    page = client.get(f"/invoices/{created.id}/documents").text
    assert 'name="purchase_order_number" class="form-control" inputmode="numeric"' in page
    assert 'value="45009001"' in page


def test_correccion_tras_observaciones(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    set_status(created.id, InvoiceStatus.REQUIRES_CORRECTION)
    response = edit(client, created.id, tax="160.00", total="1,160.00")
    assert response.headers["location"] == f"/invoices/{created.id}/documents?notice=amounts_saved"
    assert "Datos del Invoice guardados" in client.get(response.headers["location"]).text
    updated = invoice(created.id)
    assert (updated.tax, updated.total, updated.status) == (
        Decimal("160.00"),
        Decimal("1160.00"),
        InvoiceStatus.REQUIRES_CORRECTION,
    )
    [entry] = amount_audits(created.id)
    assert entry.old_value == {"tax": "0.00", "total": "1000.00"}
    assert entry.new_value == {"tax": "160.00", "total": "1160.00"}


def test_edicion_sin_cambios_sin_auditoria(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    response = edit(client, created.id)
    assert response.headers["location"].endswith("notice=amounts_unchanged") and amount_audits(created.id) == []


def test_edicion_con_errores(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    response = edit(client, created.id, tax="-1")
    assert response.status_code == 400 and "Impuestos: no puede ser negativo" in response.text
    assert invoice(created.id).total == Decimal("1000.00")


def test_total_manipulado_en_la_edicion(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    assert edit(client, created.id, subtotal="500.00", tax="80.00", total="999.99").status_code == 303
    assert (invoice(created.id).subtotal, invoice(created.id).total) == (Decimal("500.00"), Decimal("580.00"))


def test_edicion_de_factura_enviada(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    set_status(created.id, InvoiceStatus.UNDER_REVIEW)
    assert edit(client, created.id, total="1000.01", tax="0.01").status_code == 409
    assert invoice(created.id).total == Decimal("1000.00")


def test_edicion_por_otro_rol(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, "pmo@poc.local")
    assert edit(client, created.id, tax="160.00", total="1160.00").status_code == 403
    assert invoice(created.id).total == Decimal("1000.00")


def test_edicion_de_factura_nacional(client):
    login(client, "proveedor1@poc.local")
    created = invoice_by_number("A-CORRECTA")
    response = edit(client, created.id)
    assert response.status_code == 400 and MSG_NOT_INTERNATIONAL in response.text


# --- Invoice duplicado por nombre de archivo ----------------------------------------------------------------------


def test_invoice_repetido_en_otra_factura(client):
    login(client, INTERNATIONAL)
    first, second = new_invoice(client), new_invoice(client)
    name = f"INV-{uuid4().hex[:6]}"
    assert upload(client, first.id, "FOREIGN_INVOICE", f"{name}.pdf", pdf(INVOICE_TEXT)).status_code == 303
    response = upload(client, second.id, "FOREIGN_INVOICE", f"  {name.lower()}.PDF", pdf(INVOICE_TEXT))
    assert response.status_code == 409
    assert f"Ya existe una factura con un Invoice llamado «{name.lower()}.PDF»: {first.internal_folio}" in response.text
    assert stored_files(second.id) == []


def test_reemplazo_en_la_misma_factura(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    name = f"INV-{uuid4().hex[:6]}.pdf"
    assert upload(client, created.id, "FOREIGN_INVOICE", name, pdf(INVOICE_TEXT)).status_code == 303
    assert upload(client, created.id, "FOREIGN_INVOICE", name, pdf(INVOICE_TEXT)).status_code == 303
    with SessionLocal() as db:
        current = db.scalar(
            select(func.count(Document.id)).where(Document.invoice_id == created.id, Document.is_current.is_(True))
        )
    assert current == 1


def test_mismo_nombre_en_otro_proveedor(client, other_international):
    name = f"INV-{uuid4().hex[:6]}.pdf"
    login(client, INTERNATIONAL)
    assert upload(client, new_invoice(client).id, "FOREIGN_INVOICE", name, pdf(INVOICE_TEXT)).status_code == 303
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, other_international)
    other = new_invoice(client, other_international)
    assert upload(client, other.id, "FOREIGN_INVOICE", name, pdf(INVOICE_TEXT)).status_code == 303


def test_duplicado_detectado_al_enviar(client):
    login(client, INTERNATIONAL)
    first, second = new_invoice(client), new_invoice(client)
    name = f"INV-{uuid4().hex[:6]}.pdf"
    assert upload(client, first.id, "FOREIGN_INVOICE", name, pdf(INVOICE_TEXT)).status_code == 303
    complete(client, second.id, pdf(INVOICE_TEXT))
    # Un documento que no paso por el control de la carga (anterior al cambio o de otra via) repite el nombre.
    with SessionLocal() as db:
        db.execute(
            update(Document)
            .where(Document.invoice_id == second.id, Document.document_type == "FOREIGN_INVOICE")
            .values(original_filename=name)
        )
        db.commit()
    assert post(client, f"/invoices/{second.id}/submit").status_code == 409
    fin007 = results(second.id)["FIN-007"]
    assert (fin007.status, fin007.severity, fin007.message) == (
        "FAIL",
        "CRITICAL",
        "Invoice duplicado por nombre de archivo",
    )
    assert fin007.evidence_json == {"invoices": [first.internal_folio]}
    assert invoice(second.id).status == InvoiceStatus.UPLOADED


# --- Validacion internacional -------------------------------------------------------------------------------------

NOT_FOR_INTERNATIONAL = [f"XML-{n:03d}" for n in range(1, 12)] + [
    "PRV-001",
    "PRV-002",
    "PRV-003",
    "FIN-004",
    "SUP-003",
    "SUP-004",
]
ORDER_PASS = ["OC-001", "OC-002", "OC-004", "OC-005", "OC-006", "OC-010", "OC-011", "OC-012"]


def test_envio_de_extremo_a_extremo(client, purchase_orders):
    order = foreign_order(purchase_orders)
    login(client, INTERNATIONAL)
    created = new_invoice(client, purchase_order_number=str(order.convenio))
    complete(client, created.id, pdf(INVOICE_TEXT))
    assert invoice(created.id).status == InvoiceStatus.UPLOADED
    response = post(client, f"/invoices/{created.id}/submit")
    assert response.headers["location"] == f"/invoices/{created.id}?notice=submitted"
    sent = invoice(created.id)
    assert sent.status == InvoiceStatus.UNDER_REVIEW and sent.submitted_at is not None
    by_code = results(created.id)
    for code in NOT_FOR_INTERNATIONAL:
        assert (by_code[code].status, by_code[code].message) == (
            "NOT_APPLICABLE",
            "No aplica a proveedores internacionales",
        )
    assert by_code["XML-001"].severity == "CRITICAL" and by_code["SUP-003"].severity == "ERROR"
    assert [by_code[c].status for c in ("INT-001", "INT-002", "INT-003", "FIN-007")] == ["PASS"] * 4
    assert by_code["INT-004"].status == "NOT_APPLICABLE"  # direccion vacia en la instalacion
    assert all(result.status != "FAIL" for result in by_code.values())
    assert [by_code[code].status for code in ORDER_PASS] == ["PASS"] * len(ORDER_PASS)
    assert (by_code["OC-003"].status, by_code["OC-003"].message) == (
        "NOT_APPLICABLE",
        "No aplica para proveedores internacionales",
    )
    for code in ("OC-007", "OC-008", "OC-009"):
        assert (by_code[code].status, by_code[code].message) == ("NOT_APPLICABLE", "Sin partidas en el Invoice")
    assert not {"SEM-001", "FIN-001", "FIN-003", "FIN-006", "SUP-002", "DOC-005"} & set(by_code)
    assert sent.purchase_order_id == order.id


def test_datos_ausentes_son_advertencias(client, purchase_orders):
    order = foreign_order(purchase_orders)
    login(client, INTERNATIONAL)
    created = new_invoice(client, purchase_order_number=str(order.convenio))
    complete(client, created.id, pdf(["INVOICE without reference data", "Total 1,000.00"]))
    assert post(client, f"/invoices/{created.id}/submit").status_code == 303
    by_code = results(created.id)
    assert [by_code[c].status for c in ("INT-001", "INT-002", "INT-003")] == ["WARNING"] * 3
    assert by_code["INT-002"].message == "No se encontró la razón social de FERROMEX en el Invoice"
    assert by_code["INT-002"].expected_value == "INTERMODAL MEXICO"
    assert invoice(created.id).status == InvoiceStatus.UNDER_REVIEW


def test_invoice_escaneado(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    complete(client, created.id, pdf([]))
    assert post(client, f"/invoices/{created.id}/validation").status_code == 303
    by_code = results(created.id)
    for code in ("INT-001", "INT-002", "INT-003"):
        assert (by_code[code].status, by_code[code].message) == (
            "NOT_EVALUATED",
            "No se pudo leer el texto del Invoice",
        )
    # INT-004 nace eliminada (sin direccion de FERROMEX): no se evalua.
    assert (by_code["INT-004"].status, by_code["INT-004"].message) == (
        "NOT_APPLICABLE",
        "Regla inactiva en Reglas de Validación",
    )
    assert "Sin texto legible (posible escaneo)" in client.get(f"/invoices/{created.id}").text


def test_comparaciones_desactivadas_y_direccion(client, restore_validation_rules):
    with SessionLocal() as db:
        international = ValidationRule.origin == SupplierOrigin.INTERNATIONAL
        db.execute(
            update(ValidationRule)
            .where(international, ValidationRule.rule_code == "INT-003")
            .values(is_active=False, deleted_at=now_utc())
        )
        db.execute(
            update(ValidationRule)
            .where(international, ValidationRule.rule_code == "INT-004")
            .values(is_active=True, deleted_at=None, parameter="Av. Insurgentes Sur 1, Ciudad de México")
        )
        db.commit()
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    complete(client, created.id, pdf(INVOICE_TEXT))
    post(client, f"/invoices/{created.id}/validation")
    by_code = results(created.id)
    assert (by_code["INT-003"].status, by_code["INT-003"].message) == (
        "NOT_APPLICABLE",
        "Regla inactiva en Reglas de Validación",
    )
    assert by_code["INT-004"].status == "PASS"  # sin acentos ni signos: "Ciudad de México" = "Ciudad de Mexico"


def test_subtotal_distinto_de_la_orden(client, purchase_orders):
    order = foreign_order(purchase_orders)
    login(client, INTERNATIONAL)
    created = new_invoice(client, subtotal="25000.00", tax="0.00", purchase_order_number=str(order.convenio))
    complete(client, created.id, pdf(INVOICE_TEXT))
    assert post(client, f"/invoices/{created.id}/submit").status_code == 409
    rule = results(created.id)["OC-005"]
    assert (rule.status, rule.expected_value, rule.detected_value) == ("FAIL", "1000.00", "25000.00")
    assert invoice(created.id).status == InvoiceStatus.UPLOADED


def test_orden_de_otro_proveedor(client, purchase_orders, other_international):
    order = foreign_order(purchase_orders, other_international, supplier_name="Otro Proveedor Internacional LLC")
    login(client, INTERNATIONAL)
    created = new_invoice(client, purchase_order_number=str(order.convenio))
    complete(client, created.id, pdf(INVOICE_TEXT))
    assert post(client, f"/invoices/{created.id}/submit").status_code == 409
    rule = results(created.id)["OC-002"]
    assert (rule.status, rule.message) == ("FAIL", f"La orden de compra {order.convenio} no existe para el proveedor")


def test_orden_sin_entrada_de_mercancia(client, purchase_orders):
    pending = item("DATA ANALYTICS CONSULTING", "1000.00", currency="USD", delivered=False)
    order = foreign_order(purchase_orders, items=[pending])
    login(client, INTERNATIONAL)
    created = new_invoice(client, purchase_order_number=str(order.convenio))
    complete(client, created.id, pdf(INVOICE_TEXT))
    assert post(client, f"/invoices/{created.id}/submit").status_code == 409
    rule = results(created.id)["OC-011"]
    assert (rule.status, rule.message) == ("FAIL", "Partidas sin entrada de mercancía: DATA ANALYTICS CONSULTING")


def test_factura_nacional_sin_cambios(client):
    login(client, "proveedor1@poc.local")
    national = invoice_by_number("A-CORRECTA")
    assert post(client, f"/invoices/{national.id}/validation").status_code == 303
    by_code = results(national.id)
    assert not {code for code in by_code if code.startswith("INT-")} and "FIN-007" not in by_code
    assert by_code["XML-001"].status == "PASS" and by_code["FIN-004"].status == "PASS"
    assert by_code["SUP-003"].status == "PASS" and "SEM-001" not in by_code
    assert by_code["OC-001"].status == "PASS" and by_code["PRV-001"].status == "PASS"


# --- Detalle ------------------------------------------------------------------------------------------------------


def test_detalle_de_la_factura_internacional_demo(client):
    login(client, "pmo@poc.local")
    demo = invoice_by_number("INV-2026-0042")
    page = client.get(f"/invoices/{demo.id}").text
    assert "Datos del Invoice" in page and "Datos CFDI" not in page
    assert "$18,000.00 USD" in page and "No aplica (Invoice)" in page
    assert "US · 98-7654321" in page and "Legible" in page
    assert "<dt>Orden de compra</dt><dd>45009042</dd>" in page


def test_detalle_nacional_con_datos_cfdi(client):
    login(client, "pmo@poc.local")
    page = client.get(f"/invoices/{invoice_by_number('A-CORRECTA').id}").text
    assert "Datos CFDI" in page and "Datos del Invoice" not in page
