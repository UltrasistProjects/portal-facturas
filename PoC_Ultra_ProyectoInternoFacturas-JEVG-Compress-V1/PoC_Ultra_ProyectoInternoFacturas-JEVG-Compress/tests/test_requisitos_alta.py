"""Requisitos de alta del proveedor (HU-21): catalogo, requisitos por tipo de proveedor, checklist del expediente,
configuracion del Administrador y autorizacion condicionada."""

import html
import re
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update

from app.core.config import settings
from app.core.constants import DocumentRequirement, RequirementProfile, SupplierOrigin, SupplierType
from app.core.database import SessionLocal
from app.models import AuditLog, Document, SupplierDocumentType, User, ValidationResult
from app.rules.supplier_rules import supplier_rules
from app.services import supplier_requirements_service as requirements
from app.services.keycloak_admin import get_identity_admin
from tests.conftest import (
    add_expedient_documents,
    csrf,
    invoice_by_number,
    load_requirements,
    login,
    migration_module,
    supplier_by_email,
)

SEEDED = migration_module("0016_supplier_document_types").SYSTEM_TYPES
MORAL_REQUIRED = [
    "Acta constitutiva",
    "Poderes",
    "Cédula fiscal",
    "Identificación del representante legal",
    "Comprobante de domicilio del representante legal",
    "Comprobante de domicilio",
    "Estado de cuenta bancario",
]
# El Contrato se carga en cada contrato (HU-22): ya no es requisito de alta.
MORAL_OPTIONAL = ["Opinión de cumplimiento", "Propuesta económica", "Debida diligencia", "Ubicación"]
PHYSICAL_REQUIRED = ["Cédula fiscal", "Comprobante de domicilio", "Estado de cuenta bancario", "Identificación oficial"]


def supplier(
    supplier_type=SupplierType.PERSONA_MORAL, origin=SupplierOrigin.NATIONAL, quotation=False
) -> SimpleNamespace:
    return SimpleNamespace(id=0, supplier_type=supplier_type, origin=origin, economic_proposal=quotation)


def document(code: str, document_date: date | None = None, document_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=document_id, document_type=code, document_date=document_date)


def checklist_for(target, *codes, document_date=None) -> requirements.Checklist:
    current = {code: document(code, document_date, index) for index, code in enumerate(codes, start=1)}
    with SessionLocal() as db:
        return requirements.build_checklist(requirements.catalog(db), target, current)


def names(rows) -> list[str]:
    return [row.document_type.name for row in rows]


# --- Catalogo y requisitos por tipo de proveedor ------------------------------------------------------------------


def test_catalogo_inicial_en_espanol_y_en_orden():
    with SessionLocal() as db:
        loaded = requirements.catalog(db)
    assert [(t.code, t.name) for t in loaded if t.is_system] == [(code, name) for code, name, *_ in SEEDED]
    assert len(SEEDED) == 13
    assert all(t.is_active for t in loaded if t.is_system)


def test_tipo_de_proveedor():
    assert requirements.profile(supplier()) == RequirementProfile.PERSONA_MORAL
    assert requirements.profile(supplier(SupplierType.PERSONA_FISICA)) == RequirementProfile.PERSONA_FISICA
    # El internacional es un tipo propio, sin importar su tipo de persona.
    international = supplier(SupplierType.PERSONA_FISICA, SupplierOrigin.INTERNATIONAL)
    assert requirements.profile(international) == RequirementProfile.INTERNATIONAL


def test_requisitos_de_una_persona_moral_nacional():
    checklist = checklist_for(supplier())
    assert names(r for r in checklist.rows if r.exigible) == MORAL_REQUIRED
    assert names(r for r in checklist.rows if not r.exigible) == MORAL_OPTIONAL
    assert not {"Identificación oficial", "Contrato"} & set(names(checklist.rows))
    assert checklist.label == "Faltan 7 requisitos obligatorios"


def test_requisitos_de_una_persona_fisica_nacional():
    checklist = checklist_for(supplier(SupplierType.PERSONA_FISICA))
    assert sorted(names(r for r in checklist.rows if r.exigible)) == sorted(PHYSICAL_REQUIRED)
    assert not {"Acta constitutiva", "Poderes", "Contrato"} & set(names(checklist.rows))


def test_proveedor_internacional_sin_requisitos():
    checklist = checklist_for(supplier(origin=SupplierOrigin.INTERNATIONAL))
    assert checklist.rows == [] and checklist.pending == [] and not checklist.has_exigible
    assert checklist.label == "Sin requisitos de alta configurados para proveedores internacionales"


def test_propuesta_economica_exigible_por_cotizacion():
    row = next(r for r in checklist_for(supplier(quotation=True)).rows if r.document_type.code == "ECONOMIC_PROPOSAL")
    assert row.exigible and row.level == DocumentRequirement.OPTIONAL
    assert row.note == "Alta por cotización o licitación"
    row = next(r for r in checklist_for(supplier()).rows if r.document_type.code == "ECONOMIC_PROPOSAL")
    assert not row.exigible and row.note == "Exigible si el alta es por cotización o licitación"


