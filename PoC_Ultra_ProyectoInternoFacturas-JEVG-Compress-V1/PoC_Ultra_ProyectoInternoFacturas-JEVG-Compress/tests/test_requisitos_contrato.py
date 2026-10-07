"""Requisitos de alta del contrato (HU-22): catalogo, expediente y documentos del contrato, activacion, listado,
DOC-005 y configuracion del Administrador."""

import html
import re
import secrets
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, update

from app.core.config import settings
from app.core.constants import ContractStatus, DocumentRequirement
from app.core.database import SessionLocal
from app.models import AuditLog, Contract, ContractDocumentType, Document, Invoice, User, ValidationResult
from app.rules.document_rules import contract_rule
from app.services import contract_requirements_service as requirements
from app.services.submission_service import SubmissionOutcome, submit_invoice
from app.services.validation_engine import run_validation
from tests.conftest import csrf, invoice_by_number, login, migration_module, supplier_by_email
from tests.test_flujo import count_queries

SEEDED = migration_module("0017_contract_document_types").SYSTEM_TYPES
MORAL = "proveedor1@poc.local"  # proveedor de los contratos de new_contracts


def names(rows) -> list[str]:
    return [row.document_type.name for row in rows]


def document(code: str, document_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=document_id, document_type=code)


# --- Catalogo y requisitos que aplican ----------------------------------------------------------------------------


def test_catalogo_inicial_en_espanol_y_en_orden():
    with SessionLocal() as db:
        loaded = [t for t in requirements.catalog(db) if t.is_system]
    assert [(t.code, t.name, t.requirement, t.allows_multiple) for t in loaded] == [
        (code, name, level, multiple) for code, name, _, level, multiple in SEEDED
    ]
    assert [t.name for t in loaded] == ["Contrato", "Orden de compra", "Anexos"]
    assert all(t.is_active for t in loaded)


def test_requisitos_con_la_configuracion_inicial():
    with SessionLocal() as db:
        checklist = requirements.build_checklist(requirements.catalog(db), {})
    assert names(checklist.rows) == ["Contrato", "Orden de compra", "Anexos"]
    assert names(r for r in checklist.rows if r.required) == ["Contrato"]
    assert names(checklist.pending) == ["Contrato"]
    assert checklist.label == "Falta 1 requisito obligatorio"


def test_varios_archivos_vigentes_cumplen_un_requisito():
    current = {
        "SIGNED_CONTRACT": [document("SIGNED_CONTRACT", 1)],
        "CONTRACT_ANNEXES": [document("CONTRACT_ANNEXES", 2), document("CONTRACT_ANNEXES", 3)],
    }
    with SessionLocal() as db:
        checklist = requirements.build_checklist(requirements.catalog(db), current)
    assert checklist.label == "Requisitos del contrato completos"
    annexes = next(row for row in checklist.rows if row.document_type.code == "CONTRACT_ANNEXES")
    assert [d.id for d in annexes.documents] == [2, 3]


def test_etiquetas_de_pendientes():
    assert requirements.pending_label(0) == "Requisitos del contrato completos"
    assert requirements.pending_label(1) == "Falta 1 requisito obligatorio"
    assert requirements.pending_label(3) == "Faltan 3 requisitos obligatorios"


def test_documento_de_un_requisito_que_dejo_de_aplicar_queda_en_otros_documentos():
    current = {
        "SIGNED_CONTRACT": [document("SIGNED_CONTRACT", 1)],
        "CONTRACT_ANNEXES": [document("CONTRACT_ANNEXES", 2)],
    }
    with SessionLocal() as db:
        types = requirements.catalog(db)
        next(t for t in types if t.code == "CONTRACT_ANNEXES").requirement = DocumentRequirement.NOT_APPLICABLE
        checklist = requirements.build_checklist(types, current)
        assert "Anexos" not in names(checklist.rows)
        assert [(other.name, other.document.id) for other in checklist.others] == [("Anexos", 2)]
        db.rollback()


def test_documentos_de_factura_y_del_expediente_no_cuentan_para_el_contrato(new_contracts):
    contract = new_contracts()
    supplier = supplier_by_email(MORAL)
    invoice = invoice_by_number("A-CORRECTA")
    with SessionLocal() as db:
        # Un "Contrato" cargado en la factura (HU-04) o en el expediente (HU-21) no es el contrato firmado.
        for owner in ({"invoice_id": invoice.id, "supplier_id": supplier.id}, {"supplier_id": supplier.id}):
            db.add(
                Document(
                    **owner,
                    document_type="SIGNED_CONTRACT",
                    original_filename="contrato.pdf",
                    stored_filename="contrato.pdf",
                    path="invoices/0/contrato.pdf",
                    mime_type="application/pdf",
                    file_size=1,
                    sha256="0" * 64,
                    uploaded_by=invoice.uploaded_by,
                )
            )
        db.flush()
        assert requirements.contract_documents(db, [contract.id]) == {contract.id: {}}
        assert requirements.pending_names(db, db.get(Contract, contract.id)) == ["Contrato"]
        db.rollback()


def test_contratos_demo_con_su_contrato_firmado():
    with SessionLocal() as db:
        contracts = list(db.scalars(select(Contract).where(Contract.status == ContractStatus.ACTIVE)))
        pending = requirements.pending_requirements(db, contracts)
    assert contracts and all(not types for types in pending.values())


# --- Alta y estatus del contrato ----------------------------------------------------------------------------------

PDF = b"%PDF-1.4\n%demo\n"


