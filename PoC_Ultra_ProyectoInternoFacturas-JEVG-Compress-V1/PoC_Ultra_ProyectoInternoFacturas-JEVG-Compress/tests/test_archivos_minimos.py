"""Archivos minimos por tipo de proveedor (HU-04): specs archivos-minimos-factura y motor-validacion."""

import re
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.constants import FORMAT_EXTENSIONS, Role, SupplierOrigin, SupplierStatus, SupplierType
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import AuditLog, Contract, Document, Invoice, InvoiceDocumentType, Supplier, User, ValidationResult
from app.rules.document_rules import document_rules
from app.services.file_service import ALLOWED_EXTENSIONS
from app.services.validation_score_service import calculate_score
from tests.conftest import ROOT, csrf, invoice_by_number, login, supplier_by_email

NATIONAL, INTERNATIONAL = SupplierOrigin.NATIONAL, SupplierOrigin.INTERNATIONAL


def test_formatos_cubren_exactamente_las_extensiones_permitidas():
    extensions = [ext for group in FORMAT_EXTENSIONS.values() for ext in group]
    assert len(extensions) == len(set(extensions))
    assert set(extensions) == ALLOWED_EXTENSIONS


# --- Reglas documentales sin base de datos ------------------------------------------------------------------------


def doc(code: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(code=code, name=name)


CFDI_XML, CFDI_PDF = doc("INVOICE_XML", "XML del CFDI"), doc("INVOICE_PDF", "PDF del CFDI")
PURCHASE_ORDER, APPROVAL = doc("PURCHASE_ORDER", "Orden de compra"), doc("APPROVAL", "Vo.Bo. del líder de proyecto")
FOREIGN = doc("FOREIGN_INVOICE", "Invoice (PDF)")
# Configuracion inicial: tipos Obligatorios por origen, en el orden del catalogo.
REQUIRED_NATIONAL = [CFDI_XML, CFDI_PDF, PURCHASE_ORDER, APPROVAL]
REQUIRED_INTERNATIONAL = [FOREIGN, PURCHASE_ORDER, APPROVAL]


def by_code(results) -> dict:
    return {r.rule_code: r for r in results if r.rule_code != "DOC-009"}


def test_reglas_de_proveedor_nacional_sin_vobo():
    present = {"INVOICE_XML", "INVOICE_PDF", "PURCHASE_ORDER"}
    results = by_code(document_rules(present, REQUIRED_NATIONAL, NATIONAL, True, True))
    assert [results[c].status for c in ("DOC-001", "DOC-002", "DOC-003")] == ["PASS"] * 3
    assert (results["DOC-004"].status, results["DOC-004"].severity) == ("FAIL", "ERROR")
    assert results["DOC-004"].message == "Falta Vo.Bo. del líder de proyecto"
    assert results["DOC-001"].message == "XML del CFDI presente"
    assert (results["DOC-008"].status, results["DOC-008"].message) == (
        "NOT_APPLICABLE",
        "No requerido para proveedores nacionales",
    )


def test_reglas_de_proveedor_internacional_sin_invoice():
    results = by_code(document_rules({"PURCHASE_ORDER", "APPROVAL"}, REQUIRED_INTERNATIONAL, INTERNATIONAL, True, True))
    assert (results["DOC-008"].status, results["DOC-008"].severity, results["DOC-008"].message) == (
        "FAIL",
        "CRITICAL",
        "Falta Invoice (PDF)",
    )
    for code in ("DOC-001", "DOC-002"):
        assert (results[code].status, results[code].message) == (
            "NOT_APPLICABLE",
            "No requerido para proveedores internacionales",
        )


def test_orden_de_compra_opcional_no_descuenta_del_score():
    required = [CFDI_XML, CFDI_PDF, APPROVAL]
    present = {"INVOICE_XML", "INVOICE_PDF", "APPROVAL"}
    results = document_rules(present, required, NATIONAL, True, True)
    assert by_code(results)["DOC-003"].status == "NOT_APPLICABLE"
    assert calculate_score(results)["score"] == 100


def test_tipo_soporte_obligatorio_genera_doc_009():
    hours = doc("SOPORTE_12", "Reporte de horas")
    results = document_rules({"FOREIGN_INVOICE"}, [FOREIGN, hours], INTERNATIONAL, True, True)
    doc_009 = [r for r in results if r.rule_code == "DOC-009"]
    assert [(r.status, r.severity, r.source_document, r.message) for r in doc_009] == [
        ("FAIL", "ERROR", "SOPORTE_12", "Falta Reporte de horas")
    ]
    assert [r.rule_code for r in results] == [f"DOC-00{n}" for n in range(1, 10)]


def test_factura_demo_sin_vobo_con_la_configuracion_inicial():
    invoice = invoice_by_number("D-SIN-VOBO")
    with SessionLocal() as db:
        results = {
            r.rule_code: r
            for r in db.scalars(select(ValidationResult).where(ValidationResult.invoice_id == invoice.id))
            if r.category == "DOC"
        }
    assert invoice.status == "DRAFT"
    assert [results[c].status for c in ("DOC-001", "DOC-002", "DOC-003")] == ["PASS"] * 3
    assert (results["DOC-004"].status, results["DOC-004"].message) == ("FAIL", "Falta Vo.Bo. del líder de proyecto")
    assert results["DOC-008"].status == "NOT_APPLICABLE"
    assert "DOC-009" not in results


# --- Infraestructura: catalogo restaurable, proveedor internacional y facturas nuevas -----------------------------

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
TXT = b"Documento de prueba"
XML = (ROOT / "data" / "demo_documents" / "cfdi_demo_correcto.xml").read_bytes()
INTERNATIONAL_EMAIL, INTERNATIONAL_PASSWORD = "internacional@poc.local", "Test#Internacional2026"


@pytest.fixture()
def restore_catalog():
    """La base de pruebas es compartida (D20): restaura los niveles de los tipos del sistema y borra los tipos
    soporte creados. Los documentos de esos tipos se conservan: no hay FK de document_type al catalogo."""
    with SessionLocal() as db:
        saved = {
            t.code: (t.national_requirement, t.international_requirement)
            for t in db.scalars(select(InvoiceDocumentType).where(InvoiceDocumentType.is_system))
        }
    yield
    with SessionLocal() as db:
        db.execute(delete(InvoiceDocumentType).where(InvoiceDocumentType.is_system.is_(False)))
        for document_type in db.scalars(select(InvoiceDocumentType).where(InvoiceDocumentType.is_system)):
            document_type.national_requirement, document_type.international_requirement = saved[document_type.code]
        db.commit()


def set_level(code: str, origin: SupplierOrigin, level: str) -> None:
    field = "national_requirement" if origin == NATIONAL else "international_requirement"
    with SessionLocal() as db:
        document_type = db.scalar(select(InvoiceDocumentType).where(InvoiceDocumentType.code == code))
        setattr(document_type, field, level)
        db.commit()


@pytest.fixture(scope="module")
def international():
    """Proveedor internacional activo, con contrato y usuario PROVIDER (la interfaz aun no permite autorizarlo)."""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == INTERNATIONAL_EMAIL))
        if user is None:
            supplier = Supplier(
                business_name="Northwind Consulting LLC",
                supplier_type=SupplierType.PERSONA_MORAL,
                email="facturas@northwind.example",
                origin=INTERNATIONAL,
                rfc=None,
                foreign_tax_id=f"NW-{uuid4().hex[:8]}",
                country="US",
                status=SupplierStatus.ACTIVE,
            )
            db.add(supplier)
            db.flush()
            db.add(
                Contract(
                    supplier_id=supplier.id,
                    project_name="Consultoria internacional",
                    project_leader="Lider Demo",
                    authorized_technology="Power Platform",
                    authorized_amount=Decimal("100000.00"),
                    currency="USD",
                    start_date=date(2026, 1, 1),
                    end_date=date(2026, 12, 31),
                )
            )
            user = User(
                name="Proveedor internacional",
                email=INTERNATIONAL_EMAIL,
                password_hash=hash_password(INTERNATIONAL_PASSWORD),
                role=Role.PROVIDER,
                supplier_id=supplier.id,
            )
            db.add(user)
            db.commit()
        contract_id = db.scalar(select(Contract.id).where(Contract.supplier_id == user.supplier_id))
        return SimpleNamespace(supplier_id=user.supplier_id, contract_id=contract_id)