def test_requisitos_pendientes_y_completos():
    moral = supplier()
    checklist = checklist_for(moral, "INCORPORATION_ACT", "TAX_STATUS", "BANK_STATEMENT")
    assert checklist.label == "Faltan 4 requisitos obligatorios"
    assert names(checklist.pending) == [
        "Poderes",
        "Identificación del representante legal",
        "Comprobante de domicilio del representante legal",
        "Comprobante de domicilio",
    ]
    codes = ["INCORPORATION_ACT", "POWER_OF_ATTORNEY", "TAX_STATUS", "LEGAL_REP_ID", "LEGAL_REP_ADDRESS_PROOF"]
    assert checklist_for(moral, *codes, "ADDRESS_PROOF").label == "Falta 1 requisito obligatorio"
    assert checklist_for(moral, *codes, "ADDRESS_PROOF", "BANK_STATEMENT").label == "Requisitos de alta completos"


def test_documento_con_mas_de_tres_meses_cuenta_como_cargado():
    codes = [
        "INCORPORATION_ACT",
        "POWER_OF_ATTORNEY",
        "TAX_STATUS",
        "LEGAL_REP_ID",
        "LEGAL_REP_ADDRESS_PROOF",
        "ADDRESS_PROOF",
        "BANK_STATEMENT",
    ]
    checklist = checklist_for(supplier(), *codes, document_date=date.today() - timedelta(days=120))
    rows = {row.document_type.code: row for row in checklist.rows}
    assert rows["TAX_STATUS"].expired is True
    assert rows["INCORPORATION_ACT"].expired is False  # sin vigencia
    assert checklist.label == "Requisitos de alta completos"


def test_documento_de_un_tipo_que_no_aplica_queda_en_otros_documentos():
    checklist = checklist_for(supplier(SupplierType.PERSONA_FISICA), "INCORPORATION_ACT", "TAX_STATUS")
    assert [other.name for other in checklist.others] == ["Acta constitutiva"]
    assert "Acta constitutiva" not in names(checklist.rows)


def test_documentos_de_factura_no_cumplen_requisitos():
    moral = supplier_by_email("proveedor1@poc.local")
    with SessionLocal() as db:
        invoice_documents = db.scalars(
            select(Document).where(Document.supplier_id == moral.id, Document.invoice_id.is_not(None))
        ).all()
        expedient = requirements.expedient_documents(db, [moral.id])[moral.id]
    assert invoice_documents, "el seed carga documentos de factura con supplier_id"
    assert all(doc.invoice_id is None for doc in expedient.values())
    assert not {doc.id for doc in invoice_documents} & {doc.id for doc in expedient.values()}


# --- Checklist en el expediente -----------------------------------------------------------------------------------

PDF = b"%PDF-1.4\n%demo\n"


def requirement_rows(page: str) -> dict[str, str]:
    pattern = r'<strong>([^<]+)</strong><small class="requirement-status">([^<]+)</small>'
    return dict(re.findall(pattern, html.unescape(page)))


def expediente(client, supplier_id: int) -> str:
    return html.unescape(client.get(f"/suppliers/{supplier_id}").text)


def upload(client, supplier_id: int, document_type: str):
    return client.post(
        f"/suppliers/{supplier_id}/documents",
        data={"document_type": document_type, "csrf_token": csrf(client, "/")},
        files={"upload": ("documento.pdf", PDF, "application/octet-stream")},
        follow_redirects=False,
    )


def test_expediente_con_requisitos_pendientes_y_completos(client, registered_suppliers):
    (moral,) = registered_suppliers(requirements=False)
    add_expedient_documents(moral.id, ["INCORPORATION_ACT", "TAX_STATUS", "BANK_STATEMENT"])
    login(client)
    page = expediente(client, moral.id)
    assert "Faltan 4 requisitos obligatorios" in page
    rows = requirement_rows(page)
    pending = [name for name, status in rows.items() if status == "Obligatorio · Pendiente"]
    assert pending == [
        "Poderes",
        "Identificación del representante legal",
        "Comprobante de domicilio del representante legal",
        "Comprobante de domicilio",
    ]
    # El formulario de carga se abre y marca los obligatorios.
    assert "Poderes (obligatorio)" in page and "Opinión de cumplimiento (obligatorio)" not in page
    load_requirements(moral.id)
    assert "Requisitos de alta completos" in expediente(client, moral.id)


def test_documento_que_no_aplica_se_rechaza_sin_escribir_el_archivo(client, registered_suppliers):
    (physical,) = registered_suppliers(requirements=False, supplier_type=SupplierType.PERSONA_FISICA)
    folder = settings.storage_path / "suppliers" / str(physical.id)
    login(client)
    response = upload(client, physical.id, "INCORPORATION_ACT")
    assert response.status_code == 400 and "El documento no aplica a este proveedor" in response.text
    assert not folder.exists() or not any(folder.iterdir())
    assert upload(client, physical.id, "OTRO").status_code == 400
    assert upload(client, physical.id, "OFFICIAL_ID").status_code == 303


