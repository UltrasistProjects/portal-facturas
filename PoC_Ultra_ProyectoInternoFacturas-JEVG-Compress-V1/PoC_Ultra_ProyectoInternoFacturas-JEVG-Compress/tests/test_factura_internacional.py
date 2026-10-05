"""Factura del proveedor internacional: datos del Invoice, duplicados por nombre de archivo y validacion (HU-15 y
HU-16, specs factura-internacional y motor-validacion)."""

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
from app.models import AuditLog, Contract, Document, Invoice, Supplier, User, ValidationResult, ValidationSettings
from app.services.foreign_invoice_service import MSG_NOT_INTERNATIONAL
from tests.conftest import active_contract, csrf, identity_account, invoice_by_number, login

INTERNATIONAL = "proveedor3@poc.local"  # proveedor internacional demo del seed (D11)
AMOUNTS = {"invoice_date": "2026-09-15", "subtotal": "1,000.00", "tax": "0.00", "total": "1000", "currency": "USD"}
INVOICE_TEXT = [
    "INVOICE - Global Data Services Inc.",
    "Tax ID: 98-7654321",
    "Bill to: ULTRASIST, S.A. de C.V.",
    "Av. Insurgentes Sur 1, Ciudad de Mexico, C.P. 03930",
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


def contract_of(email: str) -> Contract:
    with SessionLocal() as db:
        supplier_id = db.scalar(select(User.supplier_id).where(User.email == email))
        return db.scalar(select(Contract).where(Contract.supplier_id == supplier_id))


def register(client, email: str = INTERNATIONAL, **overrides):
    """Alta de una factura con numero unico; devuelve (respuesta, numero)."""
    contract = contract_of(email)
    number = f"HU15-{uuid4().hex[:10]}"
    data = {
        "contract_id": contract.id,
        "invoice_number": number,
        "service_period": "08/2026",
        "project_name": contract.project_name,
        **AMOUNTS,
        **overrides,
        "csrf_token": csrf(client, "/invoices/new"),
    }
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
    """Invoice, orden de compra y Vo.Bo.: los obligatorios iniciales del internacional."""
    name = filename or f"INV-{uuid4().hex[:8]}.pdf"
    assert upload(client, invoice_id, "FOREIGN_INVOICE", name, invoice_pdf).status_code == 303
    assert upload(client, invoice_id, "PURCHASE_ORDER", "oc.txt", TXT).status_code == 303
    assert upload(client, invoice_id, "APPROVAL", "vobo.txt", TXT).status_code == 303


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
    """Segundo proveedor internacional autorizado, con contrato en USD y usuario; se reutiliza entre pruebas."""
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
            active_contract(
                db,
                supplier.id,
                project_name="Consultoria Canada",
                project_leader="Lider Demo",
                authorized_technology="Data Analytics",
                authorized_amount=Decimal("50000.00"),
                currency="USD",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
            )
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
    assert "Datos del Invoice" in page and 'name="invoice_date"' in page
    assert '<option value="USD" selected>' in page  # moneda del contrato preseleccionada


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


def test_total_que_no_cuadra(client):
    login(client, INTERNATIONAL)
    response, number = register(client, subtotal="1000.00", tax="160.00", total="1100.00")
    assert response.status_code == 400
    assert "Total: debe ser igual al subtotal más impuestos" in response.text
    assert 'value="1100.00"' in response.text and number in response.text  # conserva lo capturado
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
    assert "Datos del Invoice" not in client.get("/invoices/new").text
    created = new_invoice(client, "proveedor1@poc.local")  # los campos del Invoice se ignoran
    assert (created.subtotal, created.total, created.currency, created.invoice_date) == (
        Decimal("0.00"),
        Decimal("0.00"),
        "MXN",
        None,
    )


# --- Edicion de los datos del Invoice -----------------------------------------------------------------------------


def edit(client, invoice_id: int, **values):
    return post(client, f"/invoices/{invoice_id}/amounts", {**AMOUNTS, **values})


def test_formulario_en_la_carga_documental(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    page = client.get(f"/invoices/{created.id}/documents").text
    assert 'action="/invoices/' + str(created.id) + '/amounts"' in page
    assert 'value="2026-09-15"' in page and 'value="1000.00"' in page


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
    response = edit(client, created.id, total="999.00")
    assert response.status_code == 400 and "Total: debe ser igual al subtotal más impuestos" in response.text
    assert 'value="999.00"' in response.text and invoice(created.id).total == Decimal("1000.00")


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
    created = new_invoice(client, "proveedor1@poc.local")
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

NOT_FOR_INTERNATIONAL = [f"XML-{n:03d}" for n in range(1, 11)] + ["FIN-004", "SUP-003", "SUP-004"]


def test_envio_de_extremo_a_extremo(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
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
    assert (by_code["SEM-001"].status, by_code["SEM-001"].message) == (
        "NOT_EVALUATED",
        "Sin conceptos que comparar: el Invoice no es un CFDI",
    )
    assert all(result.status != "FAIL" for result in by_code.values())
    assert by_code["FIN-001"].status == "PASS" and by_code["FIN-003"].status == "PASS"


def test_datos_ausentes_son_advertencias(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    complete(client, created.id, pdf(["INVOICE without reference data", "Total 1,000.00"]))
    assert post(client, f"/invoices/{created.id}/submit").status_code == 303
    by_code = results(created.id)
    assert [by_code[c].status for c in ("INT-001", "INT-002", "INT-003")] == ["WARNING"] * 3
    assert by_code["INT-002"].message == "No se encontró la razón social de ULTRASIST en el Invoice"
    assert invoice(created.id).status == InvoiceStatus.UNDER_REVIEW


def test_invoice_escaneado(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    complete(client, created.id, pdf([]))
    assert post(client, f"/invoices/{created.id}/validation").status_code == 303
    by_code = results(created.id)
    for code in ("INT-001", "INT-002", "INT-003", "INT-004"):
        assert (by_code[code].status, by_code[code].message) == (
            "NOT_EVALUATED",
            "No se pudo leer el texto del Invoice",
        )
    assert "Sin texto legible (posible escaneo)" in client.get(f"/invoices/{created.id}").text


def test_comparaciones_desactivadas_y_direccion(client, restore_validation_rules):
    with SessionLocal() as db:
        db.execute(
            update(ValidationSettings).values(
                check_receiver_postal_code=False, receiver_address="Av. Insurgentes Sur 1, Ciudad de México"
            )
        )
        db.commit()
    login(client, INTERNATIONAL)
    created = new_invoice(client)
    complete(client, created.id, pdf(INVOICE_TEXT))
    post(client, f"/invoices/{created.id}/validation")
    by_code = results(created.id)
    assert (by_code["INT-003"].status, by_code["INT-003"].message) == (
        "NOT_APPLICABLE",
        "Comparación desactivada en Reglas de Validación",
    )
    assert by_code["INT-004"].status == "PASS"  # sin acentos ni signos: "Ciudad de México" = "Ciudad de Mexico"


def test_monto_excedido(client):
    login(client, INTERNATIONAL)
    created = new_invoice(client, subtotal="25000.00", tax="0.00", total="25000.00")
    complete(client, created.id, pdf(INVOICE_TEXT))
    assert post(client, f"/invoices/{created.id}/submit").status_code == 409
    fin001 = results(created.id)["FIN-001"]
    assert (fin001.status, fin001.severity) == ("FAIL", "CRITICAL")
    assert invoice(created.id).status == InvoiceStatus.UPLOADED


def test_factura_nacional_sin_cambios(client):
    login(client, "proveedor1@poc.local")
    national = invoice_by_number("A-CORRECTA")
    assert post(client, f"/invoices/{national.id}/validation").status_code == 303
    by_code = results(national.id)
    assert not {code for code in by_code if code.startswith("INT-")} and "FIN-007" not in by_code
    assert by_code["XML-001"].status == "PASS" and by_code["FIN-004"].status == "PASS"
    assert by_code["SUP-003"].status == "PASS" and by_code["SEM-001"].status in {"PASS", "WARNING"}


# --- Detalle ------------------------------------------------------------------------------------------------------


def test_detalle_de_la_factura_internacional_demo(client):
    login(client, "pmo@poc.local")
    demo = invoice_by_number("INV-2026-0042")
    page = client.get(f"/invoices/{demo.id}").text
    assert "Datos del Invoice" in page and "Datos CFDI" not in page
    assert "$18,000.00 USD" in page and "No aplica (Invoice)" in page
    assert "US · 98-7654321" in page and "Legible" in page


def test_detalle_nacional_con_datos_cfdi(client):
    login(client, "pmo@poc.local")
    page = client.get(f"/invoices/{invoice_by_number('A-CORRECTA').id}").text
    assert "Datos CFDI" in page and "Datos del Invoice" not in page