def login_international(client) -> None:
    login(client, INTERNATIONAL_EMAIL, INTERNATIONAL_PASSWORD)


# Datos del Invoice que el alta exige al proveedor internacional (HU-15).
FOREIGN_INVOICE_DATA = {
    "invoice_date": "2026-08-31",
    "subtotal": "1000.00",
    "tax": "0.00",
    "total": "1000.00",
    "currency": "USD",
}


def create_invoice(client, supplier_id: int, contract_id: int, project_name: str, extra: dict | None = None):
    number = f"HU04-{uuid4().hex[:10]}"
    data = {
        "supplier_id": supplier_id,
        "contract_id": contract_id,
        "invoice_number": number,
        "service_period": "08/2026",
        "project_name": project_name,
        **(extra or {}),
        "csrf_token": csrf(client, "/invoices/new"),
    }
    assert client.post("/invoices/new", data=data, follow_redirects=False).status_code == 303
    return invoice_by_number(number)


def national_invoice(client):
    """Factura nueva del proveedor 1 (nacional), con la sesion de ese proveedor abierta."""
    login(client, "proveedor1@poc.local")
    base = invoice_by_number("A-CORRECTA")
    return create_invoice(client, supplier_by_email("proveedor1@poc.local").id, base.contract_id, base.project_name)