def contract_page(client, contract_id: int) -> str:
    return html.unescape(client.get(f"/contracts/{contract_id}").text)


def requirement_rows(page: str) -> dict[str, str]:
    pattern = r'<strong>([^<]+)</strong><small class="requirement-status">([^<]+)</small>'
    return dict(re.findall(pattern, page))


def upload(client, contract_id: int, code: str, replaces: str = "", filename: str = "documento.pdf"):
    return client.post(
        f"/contracts/{contract_id}/documents",
        data={"document_type": code, "replaces_document_id": replaces, "csrf_token": csrf(client, "/")},
        files={"upload": (filename, PDF, "application/octet-stream")},
        follow_redirects=False,
    )


def documents_of(contract_id: int) -> list[Document]:
    with SessionLocal() as db:
        return list(db.scalars(select(Document).where(Document.contract_id == contract_id).order_by(Document.id)))


def audit_entries(action: str, entity_id: int | None = None) -> list[AuditLog]:
    with SessionLocal() as db:
        stmt = select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == str(entity_id))
        return list(db.scalars(stmt))


def contract_status(contract_id: int) -> str:
    with SessionLocal() as db:
        return db.get(Contract, contract_id).status


def test_alta_de_contrato_registrado(client, new_contracts):
    login(client)
    project = f"Contrato HU22 alta {secrets.token_hex(3)}"
    data = {
        "supplier_id": supplier_by_email(MORAL).id,
        "project_name": project,
        "project_leader": "Lider",
        "authorized_technology": "Power Platform",
        "authorized_amount": "1000.00",
        "currency": "MXN",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "csrf_token": csrf(client, "/contracts"),
    }
    response = client.post("/contracts", data=data, follow_redirects=False)
    with SessionLocal() as db:
        created = db.scalar(select(Contract).where(Contract.project_name == project))
    new_contracts.track(created.id)
    assert created.status == ContractStatus.REGISTERED
    assert response.headers["location"] == f"/contracts/{created.id}?ok=created"
    page = html.unescape(client.get(response.headers["location"]).text)
    assert "Contrato creado. Cargue sus requisitos para activarlo." in page and "Registrado" in page
    assert audit_entries("CONTRACT_CREATED", created.id)


def test_contrato_registrado_no_se_ofrece_al_facturar(client, new_contracts):
    contract = new_contracts()
    login(client, MORAL)
    assert contract.project_name not in client.get("/invoices/new").text
    data = {
        "supplier_id": contract.supplier_id,
        "contract_id": contract.id,
        "invoice_number": f"HU22-{secrets.token_hex(4)}",
        "service_period": "08/2026",
        "project_name": contract.project_name,
        "csrf_token": csrf(client, "/invoices/new"),
    }
    response = client.post("/invoices/new", data=data, follow_redirects=False)
    assert response.status_code == 400 and "El contrato no está activo" in html.unescape(response.text)
    assert invoice_by_number(data["invoice_number"]) is None


# --- Expediente del contrato --------------------------------------------------------------------------------------


def test_expediente_con_requisitos_pendientes(client, new_contracts):
    contract = new_contracts()
    login(client)
    page = contract_page(client, contract.id)
    assert "Falta 1 requisito obligatorio" in page
    assert requirement_rows(page) == {
        "Contrato": "Obligatorio · Pendiente",
        "Orden de compra": "Opcional · Pendiente",
        "Anexos": "Opcional · Pendiente",
    }
    assert "+ Agregar documento del contrato" in page


def test_requisitos_completos_con_varios_anexos(client, new_contracts):
    contract = new_contracts()
    login(client)
    assert upload(client, contract.id, "SIGNED_CONTRACT", filename="contrato.pdf").status_code == 303
    assert upload(client, contract.id, "CONTRACT_ANNEXES", filename="anexo-tecnico.pdf").status_code == 303
    assert upload(client, contract.id, "CONTRACT_ANNEXES", filename="anexo-economico.pdf").status_code == 303
    page = contract_page(client, contract.id)
    assert "Requisitos del contrato completos" in page
    assert requirement_rows(page)["Anexos"] == "Opcional · Cargado"
    annexes = page.split("<strong>Anexos</strong>")[1].split("</span>")[0]
    assert "anexo-tecnico.pdf" in annexes and "anexo-economico.pdf" in annexes


def test_pmo_consulta_y_descarga(client, new_contracts):
    contract = new_contracts()
    login(client)
    upload(client, contract.id, "SIGNED_CONTRACT", filename="contrato.pdf")
    (signed,) = documents_of(contract.id)
    login(client, "pmo@poc.local")
    page = contract_page(client, contract.id)
    assert "Requisitos del contrato completos" in page and "contrato.pdf" in page
    assert "+ Agregar documento del contrato" not in page and "Activar contrato" not in page
    response = client.get(f"/contracts/{contract.id}/documents/{signed.id}/download")
    assert response.status_code == 200 and response.content == PDF
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment")


def test_proveedor_sin_acceso_al_expediente_del_contrato(client, new_contracts):
    contract = new_contracts(codes=["SIGNED_CONTRACT"])
    (signed,) = documents_of(contract.id)
    login(client, MORAL)  # proveedor del contrato
    assert client.get(f"/contracts/{contract.id}").status_code == 403
    assert client.get(f"/contracts/{contract.id}/documents/{signed.id}/download").status_code == 403