def test_expediente_del_proveedor_internacional_sin_requisitos(client):
    international = supplier_by_email("proveedor3@poc.local")
    login(client)
    page = expediente(client, international.id)
    assert "Sin requisitos de alta configurados para proveedores internacionales" in page
    assert "Agregar o reemplazar documento del expediente" not in page


# --- SUP-003 con la configuracion (motor-validacion) --------------------------------------------------------------

MORAL_CODES = [
    "INCORPORATION_ACT",
    "POWER_OF_ATTORNEY",
    "TAX_STATUS",
    "LEGAL_REP_ID",
    "LEGAL_REP_ADDRESS_PROOF",
    "ADDRESS_PROOF",
    "BANK_STATEMENT",
]


def sup(outcomes, code: str):
    return next(o for o in outcomes if o.rule_code == code)


def test_proveedor_demo_con_expediente_completo():
    invoice = invoice_by_number("A-CORRECTA")
    with SessionLocal() as db:
        result = db.scalar(
            select(ValidationResult).where(
                ValidationResult.invoice_id == invoice.id, ValidationResult.rule_code == "SUP-003"
            )
        )
    assert (result.status, result.message) == ("PASS", "Expediente mínimo disponible")


def test_facturas_demo_sin_fallas_de_expediente():
    """El seed carga a los proveedores demo los requisitos que les aplican (incluido Poderes): ninguna de sus facturas
    queda bloqueada por SUP-003 (reset_demo reproduce estos resultados)."""
    numbers = [
        "BORRADOR-001",
        "A-CORRECTA",
        "B-EXCEDE",
        "E-SEMANTICO",
        "D-SIN-VOBO",
        "REVISION-001",
        "ACEPTADA-001",
        "C-RFC-ERROR",
        "OBSERVACIONES-001",
        "ENVIADA-002",
        "INV-2026-0042",
    ]
    with SessionLocal() as db:
        statuses = {
            number: db.scalar(
                select(ValidationResult.status).where(
                    ValidationResult.invoice_id == invoice_by_number(number).id, ValidationResult.rule_code == "SUP-003"
                )
            )
            for number in numbers
        }
    # El borrador nunca se valido; la factura internacional no tiene requisitos de alta exigibles.
    expected = {number: "PASS" for number in numbers} | {"BORRADOR-001": None, "INV-2026-0042": "NOT_APPLICABLE"}
    assert statuses == expected


def test_opinion_de_cumplimiento_opcional():
    moral = SimpleNamespace(**vars(supplier()), status="ACTIVE")
    outcomes = supplier_rules(moral, None, checklist_for(moral, *MORAL_CODES))
    assert sup(outcomes, "SUP-003").status == "PASS"
    outcomes = supplier_rules(moral, None, checklist_for(moral, *MORAL_CODES[:-1]))
    assert sup(outcomes, "SUP-003").status == "FAIL"
    assert (
        sup(outcomes, "SUP-003").message == "Expediente del proveedor incompleto. Pendientes: Estado de cuenta bancario"
    )


def test_requisito_obligatorio_agregado_despues_de_la_autorizacion():
    moral = supplier_by_email("proveedor1@poc.local")
    with SessionLocal() as db:
        admin_id = db.scalar(select(User.id).where(User.email == "admin@poc.local"))
        requirements.create_type(
            db, admin_id, "Declaración de ISR por retenciones de salarios", None, persona_moral_requirement="REQUIRED"
        )
        supplier = db.get(type(moral), moral.id)
        outcomes = supplier_rules(supplier, None, requirements.checklist(db, supplier))
        db.rollback()  # la base es compartida
    result = sup(outcomes, "SUP-003")
    assert (result.status, result.severity) == ("FAIL", "ERROR")
    assert result.message == (
        "Expediente del proveedor incompleto. Pendientes: Declaración de ISR por retenciones de salarios"
    )
    assert supplier_by_email("proveedor1@poc.local").status == "ACTIVE"


def test_proveedor_internacional_con_un_requisito_configurado():
    international = supplier_by_email("proveedor3@poc.local")
    with SessionLocal() as db:
        supplier = db.get(type(international), international.id)
        initial = supplier_rules(supplier, None, requirements.checklist(db, supplier))
        db.execute(
            update(SupplierDocumentType)
            .where(SupplierDocumentType.code == "BANK_STATEMENT")
            .values(international_requirement=DocumentRequirement.REQUIRED)
        )
        configured = supplier_rules(supplier, None, requirements.checklist(db, supplier))
        db.rollback()
    assert sup(initial, "SUP-003").status == "NOT_APPLICABLE"
    assert sup(initial, "SUP-003").message == "No aplica a proveedores internacionales"
    assert sup(configured, "SUP-003").status == "FAIL"
    assert sup(configured, "SUP-003").message.endswith("Pendientes: Estado de cuenta bancario")
    assert sup(configured, "SUP-004").status == "NOT_APPLICABLE"