def international_invoice(client, international):
    login_international(client)
    return create_invoice(
        client, international.supplier_id, international.contract_id, "Consultoria internacional", FOREIGN_INVOICE_DATA
    )


def upload(client, invoice_id: int, document_type: str, filename: str, content: bytes):
    return client.post(
        f"/invoices/{invoice_id}/documents",
        data={"document_type": document_type, "csrf_token": csrf(client, f"/invoices/{invoice_id}")},
        files={"upload": (filename, content, "application/octet-stream")},
        follow_redirects=False,
    )


def stored_files(invoice_id: int) -> list:
    folder = settings.storage_path / "invoices" / str(invoice_id)
    return sorted(folder.iterdir()) if folder.exists() else []


def offered(page: str) -> list[str]:
    """Claves del selector de tipos de la carga documental, en orden."""
    select_html = re.search(r'<select id="document_type".*?</select>', page, re.S).group(0)
    return re.findall(r'<option value="([^"]+)"', select_html)


def checklist_row(page: str, name: str) -> str | None:
    match = re.search(rf"<strong>{re.escape(name)}</strong><small>([^<]*)</small>", page)
    return match.group(1) if match else None


# --- Carga documental segun el origen del proveedor -----------------------------------------------------------------

NATIONAL_OFFERED = [
    "INVOICE_XML",
    "INVOICE_PDF",
    "PURCHASE_ORDER",
    "APPROVAL",
    "CONTRACT",
    "CONTRACT_ANNEX",
    "PAYMENT_COMPLEMENT_XML",
    "PAYMENT_COMPLEMENT_PDF",
    "ADDITIONAL",
]
INTERNATIONAL_OFFERED = ["FOREIGN_INVOICE", "PURCHASE_ORDER", "APPROVAL", "CONTRACT", "CONTRACT_ANNEX", "ADDITIONAL"]


def test_tipos_ofrecidos_a_proveedor_nacional(client):
    invoice = national_invoice(client)
    page = client.get(f"/invoices/{invoice.id}/documents").text
    # Obligatorios primero y despues opcionales, cada grupo en el orden del catalogo.
    assert offered(page) == NATIONAL_OFFERED
    for name in ("Orden de compra (PDF, PNG, JPEG, TXT)", "Vo.Bo. del líder de proyecto", "PDF del CFDI (PDF)"):
        assert name in page
    assert "FOREIGN_INVOICE" not in page and "Purchase Order" not in page


def test_tipos_ofrecidos_a_proveedor_internacional(client, international):
    invoice = international_invoice(client, international)
    page = client.get(f"/invoices/{invoice.id}/documents").text
    assert offered(page) == INTERNATIONAL_OFFERED
    assert "Invoice (PDF) (PDF)" in page
    assert 'accept=".pdf,.png,.jpg,.jpeg,.txt,.xml"' in page


def test_nombres_en_el_detalle_de_la_factura(client):
    login(client, "proveedor1@poc.local")
    page = client.get(f"/invoices/{invoice_by_number('A-CORRECTA').id}").text
    for name in ("XML del CFDI", "PDF del CFDI", "Orden de compra", "Vo.Bo. del líder de proyecto"):
        assert f"<strong>{name}</strong>" in page
    assert "Invoice Xml" not in page


@pytest.mark.parametrize("document_type", ["INVOICE_XML", "OTRO"])
def test_tipo_que_no_aplica_o_inexistente(client, international, document_type):
    invoice = international_invoice(client, international)
    response = upload(client, invoice.id, document_type, "cfdi.pdf", PDF)
    assert response.status_code == 400
    assert "El tipo de documento no aplica a esta factura" in response.text
    assert stored_files(invoice.id) == []


def test_formato_no_admitido_por_el_tipo(client):
    invoice = national_invoice(client)
    response = upload(client, invoice.id, "INVOICE_PDF", "factura.png", PNG)
    assert response.status_code == 400
    assert "Formato no admitido para PDF del CFDI. Formatos admitidos: PDF" in response.text
    assert stored_files(invoice.id) == []


def test_formato_admitido_se_carga(client, international):
    invoice = international_invoice(client, international)
    assert upload(client, invoice.id, "FOREIGN_INVOICE", f"invoice-{invoice.id}.pdf", PDF).status_code == 303
    assert len(stored_files(invoice.id)) == 1