def test_documento_de_otro_contrato_y_contrato_inexistente(client, new_contracts):
    first, second = new_contracts(codes=["SIGNED_CONTRACT"]), new_contracts()
    (signed,) = documents_of(first.id)
    login(client)
    assert client.get(f"/contracts/{second.id}/documents/{signed.id}/download").status_code == 404
    assert client.get("/contracts/999999").status_code == 404


# --- Carga de documentos del contrato -----------------------------------------------------------------------------


def test_carga_del_contrato_firmado(client, new_contracts):
    contract = new_contracts()
    login(client)
    response = upload(client, contract.id, "SIGNED_CONTRACT", filename="contrato.pdf")
    assert response.headers["location"] == f"/contracts/{contract.id}?ok=uploaded"
    (signed,) = documents_of(contract.id)
    assert signed.is_current and signed.supplier_id is None and signed.invoice_id is None
    assert signed.path.startswith(f"contracts/{contract.id}/") and (settings.storage_path / signed.path).is_file()
    assert requirement_rows(contract_page(client, contract.id))["Contrato"] == "Obligatorio · Cargado"
    (entry,) = audit_entries("CONTRACT_DOCUMENT_UPLOADED", signed.id)
    assert entry.new_value == {"type": "SIGNED_CONTRACT", "contract_id": contract.id}


def test_reemplazo_del_contrato_firmado(client, new_contracts):
    contract = new_contracts()
    login(client)
    upload(client, contract.id, "SIGNED_CONTRACT", filename="contrato-v1.pdf")
    upload(client, contract.id, "SIGNED_CONTRACT", filename="contrato-v2.pdf")
    first, second = documents_of(contract.id)
    assert not first.is_current and second.is_current and second.replaced_document_id == first.id
    assert audit_entries("CONTRACT_DOCUMENT_REPLACED", second.id)
    page = contract_page(client, contract.id)
    assert "contrato-v2.pdf" in page and "contrato-v1.pdf" not in page


def test_segundo_anexo_y_reemplazo_de_uno(client, new_contracts):
    contract = new_contracts()
    login(client)
    upload(client, contract.id, "CONTRACT_ANNEXES", filename="anexo-1.pdf")
    upload(client, contract.id, "CONTRACT_ANNEXES", filename="anexo-2.pdf")
    first, second = documents_of(contract.id)
    assert first.is_current and second.is_current  # sin "Reemplaza a" se agrega
    assert upload(client, contract.id, "CONTRACT_ANNEXES", str(first.id), "anexo-1b.pdf").status_code == 303
    first, second, third = documents_of(contract.id)
    assert (first.is_current, second.is_current, third.is_current) == (False, True, True)
    assert third.replaced_document_id == first.id


@pytest.mark.parametrize("replaces", ["999999", "texto", "signed"])
def test_documento_a_reemplazar_que_no_corresponde(client, new_contracts, replaces):
    contract = new_contracts(codes=["SIGNED_CONTRACT"])
    (signed,) = documents_of(contract.id)
    login(client)
    response = upload(client, contract.id, "CONTRACT_ANNEXES", str(signed.id) if replaces == "signed" else replaces)
    assert response.status_code == 400
    assert "El documento a reemplazar no corresponde a este requisito" in html.unescape(response.text)
    assert [d.id for d in documents_of(contract.id)] == [signed.id]


def test_anexo_en_un_contrato_activo(client, new_contracts):
    contract = new_contracts(codes=["SIGNED_CONTRACT"], status=ContractStatus.ACTIVE)
    login(client)
    assert upload(client, contract.id, "CONTRACT_ANNEXES").status_code == 303
    assert contract_status(contract.id) == ContractStatus.ACTIVE


@pytest.mark.parametrize("code", ["INCORPORATION_ACT", "OTRO", "CONTRACT"])
def test_tipo_que_no_aplica_sin_escribir_el_archivo(client, new_contracts, code):
    contract = new_contracts()
    folder = settings.storage_path / "contracts" / str(contract.id)
    login(client)
    response = upload(client, contract.id, code)
    assert response.status_code == 400 and "El documento no aplica a este contrato" in html.unescape(response.text)
    assert not folder.exists() or not any(folder.iterdir())
    assert documents_of(contract.id) == []