# --- Autorizacion condicionada (acceso-proveedores) ---------------------------------------------------------------

ALL_BUT_POWERS = [code for code in MORAL_CODES if code != "POWER_OF_ATTORNEY"]


def authorize(client, ids):
    data = {"supplier_ids": [str(i) for i in ids], "csrf_token": csrf(client, "/suppliers")}
    return client.post("/suppliers/authorize", data=data, follow_redirects=False)


def current(supplier_id: int):
    with SessionLocal() as db:
        found = db.get(type(supplier_by_email("proveedor1@poc.local")), supplier_id)
        user = db.scalar(select(User).where(User.supplier_id == supplier_id))
        return found, user


def audit_entries(action: str, entity_id: int | None = None) -> list[AuditLog]:
    with SessionLocal() as db:
        stmt = select(AuditLog).where(AuditLog.action == action)
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == str(entity_id))
        return list(db.scalars(stmt.order_by(AuditLog.id)))


def has_identity_account(email: str) -> bool:
    return any(account.email == email.lower() for account in get_identity_admin().accounts.values())


@pytest.mark.usefixtures("restore_notification_recipients")
def test_proveedor_con_requisitos_incompletos_no_se_autoriza(client, registered_suppliers):
    (complete,) = registered_suppliers()
    (incomplete,) = registered_suppliers(requirements=False)
    add_expedient_documents(incomplete.id, ALL_BUT_POWERS)
    login(client)
    response = authorize(client, [complete.id, incomplete.id])
    assert response.status_code == 303
    assert current(complete.id)[0].status == "ACTIVE"
    supplier, user = current(incomplete.id)
    assert supplier.status == "REGISTERED" and user is None
    assert not has_identity_account(incomplete.email)
    (bulk,) = audit_entries("SUPPLIER_BULK_AUTHORIZED")[-1:]
    assert bulk.new_value["requirements_incomplete"] == [incomplete.id]
    assert bulk.new_value["authorized"] == [complete.id]
    assert audit_entries("SUPPLIER_STATUS_CHANGED", incomplete.id) == []
    # El resumen lo lista con sus pendientes y la liga a su expediente.
    page = html.unescape(client.get(response.headers["location"]).text)
    assert "No autorizado: faltan requisitos de alta (Poderes)" in page
    assert f'href="/suppliers/{incomplete.id}"' in page


@pytest.mark.usefixtures("restore_notification_recipients")
def test_resumen_con_varios_requisitos_pendientes(client, registered_suppliers):
    (incomplete,) = registered_suppliers(requirements=False)
    add_expedient_documents(incomplete.id, [code for code in ALL_BUT_POWERS if code != "BANK_STATEMENT"])
    login(client)
    response = authorize(client, [incomplete.id])
    page = html.unescape(client.get(response.headers["location"]).text)
    assert "No autorizado: faltan requisitos de alta (Poderes, Estado de cuenta bancario)" in page
    assert current(incomplete.id)[0].status == "REGISTERED"


def test_listado_con_requisitos_pendientes(client, registered_suppliers):
    (complete,) = registered_suppliers()
    (incomplete,) = registered_suppliers(requirements=False)
    add_expedient_documents(incomplete.id, MORAL_CODES[:4])
    login(client)
    page = html.unescape(client.get("/suppliers", params={"status": "REGISTERED", "q": "Proveedor Acceso"}).text)
    assert f'name="supplier_ids" value="{complete.id}"' in page
    assert f'name="supplier_ids" value="{incomplete.id}"' not in page
    assert f'<a class="requirement-pending small" href="/suppliers/{incomplete.id}">Faltan 3 requisitos</a>' in page
    assert '<span class="text-danger">Faltan 3</span>' in page and '<span class="text-success">Completos</span>' in page


def test_boton_de_autorizacion_en_el_expediente(client, registered_suppliers):
    (complete,) = registered_suppliers()
    (incomplete,) = registered_suppliers(requirements=False)
    add_expedient_documents(incomplete.id, MORAL_CODES[:5])
    login(client)
    page = expediente(client, complete.id)
    assert 'data-confirm="Se autorizará a ' in page
    assert '<button class="btn btn-primary btn-sm" id="authorize-submit">' in page
    assert f'name="supplier_ids" value="{complete.id}"' in page
    page = expediente(client, incomplete.id)
    assert '<button class="btn btn-primary btn-sm" id="authorize-submit" disabled>' in page
    assert "Cargue los requisitos obligatorios para autorizar" in page and "Faltan 2 requisitos obligatorios" in page
    # Ni a un proveedor autorizado ni a otros roles.
    assert "Autorizar proveedor" not in expediente(client, supplier_by_email("proveedor1@poc.local").id)
    login(client, "pmo@poc.local")
    assert "Autorizar proveedor" not in expediente(client, complete.id)