def test_checklist_de_obligatorios(client):
    invoice = national_invoice(client)
    for document_type, filename, content in (("INVOICE_XML", "cfdi.xml", XML), ("INVOICE_PDF", "cfdi.pdf", PDF)):
        assert upload(client, invoice.id, document_type, filename, content).status_code == 303
    page = client.get(f"/invoices/{invoice.id}/documents").text
    assert checklist_row(page, "Orden de compra") == "Obligatorio · Pendiente"
    assert checklist_row(page, "Vo.Bo. del líder de proyecto") == "Obligatorio · Pendiente"
    assert checklist_row(page, "XML del CFDI").startswith("Obligatorio · cfdi.xml")
    assert checklist_row(page, "Contrato") == "Opcional · Pendiente"
    assert "Faltan 2 archivos obligatorios" in page
    upload(client, invoice.id, "PURCHASE_ORDER", "oc.txt", TXT)
    assert "Falta 1 archivo obligatorio" in client.get(f"/invoices/{invoice.id}/documents").text
    upload(client, invoice.id, "APPROVAL", "vobo.png", PNG)
    assert "Archivos obligatorios completos" in client.get(f"/invoices/{invoice.id}/documents").text


def test_documento_de_un_tipo_que_dejo_de_aplicar(client, restore_catalog):
    invoice = national_invoice(client)
    assert upload(client, invoice.id, "PURCHASE_ORDER", "oc.pdf", PDF).status_code == 303
    set_level("PURCHASE_ORDER", NATIONAL, "NOT_APPLICABLE")
    page = client.get(f"/invoices/{invoice.id}/documents").text
    assert "PURCHASE_ORDER" not in offered(page)
    assert checklist_row(page, "Orden de compra") is None
    assert "Faltan 3 archivos obligatorios" in page
    detail = client.get(f"/invoices/{invoice.id}").text
    assert "<strong>Orden de compra</strong>" in detail
    link = re.search(rf'href="(/invoices/{invoice.id}/documents/\d+/download)"', detail).group(1)
    assert client.get(link).content == PDF


# --- Pantalla de configuracion: acceso ------------------------------------------------------------------------------

URL = "/admin/required-documents"


def type_by(**filters) -> InvoiceDocumentType | None:
    with SessionLocal() as db:
        return db.scalar(select(InvoiceDocumentType).filter_by(**filters))


def config_snapshot() -> tuple:
    """Catalogo completo y numero de registros de auditoria de la configuracion."""
    with SessionLocal() as db:
        types = sorted(
            (
                t.code,
                t.name,
                t.description,
                tuple(t.formats),
                t.national_requirement,
                t.international_requirement,
                t.is_active,
            )
            for t in db.scalars(select(InvoiceDocumentType))
        )
        audits = len(list(db.scalars(select(AuditLog.id).where(AuditLog.action.like("INVOICE_DOCUMENT_%")))))
    return types, audits


def config_routes() -> list[str]:
    type_id = type_by(code="ADDITIONAL").id
    return [URL, f"{URL}/types", f"{URL}/types/{type_id}", f"{URL}/types/{type_id}/status"]


@pytest.mark.parametrize("email", ["pmo@poc.local", "proveedor1@poc.local"])
def test_configuracion_sin_acceso_para_internal_y_proveedor(client, email):
    login(client, email)
    before = config_snapshot()
    token = csrf(client, "/invoices")
    assert client.get(URL).status_code == 403
    for route in config_routes():
        data = {"csrf_token": token, "name": "Intruso", "formats": "PDF", "active": "false"}
        assert client.post(route, data=data, follow_redirects=False).status_code == 403
    assert config_snapshot() == before


@pytest.mark.parametrize("token", [None, "invalido"])
def test_configuracion_sin_token_csrf(client, token):
    login(client)
    form = matrix(client.get(URL).text)
    form["national__CONTRACT"] = "REQUIRED"
    if token:
        form["csrf_token"] = token
    before = config_snapshot()
    assert client.post(URL, data=form, follow_redirects=False).status_code == 403
    assert config_snapshot() == before


# --- Pantalla de configuracion: matriz de niveles -------------------------------------------------------------------


def matrix(page: str) -> dict[str, str]:
    """Campos del formulario de la matriz tal como los enviaria el navegador."""
    form = re.search(r'<form method="post" action="/admin/required-documents">.*?</form>', page, re.S).group(0)
    values = {
        name: re.search(r'<option value="([A-Z_]+)" selected>', options).group(1)
        for name, options in re.findall(
            r'<select name="((?:national|international)__[A-Z0-9_]+)"[^>]*>(.*?)</select>', form, re.S
        )
    }
    values["config_version"] = re.search(r'name="config_version" value="([0-9a-f]+)"', form).group(1)
    return values