def test_contenido_que_no_corresponde_a_la_extension(client, new_contracts):
    contract = new_contracts()
    login(client)
    response = client.post(
        f"/contracts/{contract.id}/documents",
        data={"document_type": "SIGNED_CONTRACT", "csrf_token": csrf(client, "/")},
        files={"upload": ("contrato.pdf", b"MZ ejecutable", "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 400 and "El contenido no corresponde a un PDF" in response.text
    assert documents_of(contract.id) == []


def test_carga_en_un_contrato_inactivo(client, new_contracts):
    contract = new_contracts(status=ContractStatus.INACTIVE)
    login(client)
    response = upload(client, contract.id, "SIGNED_CONTRACT")
    assert response.status_code == 409
    assert "Sólo se cargan documentos en un contrato Registrado o Activo" in html.unescape(response.text)


@pytest.mark.parametrize("email", ["pmo@poc.local", MORAL])
def test_pmo_y_proveedor_no_cargan(client, new_contracts, email):
    contract = new_contracts()
    folder = settings.storage_path / "contracts" / str(contract.id)
    login(client, email)
    assert upload(client, contract.id, "SIGNED_CONTRACT").status_code == 403
    assert not folder.exists() and documents_of(contract.id) == []


# --- Activacion ---------------------------------------------------------------------------------------------------


@pytest.fixture()
def restore_contract_requirements():
    """La base de pruebas es compartida: restaura los requisitos del sistema (nombre, descripcion, nivel y baja logica)
    y borra los creados por la prueba (sus documentos los borra new_contracts)."""
    fields = ("name", "description", "requirement", "is_active", "deleted_at", "deleted_by")
    with SessionLocal() as db:
        saved = {
            t.code: {field: getattr(t, field) for field in fields}
            for t in db.scalars(select(ContractDocumentType).where(ContractDocumentType.is_system))
        }
    yield
    with SessionLocal() as db:
        db.execute(delete(ContractDocumentType).where(ContractDocumentType.is_system.is_(False)))
        for document_type in db.scalars(select(ContractDocumentType).where(ContractDocumentType.is_system)):
            for field, value in saved[document_type.code].items():
                setattr(document_type, field, value)
        db.commit()


def set_level(code: str, level: str) -> None:
    with SessionLocal() as db:
        db.scalar(select(ContractDocumentType).where(ContractDocumentType.code == code)).requirement = level
        db.commit()


def activate(client, contract_id: int):
    data = {"csrf_token": csrf(client, "/")}
    return client.post(f"/contracts/{contract_id}/activate", data=data, follow_redirects=False)


def admin_id() -> int:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == "admin@poc.local"))


def test_activacion(client, new_contracts):
    contract = new_contracts()
    login(client)
    upload(client, contract.id, "SIGNED_CONTRACT")
    page = contract_page(client, contract.id)
    assert f'data-confirm="Se activará el contrato {contract.project_name} de ' in page
    assert re.search(r'id="activate-submit">', page), "el boton esta habilitado"
    response = activate(client, contract.id)
    assert response.headers["location"] == f"/contracts/{contract.id}?ok=activated"
    assert "Contrato activado" in html.unescape(client.get(response.headers["location"]).text)
    with SessionLocal() as db:
        activated = db.get(Contract, contract.id)
        assert (activated.status, activated.updated_by) == (ContractStatus.ACTIVE, admin_id())
    (entry,) = audit_entries("CONTRACT_STATUS_CHANGED", contract.id)
    assert (entry.user_id, entry.old_value, entry.new_value) == (
        admin_id(),
        {"status": "REGISTERED"},
        {"status": "ACTIVE"},
    )
    assert "Activar contrato" not in contract_page(client, contract.id)
    login(client, MORAL)
    assert contract.project_name in client.get("/invoices/new").text


def test_boton_deshabilitado_por_requisitos_y_peticion_manipulada(client, new_contracts):
    contract = new_contracts()
    login(client)
    page = contract_page(client, contract.id)
    assert 'id="activate-submit" disabled' in page and "Cargue los requisitos obligatorios para activar" in page
    response = activate(client, contract.id)
    assert response.status_code == 409
    assert "No se activó el contrato: faltan requisitos obligatorios (Contrato)" in html.unescape(response.text)
    assert contract_status(contract.id) == ContractStatus.REGISTERED
    assert audit_entries("CONTRACT_STATUS_CHANGED", contract.id) == []


def test_proveedor_no_autorizado(client, registered_suppliers, new_contracts):
    (supplier,) = registered_suppliers()
    contract = new_contracts(codes=["SIGNED_CONTRACT"], supplier_id=supplier.id)
    login(client)
    page = contract_page(client, contract.id)
    assert 'id="activate-submit" disabled' in page and "Autorice al proveedor para activar el contrato" in page
    assert f'href="/suppliers/{supplier.id}">Ver proveedor' in page
    response = activate(client, contract.id)
    assert response.status_code == 409
    assert "No se activó el contrato: el proveedor no está autorizado" in html.unescape(response.text)
    assert contract_status(contract.id) == ContractStatus.REGISTERED


def test_requisito_agregado_mientras_se_activaba(client, new_contracts, restore_contract_requirements):
    contract = new_contracts(codes=["SIGNED_CONTRACT"])
    login(client)
    assert re.search(r'id="activate-submit">', contract_page(client, contract.id))
    set_level("CONTRACT_PURCHASE_ORDER", "REQUIRED")  # otro Administrador, entre la vista y la activacion
    response = activate(client, contract.id)
    assert response.status_code == 409
    assert "No se activó el contrato: faltan requisitos obligatorios (Orden de compra)" in html.unescape(response.text)
    assert contract_status(contract.id) == ContractStatus.REGISTERED


def test_contrato_ya_activo(client, new_contracts):
    contract = new_contracts(codes=["SIGNED_CONTRACT"], status=ContractStatus.ACTIVE)
    login(client)
    response = activate(client, contract.id)
    assert response.status_code == 409
    assert "Sólo se puede activar un contrato Registrado" in html.unescape(response.text)
    assert audit_entries("CONTRACT_STATUS_CHANGED", contract.id) == []


@pytest.mark.parametrize("email", ["pmo@poc.local", MORAL])
def test_pmo_y_proveedor_no_activan(client, new_contracts, email):
    contract = new_contracts(codes=["SIGNED_CONTRACT"])
    login(client, email)
    assert activate(client, contract.id).status_code == 403
    assert contract_status(contract.id) == ContractStatus.REGISTERED


# --- Listado de contratos -----------------------------------------------------------------------------------------


def contract_row(page: str, contract_id: int) -> str:
    return html.unescape(page).split(f'<a href="/contracts/{contract_id}">')[1].split("</tr>")[0]


def test_listado_con_contrato_por_activar_y_activo_sin_documentos(client, new_contracts):
    registered = new_contracts()
    active = new_contracts(status=ContractStatus.ACTIVE)
    complete = new_contracts(codes=["SIGNED_CONTRACT"], status=ContractStatus.ACTIVE)
    login(client)
    page = client.get("/contracts", params={"q": "Contrato HU22"}).text
    assert "Registrado" in contract_row(page, registered.id) and "Faltan 1" in contract_row(page, registered.id)
    assert "Activo" in contract_row(page, active.id) and "Faltan 1" in contract_row(page, active.id)
    assert "Completos" in contract_row(page, complete.id)


def test_listado_sin_una_consulta_por_contrato(client, new_contracts):
    tag = f"HU22N1 {secrets.token_hex(3)}"
    for index in range(6):
        new_contracts(codes=["SIGNED_CONTRACT"] if index % 2 else (), project_name=f"{tag} {index}")
    login(client)
    many = count_queries(lambda: client.get("/contracts", params={"q": tag}))
    one = count_queries(lambda: client.get("/contracts", params={"q": f"{tag} 0"}))
    assert many == one


# --- DOC-005 (motor-validacion) -----------------------------------------------------------------------------------

DEMO_INVOICES = [
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


def doc_005(results):
    return next(r for r in results if r.rule_code == "DOC-005")


def test_facturas_demo_con_su_contrato_completo():
    """El seed carga el contrato firmado de los contratos demo: DOC-005 resulta PASS en todas las facturas validadas
    (reset_demo reproduce estos resultados)."""
    with SessionLocal() as db:
        results = {
            number: db.execute(
                select(ValidationResult.status, ValidationResult.message).where(
                    ValidationResult.invoice_id == invoice_by_number(number).id, ValidationResult.rule_code == "DOC-005"
                )
            ).one()
            for number in DEMO_INVOICES
        }
    assert results == {number: ("PASS", "Contrato/anexo disponible") for number in DEMO_INVOICES}


def test_contrato_activo_sin_contrato_firmado_impide_el_envio():
    """Contrato Activo de antes de la migracion, sin documentos; el "Contrato" cargado en la factura (HU-04) no
    cuenta. Se evalua en una transaccion que se revierte: la base es compartida."""
    with SessionLocal() as db:
        invoice = db.get(Invoice, invoice_by_number("A-CORRECTA").id)
        db.execute(update(Document).where(Document.contract_id == invoice.contract_id).values(is_current=False))
        contract_file = Document(
            invoice_id=invoice.id,
            supplier_id=invoice.supplier_id,
            document_type="CONTRACT",
            original_filename="contrato.pdf",
            stored_filename="contrato.pdf",
            path=f"invoices/{invoice.id}/contrato.pdf",
            mime_type="application/pdf",
            file_size=1,
            sha256="0" * 64,
            uploaded_by=invoice.uploaded_by,
        )
        db.add(contract_file)
        db.flush()
        result = submit_invoice(db, invoice, invoice.uploaded_by)
        failure = doc_005(result.failures)
        assert result.outcome == SubmissionOutcome.RULES_FAILED
        assert (failure.status, failure.severity, failure.message) == (
            "FAIL",
            "ERROR",
            "Faltan documentos del contrato: Contrato",
        )
        assert invoice.status == "UPLOADED"
        db.rollback()


def test_requisito_obligatorio_agregado_despues_de_la_activacion():
    with SessionLocal() as db:
        invoice = db.get(Invoice, invoice_by_number("A-CORRECTA").id)
        db.execute(
            update(ContractDocumentType)
            .where(ContractDocumentType.code == "CONTRACT_PURCHASE_ORDER")
            .values(requirement=DocumentRequirement.REQUIRED)
        )
        result = doc_005(run_validation(db, invoice)["results"])
        assert (result.status, result.message) == ("FAIL", "Faltan documentos del contrato: Orden de compra")
        assert invoice.contract.status == ContractStatus.ACTIVE
        db.rollback()


def test_factura_sin_contrato():
    with SessionLocal() as db:
        assert requirements.pending_names(db, None) is None
    result = contract_rule(None)
    assert (result.status, result.severity, result.message) == ("FAIL", "ERROR", "Falta contrato/anexo")
    assert contract_rule([]).status == "PASS"


# --- Pantalla de configuracion (Administrador) --------------------------------------------------------------------

URL = "/admin/contract-requirements"


def requirement_by(**filters) -> ContractDocumentType | None:
    with SessionLocal() as db:
        return db.scalar(select(ContractDocumentType).filter_by(**filters))


def config_snapshot() -> tuple:
    """Catalogo completo y numero de registros de auditoria de la configuracion."""
    with SessionLocal() as db:
        types = sorted(
            (t.code, t.name, t.description, t.requirement, t.allows_multiple, t.is_active)
            for t in db.scalars(select(ContractDocumentType))
        )
        audits = db.scalars(
            select(AuditLog.id).where(
                AuditLog.action.in_(
                    [
                        "CONTRACT_REQUIREMENTS_UPDATED",
                        "CONTRACT_DOCUMENT_TYPE_CREATED",
                        "CONTRACT_DOCUMENT_TYPE_UPDATED",
                        "CONTRACT_DOCUMENT_TYPE_RESTORED",
                        "CONTRACT_DOCUMENT_TYPE_DELETED",
                    ]
                )
            )
        ).all()
    return types, len(audits)


def levels_form(page: str) -> dict[str, str]:
    """Campos del formulario de niveles tal como los enviaria el navegador."""
    form = re.search(r'<form method="post" action="/admin/contract-requirements">.*?</form>', page, re.S).group(0)
    values = {
        name: re.search(r'<option value="([A-Z_]+)" selected>', options).group(1)
        for name, options in re.findall(r'<select name="(requirement__[A-Z0-9_]+)"[^>]*>(.*?)</select>', form, re.S)
    }
    values["config_version"] = re.search(r'name="config_version" value="([0-9a-f]+)"', form).group(1)
    return values


def save_levels(client, changes: dict[str, str], form: dict[str, str] | None = None):
    data = {**(form or levels_form(client.get(URL).text)), **changes, "csrf_token": csrf(client, URL)}
    return client.post(URL, data=data, follow_redirects=False)


def create_requirement(client, name: str, **fields: str):
    data = {"name": name, "description": "", **fields, "csrf_token": csrf(client, URL)}
    return client.post(f"{URL}/types", data=data, follow_redirects=False)


def restore_requirement(client, type_id: int):
    data = {"csrf_token": csrf(client, URL)}
    return client.post(f"{URL}/types/{type_id}/restore", data=data, follow_redirects=False)


@pytest.mark.parametrize("email", ["pmo@poc.local", MORAL])
def test_configuracion_sin_acceso_para_pmo_y_proveedor(client, email):
    login(client, email)
    before = config_snapshot()
    token = csrf(client, "/invoices")
    type_id = requirement_by(code="CONTRACT_ANNEXES").id
    assert client.get(URL).status_code == 403
    routes = (
        URL,
        f"{URL}/types",
        f"{URL}/types/{type_id}",
        f"{URL}/types/{type_id}/restore",
        f"{URL}/types/{type_id}/delete",
    )
    for route in routes:
        data = {"csrf_token": token, "name": "Intruso", "active": "false"}
        assert client.post(route, data=data, follow_redirects=False).status_code == 403
    assert config_snapshot() == before
    page = client.get("/").text
    assert "Requisitos mínimos" not in page and f'href="{URL}"' not in page


@pytest.mark.parametrize("token", [None, "invalido"])
def test_configuracion_sin_token_csrf(client, token):
    login(client)
    form = levels_form(client.get(URL).text)
    form["requirement__CONTRACT_PURCHASE_ORDER"] = "REQUIRED"
    if token:
        form["csrf_token"] = token
    before = config_snapshot()
    assert client.post(URL, data=form, follow_redirects=False).status_code == 403
    assert config_snapshot() == before


def test_menu_de_requisitos_minimos(client):
    login(client)
    menu = client.get("/").text.split('<div class="nav-label">Requisitos mínimos</div>')[1].split("</nav>")[0]
    assert re.findall(r'href="(/admin/[a-z-]+)" class="nav-item"><i class="[^"]+"></i> ([^<]+)</a>', menu) == [
        ("/admin/required-documents", "Archivos de factura"),
        ("/admin/supplier-requirements", "Alta de proveedor"),
        ("/admin/contract-requirements", "Alta de contrato"),
    ]


def test_hacer_obligatoria_la_orden_de_compra(client, new_contracts, restore_contract_requirements):
    contract = new_contracts()
    login(client)
    response = save_levels(client, {"requirement__CONTRACT_PURCHASE_ORDER": "REQUIRED"})
    assert response.status_code == 303
    assert "Configuración guardada" in client.get(response.headers["location"]).text
    page = contract_page(client, contract.id)
    assert requirement_rows(page)["Orden de compra"] == "Obligatorio · Pendiente"
    assert "Faltan 2 requisitos obligatorios" in page


def test_dejar_de_pedir_los_anexos(client, new_contracts, restore_contract_requirements):
    contract = new_contracts()
    login(client)
    assert save_levels(client, {"requirement__CONTRACT_ANNEXES": "NOT_APPLICABLE"}).status_code == 303
    page = contract_page(client, contract.id)
    assert "Anexos" not in requirement_rows(page) and 'value="CONTRACT_ANNEXES"' not in page


def test_contrato_con_nivel_editable(client, new_contracts, restore_contract_requirements):
    login(client)
    page = html.unescape(client.get(URL).text)
    row = page.split("<strong>Contrato</strong>")[1].split("</tr>")[0]
    assert "<select" in row and "bi-lock-fill" not in row
    assert save_levels(client, {"requirement__SIGNED_CONTRACT": "OPTIONAL"}).status_code == 303
    contract = new_contracts(codes=[])
    with SessionLocal() as db:
        assert requirements.pending_names(db, db.get(Contract, contract.id)) == []


def test_guardar_sin_cambios(client, restore_contract_requirements):
    login(client)
    before = config_snapshot()
    response = save_levels(client, {})
    assert response.status_code == 303
    assert "Sin cambios" in client.get(response.headers["location"]).text
    assert config_snapshot() == before


def test_nivel_invalido_y_nivel_faltante(client, restore_contract_requirements):
    login(client)
    before = config_snapshot()
    response = save_levels(
        client, {"requirement__CONTRACT_PURCHASE_ORDER": "REQUIRED", "requirement__CONTRACT_ANNEXES": "MANDATORY"}
    )
    assert response.status_code == 400 and "Nivel de exigencia inválido" in response.text
    form = levels_form(client.get(URL).text)
    del form["requirement__CONTRACT_ANNEXES"]
    assert save_levels(client, {"requirement__CONTRACT_PURCHASE_ORDER": "REQUIRED"}, form).status_code == 400
    assert config_snapshot() == before


def test_dos_administradores_editan_a_la_vez(client, restore_contract_requirements):
    login(client)
    stale = levels_form(client.get(URL).text)
    assert save_levels(client, {"requirement__CONTRACT_PURCHASE_ORDER": "REQUIRED"}).status_code == 303
    response = save_levels(client, {"requirement__CONTRACT_ANNEXES": "REQUIRED"}, stale)
    assert response.status_code == 409
    assert "La configuración cambió mientras la editaba. Recargue la página." in html.unescape(response.text)
    assert requirement_by(code="CONTRACT_PURCHASE_ORDER").requirement == "REQUIRED"
    assert requirement_by(code="CONTRACT_ANNEXES").requirement == "OPTIONAL"


def test_cambio_de_nivel_auditado(client, restore_contract_requirements):
    login(client)
    assert save_levels(client, {"requirement__CONTRACT_PURCHASE_ORDER": "REQUIRED"}).status_code == 303
    (entry,) = audit_entries("CONTRACT_REQUIREMENTS_UPDATED")[-1:]
    assert entry.user_id == admin_id()
    assert entry.old_value == {"CONTRACT_PURCHASE_ORDER": "OPTIONAL"}
    assert entry.new_value == {"CONTRACT_PURCHASE_ORDER": "REQUIRED"}


# --- Requisitos del contrato definidos por el Administrador -------------------------------------------------------

NDA = "Convenio de confidencialidad"


def test_alta_de_un_requisito(client, new_contracts, restore_contract_requirements):
    contract = new_contracts()
    login(client)
    response = create_requirement(client, NDA, requirement="REQUIRED")
    assert response.status_code == 303
    assert "Requisito creado" in client.get(response.headers["location"]).text
    created = requirement_by(name=NDA)
    assert created.code == f"REQ_CONTRATO_{created.id}" and created.is_active and not created.is_system
    assert created.allows_multiple is False
    assert NDA in client.get(URL).text
    assert requirement_rows(contract_page(client, contract.id))[NDA] == "Obligatorio · Pendiente"
    (entry,) = audit_entries("CONTRACT_DOCUMENT_TYPE_CREATED", created.id)
    assert entry.new_value == {
        "code": created.code,
        "name": NDA,
        "requirement": "REQUIRED",
        "allows_multiple": False,
    }


def test_alta_con_varios_archivos_y_formulario_en_no_aplica(client, restore_contract_requirements):
    login(client)
    page = client.get(URL).text
    options = re.search(r'<select id="new-requirement" name="requirement"[^>]*>(.*?)</select>', page, re.S).group(1)
    assert re.findall(r'<option value="([A-Z_]+)" selected>', options) == ["NOT_APPLICABLE"]
    checkbox = page.split('id="new-allows-multiple"')[1].split(">")[0]
    assert 'name="allows_multiple" value="true"' in checkbox and "checked" not in checkbox
    create_requirement(client, "Acta de inicio del proyecto", allows_multiple="true")
    created = requirement_by(name="Acta de inicio del proyecto")
    assert (created.requirement, created.allows_multiple) == ("NOT_APPLICABLE", True)


def test_requisito_con_nombre_repetido(client, restore_contract_requirements):
    login(client)
    before = config_snapshot()
    response = create_requirement(client, "  ORDEN de   compra ")
    assert response.status_code == 409 and "Ya existe un requisito con ese nombre" in response.text
    assert config_snapshot() == before


def test_eliminacion_logica_y_restauracion(client, new_contracts, restore_contract_requirements):
    login(client)
    create_requirement(client, NDA, requirement="REQUIRED")
    created = requirement_by(name=NDA)
    contract = new_contracts(codes=["SIGNED_CONTRACT", created.code])
    assert delete_requirement(client, created.id).headers["location"] == f"{URL}?ok=deleted"
    deleted = requirement_by(id=created.id)
    assert (deleted.is_active, deleted.deleted_at is not None, deleted.deleted_by) == (False, True, admin_id())
    listed = html.unescape(client.get(f"{URL}?eliminados=1").text).split("Requisitos eliminados")[1]
    assert NDA in listed and created.code in listed and "Restaurar" in listed
    page = contract_page(client, contract.id)
    assert NDA not in requirement_rows(page)
    others = page.split("Otros documentos del contrato")[1]
    assert NDA in others and f"/contracts/{contract.id}/documents/" in others
    with SessionLocal() as db:
        assert requirements.pending_names(db, db.get(Contract, contract.id)) == []
    assert restore_requirement(client, created.id).headers["location"] == f"{URL}?ok=restored"
    restored = requirement_by(id=created.id)
    assert restored.is_active and restored.requirement == "REQUIRED"
    assert len(audit_entries("CONTRACT_DOCUMENT_TYPE_DELETED", created.id)) == 1
    assert len(audit_entries("CONTRACT_DOCUMENT_TYPE_RESTORED", created.id)) == 1


def test_requisito_del_sistema_se_edita_y_se_elimina(client, new_contracts, restore_contract_requirements):
    login(client)
    annexes = requirement_by(code="CONTRACT_ANNEXES")
    data = {"name": "Anexos técnicos", "description": "", "csrf_token": csrf(client, URL)}
    assert client.post(f"{URL}/types/{annexes.id}", data=data, follow_redirects=False).status_code == 303
    assert (requirement_by(id=annexes.id).name, requirement_by(id=annexes.id).code) == (
        "Anexos técnicos",
        "CONTRACT_ANNEXES",
    )
    signed = requirement_by(code="SIGNED_CONTRACT")
    assert delete_requirement(client, signed.id).status_code == 303
    contract = new_contracts(codes=[])
    assert activate(client, contract.id).status_code == 303
    assert contract_status(contract.id) == "ACTIVE"


def test_edicion_de_un_requisito(client, restore_contract_requirements):
    login(client)
    create_requirement(client, NDA)
    created = requirement_by(name=NDA)
    data = {"name": "Convenio de confidencialidad firmado", "description": "Vigente", "csrf_token": csrf(client, URL)}
    response = client.post(f"{URL}/types/{created.id}", data=data, follow_redirects=False)
    assert response.status_code == 303
    edited = requirement_by(id=created.id)
    assert (edited.name, edited.description, edited.code) == (
        "Convenio de confidencialidad firmado",
        "Vigente",
        created.code,
    )
    (entry,) = audit_entries("CONTRACT_DOCUMENT_TYPE_UPDATED", created.id)
    assert entry.old_value == {"name": NDA, "description": None}


def test_operaciones_rechazadas_sin_auditoria(client, new_contracts, restore_contract_requirements):
    contract = new_contracts()
    login(client)
    before = config_snapshot()
    actions = ("CONTRACT_STATUS_CHANGED", "CONTRACT_DOCUMENT_UPLOADED")
    audited = [[entry.id for entry in audit_entries(action)] for action in actions]
    assert save_levels(client, {"requirement__CONTRACT_ANNEXES": "MANDATORY"}).status_code == 400
    assert create_requirement(client, "Anexos").status_code == 409
    assert activate(client, contract.id).status_code == 409
    assert upload(client, contract.id, "INCORPORATION_ACT").status_code == 400
    assert config_snapshot() == before
    assert [[entry.id for entry in audit_entries(action)] for action in actions] == audited


def test_datos_invalidos_y_operaciones_sin_cambios(client, restore_contract_requirements):
    login(client)
    response = create_requirement(client, "AB")
    assert response.status_code == 400 and requirement_by(name="AB") is None
    create_requirement(client, NDA)
    created = requirement_by(name=NDA)
    before = config_snapshot()
    data = {"name": "X", "description": "", "csrf_token": csrf(client, URL)}
    assert client.post(f"{URL}/types/{created.id}", data=data, follow_redirects=False).status_code == 400
    data = {"name": NDA, "description": "", "csrf_token": csrf(client, URL)}
    response = client.post(f"{URL}/types/{created.id}", data=data, follow_redirects=False)
    assert "Sin cambios" in client.get(response.headers["location"]).text
    response = restore_requirement(client, created.id)  # ya estaba activo
    assert "Sin cambios" in client.get(response.headers["location"]).text
    assert restore_requirement(client, 999999).status_code == 404
    assert config_snapshot() == before


# --- Editar y Eliminar requisitos del Administrador ------------------------------------------------------------------


def delete_requirement(client, type_id: int, token: str | None = "auto"):
    data = {"csrf_token": csrf(client, URL)} if token == "auto" else ({"csrf_token": token} if token else {})
    return client.post(f"{URL}/types/{type_id}/delete", data=data, follow_redirects=False)


def config_row(page: str, name: str) -> str:
    table = re.search(r"<h2>Configuración</h2>.*?</table>", page, re.S).group(0)
    return re.search(rf"<tr><td><strong>{re.escape(name)}</strong>.*?</tr>", table, re.S).group(0)


def test_acciones_editar_y_eliminar_en_todos_los_requisitos(client, restore_contract_requirements):
    login(client)
    create_requirement(client, NDA)
    created = requirement_by(name=NDA)
    page = html.unescape(client.get(URL).text)
    row = config_row(page, NDA)
    assert f'href="?editar={created.id}#editar-{created.id}"' in row and f'form="eliminar-{created.id}"' in row
    assert f"¿Eliminar «{NDA}»?" in row
    annexes = requirement_by(code="CONTRACT_ANNEXES")
    system = config_row(page, "Anexos")
    assert f'href="?editar={annexes.id}#editar-{annexes.id}"' in system and "Eliminar" in system
    opened = client.get(f"{URL}?editar={created.id}").text
    assert f'id="editar-{created.id}" class="admin-create border-bottom" open' in opened


def test_eliminacion_de_un_requisito_con_documentos(client, new_contracts, restore_contract_requirements):
    contract = new_contracts()
    login(client)
    create_requirement(client, NDA, requirement="REQUIRED")
    created = requirement_by(name=NDA)
    assert upload(client, contract.id, created.code).status_code == 303
    assert delete_requirement(client, created.id).status_code == 303
    assert requirement_by(id=created.id).is_active is False
    (entry,) = audit_entries("CONTRACT_DOCUMENT_TYPE_DELETED", created.id)
    assert (entry.user_id, entry.old_value, entry.new_value) == (admin_id(), {"is_active": True}, {"is_active": False})
    assert NDA in contract_page(client, contract.id).split("Otros documentos del contrato")[1]


def test_eliminacion_de_un_requisito_inexistente_o_sin_csrf(client, restore_contract_requirements):
    login(client)
    assert delete_requirement(client, 999_999).status_code == 404
    create_requirement(client, NDA)
    created = requirement_by(name=NDA)
    before = config_snapshot()
    assert delete_requirement(client, created.id, None).status_code == 403
    assert delete_requirement(client, created.id, "invalido").status_code == 403
    assert config_snapshot() == before