@pytest.mark.usefixtures("restore_notification_recipients")
def test_autorizacion_individual_desde_el_expediente(client, registered_suppliers):
    (complete,) = registered_suppliers()
    login(client)
    response = authorize(client, [complete.id])
    supplier, user = current(complete.id)
    assert supplier.status == "ACTIVE" and user is not None
    assert "Autorizado · Credenciales enviadas" in html.unescape(client.get(response.headers["location"]).text)


@pytest.mark.usefixtures("restore_notification_recipients")
def test_peticion_manipulada_con_requisitos_pendientes(client, registered_suppliers):
    (incomplete,) = registered_suppliers(requirements=False)
    login(client)
    response = authorize(client, [incomplete.id])
    assert response.status_code == 303
    supplier, user = current(incomplete.id)
    assert supplier.status == "REGISTERED" and user is None
    assert "No autorizado: faltan requisitos de alta" in html.unescape(client.get(response.headers["location"]).text)


# --- Pantalla de configuracion (Administrador) --------------------------------------------------------------------

URL = "/admin/supplier-requirements"
PROFILE_KEYS = ("persona_moral", "persona_fisica", "international")


@pytest.fixture()
def restore_requirements():
    """La base de pruebas es compartida: restaura los niveles de los requisitos del sistema y borra los creados por
    la prueba (sus documentos los borra registered_suppliers)."""
    fields = [f"{key}_requirement" for key in PROFILE_KEYS]
    with SessionLocal() as db:
        saved = {
            t.code: tuple(getattr(t, field) for field in fields)
            for t in db.scalars(select(SupplierDocumentType).where(SupplierDocumentType.is_system))
        }
    yield
    with SessionLocal() as db:
        db.execute(delete(SupplierDocumentType).where(SupplierDocumentType.is_system.is_(False)))
        for document_type in db.scalars(select(SupplierDocumentType).where(SupplierDocumentType.is_system)):
            for field, value in zip(fields, saved[document_type.code], strict=True):
                setattr(document_type, field, value)
        db.commit()


def requirement_by(**filters) -> SupplierDocumentType | None:
    with SessionLocal() as db:
        return db.scalar(select(SupplierDocumentType).filter_by(**filters))


def config_snapshot() -> tuple:
    """Catalogo completo y numero de registros de auditoria de la configuracion."""
    with SessionLocal() as db:
        types = sorted(
            (
                t.code,
                t.name,
                t.description,
                t.persona_moral_requirement,
                t.persona_fisica_requirement,
                t.international_requirement,
                t.is_active,
            )
            for t in db.scalars(select(SupplierDocumentType))
        )
        audits = db.scalars(
            select(AuditLog.id).where(
                AuditLog.action.in_(
                    [
                        "SUPPLIER_REQUIREMENTS_UPDATED",
                        "SUPPLIER_DOCUMENT_TYPE_CREATED",
                        "SUPPLIER_DOCUMENT_TYPE_UPDATED",
                        "SUPPLIER_DOCUMENT_TYPE_STATUS_CHANGED",
                        "SUPPLIER_DOCUMENT_TYPE_DELETED",
                    ]
                )
            )
        ).all()
    return types, len(audits)


def matrix(page: str) -> dict[str, str]:
    """Campos del formulario de la matriz tal como los enviaria el navegador."""
    form = re.search(r'<form method="post" action="/admin/supplier-requirements">.*?</form>', page, re.S).group(0)
    values = {
        name: re.search(r'<option value="([A-Z_]+)" selected>', options).group(1)
        for name, options in re.findall(
            r'<select name="((?:persona_moral|persona_fisica|international)__[A-Z0-9_]+)"[^>]*>(.*?)</select>',
            form,
            re.S,
        )
    }
    values["config_version"] = re.search(r'name="config_version" value="([0-9a-f]+)"', form).group(1)
    return values


def save_matrix(client, changes: dict[str, str], form: dict[str, str] | None = None):
    data = {**(form or matrix(client.get(URL).text)), **changes, "csrf_token": csrf(client, URL)}
    return client.post(URL, data=data, follow_redirects=False)


def create_requirement(client, name: str, **levels: str):
    data = {"name": name, "description": "", **levels, "csrf_token": csrf(client, URL)}
    return client.post(f"{URL}/types", data=data, follow_redirects=False)


def set_status(client, type_id: int, active: bool):
    data = {"active": "true" if active else "false", "csrf_token": csrf(client, URL)}
    return client.post(f"{URL}/types/{type_id}/status", data=data, follow_redirects=False)


@pytest.mark.parametrize("email", ["pmo@poc.local", "proveedor1@poc.local"])
def test_configuracion_sin_acceso_para_pmo_y_proveedor(client, email):
    login(client, email)
    before = config_snapshot()
    token = csrf(client, "/invoices")
    type_id = requirement_by(code="LOCATION").id
    assert client.get(URL).status_code == 403
    routes = (
        URL,
        f"{URL}/types",
        f"{URL}/types/{type_id}",
        f"{URL}/types/{type_id}/status",
        f"{URL}/types/{type_id}/delete",
    )
    for route in routes:
        data = {"csrf_token": token, "name": "Intruso", "active": "false"}
        assert client.post(route, data=data, follow_redirects=False).status_code == 403
    assert config_snapshot() == before
    assert 'href="/admin/supplier-requirements"' not in client.get("/").text