def save_matrix(client, changes: dict[str, str], form: dict[str, str] | None = None):
    data = {**(form or matrix(client.get(URL).text)), **changes, "csrf_token": csrf(client, URL)}
    return client.post(URL, data=data, follow_redirects=False)


def test_exigir_contrato_al_proveedor_internacional(client, international, restore_catalog):
    login(client)
    response = save_matrix(client, {"international__CONTRACT": "REQUIRED"})
    assert response.status_code == 303
    assert "Configuración guardada" in client.get(response.headers["location"]).text
    invoice = international_invoice(client, international)
    page = client.get(f"/invoices/{invoice.id}/documents").text
    assert checklist_row(page, "Contrato") == "Obligatorio · Pendiente"


def test_orden_de_compra_opcional_para_el_nacional(client, restore_catalog):
    login(client)
    assert save_matrix(client, {"national__PURCHASE_ORDER": "OPTIONAL"}).status_code == 303
    invoice = national_invoice(client)
    page = client.get(f"/invoices/{invoice.id}/documents").text
    assert checklist_row(page, "Orden de compra") == "Opcional · Pendiente"


def test_guardar_sin_cambios(client, restore_catalog):
    login(client)
    before = config_snapshot()
    response = save_matrix(client, {})
    assert response.status_code == 303
    assert "Sin cambios" in client.get(response.headers["location"]).text
    assert config_snapshot() == before


def test_nivel_invalido(client, restore_catalog):
    login(client)
    before = config_snapshot()
    response = save_matrix(client, {"national__CONTRACT": "REQUIRED", "international__ADDITIONAL": "MANDATORY"})
    assert response.status_code == 400
    assert "Nivel de exigencia inválido" in response.text
    assert config_snapshot() == before


def test_falta_el_nivel_de_un_tipo_editable(client, restore_catalog):
    login(client)
    form = matrix(client.get(URL).text)
    del form["national__APPROVAL"]
    before = config_snapshot()
    assert save_matrix(client, {"national__CONTRACT": "REQUIRED"}, form).status_code == 400
    assert config_snapshot() == before


def test_niveles_fijos_en_la_pantalla(client):
    login(client)
    page = client.get(URL).text
    row = re.search(r"<tr><td><strong>XML del CFDI</strong>.*?</tr>", page, re.S).group(0)
    assert "<select" not in row
    assert row.count("bi-lock-fill") == 2
    assert re.search(r"bi-lock-fill[^<]*</i> Obligatorio</span><small[^>]*>El proveedor nacional factura con CFDI", row)
    assert "</i> No aplica</span>" in row
    assert "international__FOREIGN_INVOICE" not in page and "national__FOREIGN_INVOICE" not in page


def test_peticion_manipulada_sobre_un_nivel_fijo(client, restore_catalog):
    login(client)
    before = config_snapshot()
    response = save_matrix(client, {"national__INVOICE_XML": "OPTIONAL", "national__CONTRACT": "REQUIRED"})
    assert response.status_code == 409
    assert "XML del CFDI tiene un nivel fijo para proveedores nacionales" in response.text
    assert config_snapshot() == before
    # El mismo nivel fijo enviado sin cambio no es un intento de cambiarlo.
    assert save_matrix(client, {"international__INVOICE_PDF": "NOT_APPLICABLE"}).status_code == 303


def test_dos_administradores_editan_a_la_vez(client, restore_catalog):
    from fastapi.testclient import TestClient

    from app.main import app

    login(client)
    with TestClient(app) as other:
        login(other)
        form_a, form_b = matrix(client.get(URL).text), matrix(other.get(URL).text)
        assert save_matrix(client, {"national__CONTRACT": "REQUIRED"}, form_a).status_code == 303
        response = save_matrix(other, {"national__ADDITIONAL": "REQUIRED"}, form_b)
    assert response.status_code == 409
    assert "La configuración cambió mientras la editaba. Recargue la página." in response.text
    assert type_by(code="CONTRACT").national_requirement == "REQUIRED"
    assert type_by(code="ADDITIONAL").national_requirement == "OPTIONAL"


def test_huella_ausente(client, restore_catalog):
    login(client)
    form = matrix(client.get(URL).text)
    del form["config_version"]
    assert save_matrix(client, {"national__CONTRACT": "REQUIRED"}, form).status_code == 409


def last_audit(action: str) -> AuditLog:
    with SessionLocal() as db:
        return db.scalar(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id.desc()))


def admin_id() -> int:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == "admin@poc.local"))


def test_cambio_de_nivel_auditado(client, restore_catalog):
    login(client)
    assert save_matrix(client, {"international__PURCHASE_ORDER": "OPTIONAL"}).status_code == 303
    entry = last_audit("INVOICE_DOCUMENT_REQUIREMENTS_UPDATED")
    assert entry.user_id == admin_id()
    assert entry.old_value == {"PURCHASE_ORDER": {"international": "REQUIRED"}}
    assert entry.new_value == {"PURCHASE_ORDER": {"international": "OPTIONAL"}}


# --- Tipos de documento soporte --------------------------------------------------------------------------------------


def create_type(client, name: str, formats=("PDF",), national="NOT_APPLICABLE", international="NOT_APPLICABLE"):
    data = {
        "csrf_token": csrf(client, URL),
        "name": name,
        "description": "Horas dedicadas en el periodo",
        "formats": list(formats),
        "national_requirement": national,
        "international_requirement": international,
    }
    return client.post(f"{URL}/types", data=data, follow_redirects=False)


def hours_type(client, formats=("PDF",)) -> InvoiceDocumentType:
    login(client)
    assert create_type(client, "Reporte de horas", formats, international="REQUIRED").status_code == 303
    return type_by(name="Reporte de horas")


def test_alta_de_un_tipo_soporte(client, international, restore_catalog):
    created = hours_type(client)
    assert created.code == f"SOPORTE_{created.id}"
    assert (created.is_active, created.is_system, created.formats) == (True, False, ["PDF"])
    assert f'name="international__{created.code}"' in client.get(URL).text
    entry = last_audit("INVOICE_DOCUMENT_TYPE_CREATED")
    assert (entry.user_id, entry.entity_id) == (admin_id(), str(created.id))
    assert entry.new_value == {
        "code": created.code,
        "name": "Reporte de horas",
        "formats": ["PDF"],
        "national": "NOT_APPLICABLE",
        "international": "REQUIRED",
    }
    page = client.get(f"/invoices/{international_invoice(client, international).id}/documents").text
    assert checklist_row(page, "Reporte de horas") == "Obligatorio · Pendiente"
    assert created.code not in offered(client.get(f"/invoices/{national_invoice(client).id}/documents").text)


def test_nombre_repetido(client, restore_catalog):
    login(client)
    before = config_snapshot()
    response = create_type(client, "  orden   de COMPRA ")
    assert response.status_code == 409
    assert "Ya existe un tipo de documento con ese nombre" in response.text
    assert config_snapshot() == before


@pytest.mark.parametrize(
    ("name", "formats", "message"),
    [
        ("Reporte de horas", (), "Seleccione al menos un formato"),
        ("Rh", ("PDF",), "El nombre debe tener entre 3 y 80 caracteres"),
        ("Reporte de horas", ("DOCX",), "Formato no válido"),
    ],
)
def test_alta_invalida(client, restore_catalog, name, formats, message):
    login(client)
    before = config_snapshot()
    response = create_type(client, name, formats)
    assert response.status_code == 400
    assert message in response.text
    assert config_snapshot() == before


def edit_type(client, type_id: int, name: str, formats, description: str = ""):
    data = {"csrf_token": csrf(client, URL), "name": name, "description": description, "formats": list(formats)}
    return client.post(f"{URL}/types/{type_id}", data=data, follow_redirects=False)


def set_status(client, type_id: int, active: str):
    data = {"csrf_token": csrf(client, URL), "active": active}
    return client.post(f"{URL}/types/{type_id}/status", data=data, follow_redirects=False)


def current_document(invoice_id: int, code: str) -> Document | None:
    with SessionLocal() as db:
        return db.scalar(
            select(Document).where(
                Document.invoice_id == invoice_id, Document.document_type == code, Document.is_current
            )
        )


def test_cambio_de_formatos(client, international, restore_catalog):
    hours = hours_type(client)
    invoice = international_invoice(client, international)
    assert upload(client, invoice.id, hours.code, "horas.png", PNG).status_code == 400
    assert upload(client, invoice.id, hours.code, "horas.pdf", PDF).status_code == 303
    loaded = current_document(invoice.id, hours.code)
    login(client)
    assert edit_type(client, hours.id, "Reporte de horas", ("PDF", "PNG")).status_code == 303
    entry = last_audit("INVOICE_DOCUMENT_TYPE_UPDATED")
    assert (entry.old_value, entry.new_value) == (
        {"formats": ["PDF"], "description": "Horas dedicadas en el periodo"},
        {"formats": ["PDF", "PNG"], "description": None},
    )
    unchanged = current_document(invoice.id, hours.code)
    assert (unchanged.id, unchanged.original_filename, unchanged.mime_type) == (
        loaded.id,
        "horas.pdf",
        loaded.mime_type,
    )
    login_international(client)
    assert upload(client, invoice.id, hours.code, "horas.png", PNG).status_code == 303