@pytest.mark.parametrize("token", [None, "invalido"])
def test_configuracion_sin_token_csrf(client, token):
    login(client)
    page = client.get(URL).text
    assert 'href="/admin/supplier-requirements"' in page
    form = matrix(page)
    form["persona_moral__LOCATION"] = "REQUIRED"
    if token:
        form["csrf_token"] = token
    before = config_snapshot()
    assert client.post(URL, data=form, follow_redirects=False).status_code == 403
    assert config_snapshot() == before


def test_hacer_opcional_un_requisito(client, registered_suppliers, restore_requirements):
    (moral,) = registered_suppliers(requirements=False)
    add_expedient_documents(moral.id, ALL_BUT_POWERS)
    login(client)
    response = save_matrix(client, {"persona_moral__POWER_OF_ATTORNEY": "OPTIONAL"})
    assert response.status_code == 303
    assert "Configuración guardada" in client.get(response.headers["location"]).text
    page = expediente(client, moral.id)
    assert requirement_rows(page)["Poderes"] == "Opcional · Pendiente"
    assert "Requisitos de alta completos" in page


@pytest.mark.usefixtures("restore_notification_recipients")
def test_exigir_un_requisito_al_proveedor_internacional(client, registered_suppliers, restore_requirements):
    (international,) = registered_suppliers(
        requirements=False,
        origin=SupplierOrigin.INTERNATIONAL,
        rfc=None,
        foreign_tax_id=f"TST-{uuid4().hex[:8].upper()}",
        country="US",
    )
    login(client)
    assert save_matrix(client, {"international__BANK_STATEMENT": "REQUIRED"}).status_code == 303
    assert requirement_rows(expediente(client, international.id)) == {
        "Estado de cuenta bancario": "Obligatorio · Pendiente"
    }
    authorize(client, [international.id])
    assert current(international.id)[0].status == "REGISTERED"


def test_guardar_sin_cambios(client, restore_requirements):
    login(client)
    before = config_snapshot()
    response = save_matrix(client, {})
    assert response.status_code == 303
    assert "Sin cambios" in client.get(response.headers["location"]).text
    assert config_snapshot() == before


def test_nivel_invalido(client, restore_requirements):
    login(client)
    before = config_snapshot()
    response = save_matrix(client, {"persona_moral__LOCATION": "REQUIRED", "international__LOCATION": "MANDATORY"})
    assert response.status_code == 400 and "Nivel de exigencia inválido" in response.text
    assert config_snapshot() == before


def test_falta_el_nivel_de_un_requisito(client, restore_requirements):
    login(client)
    form = matrix(client.get(URL).text)
    del form["persona_fisica__TAX_STATUS"]
    before = config_snapshot()
    assert save_matrix(client, {"persona_moral__LOCATION": "REQUIRED"}, form).status_code == 400
    assert config_snapshot() == before


def test_dos_administradores_editan_a_la_vez(client, restore_requirements):
    login(client)
    stale = matrix(client.get(URL).text)
    assert save_matrix(client, {"persona_moral__LOCATION": "REQUIRED"}).status_code == 303
    response = save_matrix(client, {"persona_fisica__LOCATION": "REQUIRED"}, stale)
    assert response.status_code == 409
    assert "La configuración cambió mientras la editaba. Recargue la página." in html.unescape(response.text)
    location = requirement_by(code="LOCATION")
    assert (location.persona_moral_requirement, location.persona_fisica_requirement) == ("REQUIRED", "OPTIONAL")


def test_cambio_de_nivel_auditado(client, restore_requirements):
    login(client)
    assert save_matrix(client, {"persona_moral__POWER_OF_ATTORNEY": "OPTIONAL"}).status_code == 303
    (entry,) = audit_entries("SUPPLIER_REQUIREMENTS_UPDATED")[-1:]
    assert entry.user_id == current_admin_id()
    assert entry.old_value == {"POWER_OF_ATTORNEY": {"persona_moral": "REQUIRED"}}
    assert entry.new_value == {"POWER_OF_ATTORNEY": {"persona_moral": "OPTIONAL"}}


def current_admin_id() -> int:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == "admin@poc.local"))


# --- Requisitos del Administrador ---------------------------------------------------------------------------------

ISR = "Declaración de ISR por retenciones de salarios"


def test_alta_de_un_requisito(client, registered_suppliers, restore_requirements):
    (moral,) = registered_suppliers()
    login(client)
    response = create_requirement(client, ISR, persona_moral_requirement="REQUIRED")
    assert response.status_code == 303
    assert "Requisito creado" in client.get(response.headers["location"]).text
    created = requirement_by(name=ISR)
    assert created.code == f"REQUISITO_{created.id}" and created.is_active and not created.is_system
    assert (created.persona_fisica_requirement, created.international_requirement) == (
        "NOT_APPLICABLE",
        "NOT_APPLICABLE",
    )
    assert ISR in client.get(URL).text
    assert requirement_rows(expediente(client, moral.id))[ISR] == "Obligatorio · Pendiente"
    (entry,) = audit_entries("SUPPLIER_DOCUMENT_TYPE_CREATED", created.id)
    assert entry.new_value == {
        "code": created.code,
        "name": ISR,
        "persona_moral": "REQUIRED",
        "persona_fisica": "NOT_APPLICABLE",
        "international": "NOT_APPLICABLE",
    }


def test_formulario_de_alta_con_niveles_en_no_aplica(client):
    login(client)
    page = client.get(URL).text
    for key in PROFILE_KEYS:
        pattern = rf'<select id="new-{key}" name="{key}_requirement"[^>]*>(.*?)</select>'
        options = re.search(pattern, page, re.S).group(1)
        assert re.findall(r'<option value="([A-Z_]+)" selected>', options) == ["NOT_APPLICABLE"], key


def test_requisito_con_nombre_repetido(client, restore_requirements):
    login(client)
    before = config_snapshot()
    response = create_requirement(client, "  cédula   FISCAL ")
    assert response.status_code == 409 and "Ya existe un requisito con ese nombre" in response.text
    assert config_snapshot() == before


def test_desactivacion_y_reactivacion(client, registered_suppliers, restore_requirements):
    login(client)
    create_requirement(client, ISR, persona_moral_requirement="REQUIRED")
    created = requirement_by(name=ISR)
    (moral,) = registered_suppliers()  # sus requisitos ya incluyen el nuevo
    assert set_status(client, created.id, False).status_code == 303
    inactive = html.unescape(client.get(URL).text).split("Requisitos inactivos")[1]
    assert ISR in inactive and created.code in inactive and "Reactivar" in inactive
    assert ISR not in requirement_rows(expediente(client, moral.id))
    others = expediente(client, moral.id).split("Otros documentos del expediente")[1]
    assert ISR in others and f"/suppliers/{moral.id}/documents/" in others
    with SessionLocal() as db:
        found = db.get(type(supplier_by_email("proveedor1@poc.local")), moral.id)
        assert all(t.code != created.code for t in requirements.pending_requirements(db, [found])[moral.id])
    assert set_status(client, created.id, True).status_code == 303
    reactivated = requirement_by(id=created.id)
    assert reactivated.is_active and reactivated.persona_moral_requirement == "REQUIRED"
    assert len(audit_entries("SUPPLIER_DOCUMENT_TYPE_STATUS_CHANGED", created.id)) == 2


def test_requisito_del_sistema_no_se_edita_ni_se_desactiva(client):
    login(client)
    tax_status = requirement_by(code="TAX_STATUS")
    before = config_snapshot()
    data = {"name": "Otro nombre", "description": "", "csrf_token": csrf(client, URL)}
    response = client.post(f"{URL}/types/{tax_status.id}", data=data, follow_redirects=False)
    assert response.status_code == 409
    assert "Los requisitos del sistema no se pueden editar ni desactivar" in response.text
    assert set_status(client, tax_status.id, False).status_code == 409
    assert config_snapshot() == before


def test_edicion_de_un_requisito(client, restore_requirements):
    login(client)
    create_requirement(client, ISR)
    created = requirement_by(name=ISR)
    data = {"name": "Declaración anual de ISR", "description": "Del último ejercicio", "csrf_token": csrf(client, URL)}
    response = client.post(f"{URL}/types/{created.id}", data=data, follow_redirects=False)
    assert response.status_code == 303
    edited = requirement_by(id=created.id)
    assert (edited.name, edited.description, edited.code) == (
        "Declaración anual de ISR",
        "Del último ejercicio",
        created.code,
    )
    (entry,) = audit_entries("SUPPLIER_DOCUMENT_TYPE_UPDATED", created.id)
    assert entry.old_value == {"name": ISR, "description": None}


def delete_requirement(client, type_id: int, token: str | None = "auto"):
    data = {"csrf_token": csrf(client, URL)} if token == "auto" else ({"csrf_token": token} if token else {})
    return client.post(f"{URL}/types/{type_id}/delete", data=data, follow_redirects=False)


def config_row(page: str, name: str) -> str:
    table = re.search(r"<h2>Configuración por tipo de proveedor</h2>.*?</table>", page, re.S).group(0)
    return re.search(rf"<tr><td><strong>{re.escape(name)}</strong>.*?</tr>", table, re.S).group(0)