def test_edicion_sin_cambios_y_nombre_repetido(client, restore_catalog):
    hours = hours_type(client)
    before = config_snapshot()
    assert edit_type(client, hours.id, "Reporte de horas", ("PDF",), "Horas dedicadas en el periodo").status_code == 303
    assert edit_type(client, hours.id, "CONTRATO", ("PDF",)).status_code == 409
    assert edit_type(client, 999_999, "Otro nombre", ("PDF",)).status_code == 404
    assert config_snapshot() == before


def test_desactivacion_y_reactivacion(client, international, restore_catalog):
    hours = hours_type(client)
    invoice = international_invoice(client, international)
    assert upload(client, invoice.id, hours.code, "horas.pdf", PDF).status_code == 303
    login(client)
    assert set_status(client, hours.id, "false").status_code == 303
    assert "Reporte de horas" in re.search(r"<h2>Tipos inactivos</h2>.*", client.get(URL).text, re.S).group(0)
    entry = last_audit("INVOICE_DOCUMENT_TYPE_STATUS_CHANGED")
    assert (entry.old_value, entry.new_value) == ({"is_active": True}, {"is_active": False})
    before = config_snapshot()
    assert set_status(client, hours.id, "false").status_code == 303  # ya inactivo: sin cambios ni auditoria
    assert config_snapshot() == before
    login_international(client)
    assert hours.code not in offered(client.get(f"/invoices/{invoice.id}/documents").text)
    other = international_invoice(client, international)
    assert validate(client, other).status_code == 303
    assert not [r for r in rule_results(other.id, "DOC-009") if r.source_document == hours.code]
    detail = client.get(f"/invoices/{invoice.id}").text
    assert "<strong>Reporte de horas</strong>" in detail
    link = re.search(rf'href="(/invoices/{invoice.id}/documents/\d+/download)"', detail).group(1)
    assert client.get(link).content == PDF
    login(client)
    assert set_status(client, hours.id, "true").status_code == 303
    assert type_by(id=hours.id).international_requirement == "REQUIRED"
    login_international(client)
    page = client.get(f"/invoices/{other.id}/documents").text
    assert checklist_row(page, "Reporte de horas") == "Obligatorio · Pendiente"


def test_tipo_del_sistema_no_se_edita_ni_desactiva(client):
    login(client)
    purchase_order = type_by(code="PURCHASE_ORDER")
    before = config_snapshot()
    for response in (
        edit_type(client, purchase_order.id, "Orden de compra firmada", ("PDF",)),
        set_status(client, purchase_order.id, "false"),
    ):
        assert response.status_code == 409
        assert "Los tipos de documento del sistema no se pueden editar ni desactivar" in response.text
    assert set_status(client, purchase_order.id, "quizas").status_code == 400
    assert config_snapshot() == before


# --- Motor de validacion con la configuracion vigente ---------------------------------------------------------------

DEMO_PDF = (ROOT / "data" / "demo_documents" / "factura_demo.pdf").read_bytes()


def validate(client, invoice):
    token = csrf(client, f"/invoices/{invoice.id}")
    return client.post(f"/invoices/{invoice.id}/validation", data={"csrf_token": token}, follow_redirects=False)


def rule_results(invoice_id: int, code: str) -> list[ValidationResult]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(ValidationResult)
                .where(ValidationResult.invoice_id == invoice_id, ValidationResult.rule_code == code)
                .order_by(ValidationResult.id)
            )
        )


def invoice_status(invoice_id: int) -> str:
    with SessionLocal() as db:
        return db.get(Invoice, invoice_id).status


def national_with_cfdi(client, *extra: tuple[str, str, bytes]):
    """Factura nacional nueva con XML (UUID unico) y PDF del CFDI, mas los documentos indicados."""
    invoice = national_invoice(client)
    xml = re.sub(r'UUID="[^"]*"', f'UUID="{str(uuid4()).upper()}"', XML.decode()).encode()
    for document_type, filename, content in (
        ("INVOICE_XML", "cfdi.xml", xml),
        ("INVOICE_PDF", "cfdi.pdf", DEMO_PDF),
        *extra,
    ):
        assert upload(client, invoice.id, document_type, filename, content).status_code == 303
    return invoice


def submit(client, invoice):
    token = csrf(client, f"/invoices/{invoice.id}")
    return client.post(f"/invoices/{invoice.id}/submit", data={"csrf_token": token}, follow_redirects=False)