def test_acciones_editar_y_eliminar_solo_en_requisitos_del_administrador(client, restore_requirements):
    login(client)
    create_requirement(client, ISR)
    created = requirement_by(name=ISR)
    page = html.unescape(client.get(URL).text)
    row = config_row(page, ISR)
    assert f'href="?editar={created.id}#editar-{created.id}"' in row and f'form="eliminar-{created.id}"' in row
    assert f"¿Eliminar «{ISR}»?" in row
    system = config_row(page, "Cédula fiscal")
    assert "Editar" not in system and "Eliminar" not in system
    opened = client.get(f"{URL}?editar={created.id}").text
    assert f'id="editar-{created.id}" class="admin-create border-bottom" open' in opened
    assert set_status(client, created.id, False).status_code == 303
    inactive = html.unescape(client.get(URL).text).split("Requisitos inactivos")[1]
    assert f'href="?editar={created.id}#editar-{created.id}"' in inactive


@pytest.mark.parametrize("inactive", [False, True])
def test_eliminacion_de_un_requisito_sin_documentos(client, restore_requirements, inactive):
    login(client)
    create_requirement(client, ISR, persona_moral_requirement="REQUIRED")
    created = requirement_by(name=ISR)
    if inactive:
        assert set_status(client, created.id, False).status_code == 303
    response = delete_requirement(client, created.id)
    assert response.status_code == 303 and response.headers["location"] == f"{URL}?ok=deleted"
    assert requirement_by(id=created.id) is None
    page = html.unescape(client.get(response.headers["location"]).text)
    assert "Tipo eliminado" in page and ISR not in page
    (entry,) = audit_entries("SUPPLIER_DOCUMENT_TYPE_DELETED", created.id)
    assert entry.user_id == current_admin_id()
    assert entry.old_value == {
        "code": created.code,
        "name": ISR,
        "description": None,
        "is_active": not inactive,
        "persona_moral": "REQUIRED",
        "persona_fisica": "NOT_APPLICABLE",
        "international": "NOT_APPLICABLE",
    }


def test_eliminacion_de_un_requisito_con_documentos(client, registered_suppliers, restore_requirements):
    login(client)
    create_requirement(client, ISR, persona_moral_requirement="REQUIRED")
    created = requirement_by(name=ISR)
    (moral,) = registered_suppliers()
    assert upload(client, moral.id, created.code).status_code == 303
    before = config_snapshot()
    response = delete_requirement(client, created.id)
    assert response.status_code == 409
    assert "El tipo ya tiene documentos cargados; desactívelo en su lugar" in html.unescape(response.text)
    assert config_snapshot() == before


def test_eliminacion_de_un_requisito_del_sistema_inexistente_o_sin_csrf(client, restore_requirements):
    login(client)
    before = config_snapshot()
    response = delete_requirement(client, requirement_by(code="TAX_STATUS").id)
    assert response.status_code == 409 and "Los elementos del sistema no se pueden eliminar" in response.text
    assert delete_requirement(client, 999_999).status_code == 404
    create_requirement(client, ISR)
    created = requirement_by(name=ISR)
    before = config_snapshot()
    assert delete_requirement(client, created.id, None).status_code == 403
    assert delete_requirement(client, created.id, "invalido").status_code == 403
    assert config_snapshot() == before


# --- El Contrato sale del alta del proveedor (HU-22) --------------------------------------------------------------


def test_contrato_con_nivel_fijo_en_la_pantalla(client):
    login(client)
    page = html.unescape(client.get(URL).text)
    row = page.split("<strong>Contrato</strong>")[1].split("</tr>")[0]
    assert row.count("bi-lock-fill") == 3 and row.count("No aplica") == 3 and "Se carga en cada contrato" in row
    assert "<select" not in row
    assert "persona_moral__SUPPLIER_CONTRACT" not in matrix(page)


@pytest.mark.parametrize(
    ("key", "plural"), [("persona_moral", "personas morales"), ("international", "proveedores internacionales")]
)
def test_peticion_manipulada_sobre_el_contrato(client, restore_requirements, key, plural):
    login(client)
    before = config_snapshot()
    response = save_matrix(client, {"persona_moral__LOCATION": "REQUIRED", f"{key}__SUPPLIER_CONTRACT": "OPTIONAL"})
    assert response.status_code == 409
    assert f"Contrato tiene un nivel fijo para {plural}" in html.unescape(response.text)
    assert config_snapshot() == before


def test_guardar_sin_los_niveles_del_contrato(client, restore_requirements):
    login(client)
    assert save_matrix(client, {"persona_moral__LOCATION": "REQUIRED"}).status_code == 303
    assert requirement_by(code="LOCATION").persona_moral_requirement == "REQUIRED"


def test_contrato_cargado_antes_en_el_expediente(client, registered_suppliers):
    (moral,) = registered_suppliers()
    add_expedient_documents(moral.id, ["SUPPLIER_CONTRACT"])
    login(client)
    page = expediente(client, moral.id)
    assert "Contrato" not in requirement_rows(page)
    others = page.split("Otros documentos del expediente")[1]
    assert "<strong>Contrato</strong>" in others and f"/suppliers/{moral.id}/documents/" in others
    response = upload(client, moral.id, "SUPPLIER_CONTRACT")
    assert response.status_code == 400 and "El documento no aplica a este proveedor" in response.text