def complete_national(client):
    return national_with_cfdi(client, ("PURCHASE_ORDER", "oc.txt", TXT), ("APPROVAL", "vobo.txt", TXT))


def test_factura_ya_enviada_conserva_sus_resultados(client, restore_catalog):
    invoice = complete_national(client)
    assert invoice_status(invoice.id) == "UPLOADED"
    assert submit(client, invoice).status_code == 303
    assert invoice_status(invoice.id) == "UNDER_REVIEW"
    before = [(r.rule_code, r.status, r.message) for r in rule_results(invoice.id, "DOC-004")]
    set_level("CONTRACT", NATIONAL, "REQUIRED")
    assert rule_results(invoice.id, "DOC-009") == []
    assert [(r.rule_code, r.status, r.message) for r in rule_results(invoice.id, "DOC-004")] == before
    assert invoice_status(invoice.id) == "UNDER_REVIEW"


def test_factura_en_observaciones_enviada_de_nuevo(client, restore_catalog):
    invoice = complete_national(client)
    assert submit(client, invoice).status_code == 303
    login(client, "pmo@poc.local")
    data = {"decision": "REQUIRES_CORRECTION", "comments": "Falta el contrato", "csrf_token": csrf(client, "/invoices")}
    assert client.post(f"/invoices/{invoice.id}/review", data=data, follow_redirects=False).status_code == 303
    set_level("CONTRACT", NATIONAL, "REQUIRED")
    login(client, "proveedor1@poc.local")
    assert submit(client, invoice).status_code == 409
    [contract] = rule_results(invoice.id, "DOC-009")
    assert (contract.status, contract.message, contract.source_document) == ("FAIL", "Falta Contrato", "CONTRACT")
    assert invoice_status(invoice.id) == "REQUIRES_CORRECTION"


def test_factura_editable_verificada_de_nuevo(client, restore_catalog):
    invoice = national_with_cfdi(client)
    assert validate(client, invoice).status_code == 303
    assert invoice_status(invoice.id) == "DRAFT"
    assert rule_results(invoice.id, "DOC-009") == []
    set_level("CONTRACT", NATIONAL, "REQUIRED")
    assert validate(client, invoice).status_code == 303
    [contract] = rule_results(invoice.id, "DOC-009")
    assert (contract.status, contract.message, contract.source_document) == ("FAIL", "Falta Contrato", "CONTRACT")


def test_factura_internacional_sin_invoice(client, international):
    invoice = international_invoice(client, international)
    assert validate(client, invoice).status_code == 303
    [doc_008] = rule_results(invoice.id, "DOC-008")
    assert (doc_008.status, doc_008.severity, doc_008.message) == ("FAIL", "CRITICAL", "Falta Invoice (PDF)")
    for code in ("DOC-001", "DOC-002"):
        [result] = rule_results(invoice.id, code)
        assert (result.status, result.message) == ("NOT_APPLICABLE", "No requerido para proveedores internacionales")
    assert invoice_status(invoice.id) == "DRAFT"
    assert "rule-result not_applicable" in client.get(f"/invoices/{invoice.id}").text


def test_tipo_soporte_obligatorio_en_la_prevalidacion(client, international, restore_catalog):
    hours = hours_type(client)
    invoice = international_invoice(client, international)
    assert upload(client, invoice.id, "FOREIGN_INVOICE", f"invoice-{invoice.id}.pdf", PDF).status_code == 303
    assert validate(client, invoice).status_code == 303
    [result] = rule_results(invoice.id, "DOC-009")
    assert (result.status, result.source_document, result.message) == ("FAIL", hours.code, "Falta Reporte de horas")
    assert rule_results(invoice.id, "DOC-008")[0].status == "PASS"


def test_edicion_invalida(client, restore_catalog):
    hours = hours_type(client)
    before = config_snapshot()
    response = edit_type(client, hours.id, "Reporte de horas", ())
    assert response.status_code == 400
    assert "Seleccione al menos un formato" in response.text
    assert config_snapshot() == before


def test_la_base_de_datos_decide_el_nombre_repetido(monkeypatch, restore_catalog):
    # Carrera: otro Administrador guardo el mismo nombre despues de la verificacion del servicio.
    from app.core.errors import BusinessRuleError
    from app.services import document_requirements_service as service

    monkeypatch.setattr(service, "_ensure_unique_name", lambda *args, **kwargs: None)
    with SessionLocal() as db:
        with pytest.raises(BusinessRuleError, match="Ya existe un tipo de documento con ese nombre"):
            service.create_type(db, admin_id(), "Orden de Compra", None, ["PDF"], "OPTIONAL", "OPTIONAL")
    assert type_by(name="Orden de Compra") is None
