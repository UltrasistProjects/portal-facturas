"""Registro y envio de la factura nacional (HU-12, HU-13; EP-01 DT-01 a DT-05)."""

import re
import secrets
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, update

from app.core.database import SessionLocal
from app.models import AuditLog, Contract, Invoice, Supplier, User, ValidationResult, ValidationRule
from tests.conftest import ROOT, csrf, invoice_by_number, login, supplier_by_email

DEMO = ROOT / "data" / "demo_documents"
CFDI = (DEMO / "cfdi_demo_correcto.xml").read_text(encoding="utf-8")
EXCEEDED = (DEMO / "cfdi_demo_monto_excedido.xml").read_text(encoding="utf-8")
PDF = (DEMO / "factura_demo.pdf").read_bytes()
SUPPORT = b"Documento soporte de prueba"
PROVIDER = "proveedor1@poc.local"
OTHER_PROVIDER = "proveedor2@poc.local"
PROJECT = "Automatizacion Operativa 2026"
LABELS = [
    "Borrador",
    "Cargada",
    "Enviada",
    "Autorizada",
    "Rechazada",
    "Observaciones",
    "Cancelada",
    "Pagada",
]  # Sin los pasos de ClickBalance, retirados con HU-20; Cancelada, de HU-14; Pagada, de la HU Complemento de Pagos


def unique(prefix: str = "HU12") -> str:
    return f"{prefix}-{secrets.token_hex(4).upper()}"


def new_uuid() -> str:
    return f"{secrets.token_hex(4)}-0000-4000-8000-{secrets.token_hex(6)}".upper()


def cfdi(uuid: str | None = None, source: str = CFDI, **attributes) -> bytes:
    """CFDI demo con un UUID nuevo y atributos del Receptor o del Comprobante cambiados."""
    xml = re.sub(r'UUID="[^"]*"', f'UUID="{uuid or new_uuid()}"', source)
    for name, value in attributes.items():
        xml = re.sub(rf'(<cfdi:(?:Receptor|Comprobante)[^>]*\b{name}=")[^"]*"', rf'\g<1>{value}"', xml)
    return xml.encode()


def own_contract_id(email: str = PROVIDER) -> int:
    supplier = supplier_by_email(email)
    with SessionLocal() as db:
        return db.scalar(select(Contract.id).where(Contract.supplier_id == supplier.id).order_by(Contract.id))


def token(client) -> str:
    # Toda pagina autenticada lleva el token en el formulario de cierre de sesion.
    return csrf(client, "/invoices")


def create(client, number: str | None = None, **overrides):
    number = number or unique()
    data = {
        "contract_id": own_contract_id(),
        "invoice_number": number,
        "service_period": "08/2026",
        "project_name": PROJECT,
        "csrf_token": token(client),
        **overrides,
    }
    return client.post("/invoices/new", data=data, follow_redirects=False), number


def create_invoice(client) -> Invoice:
    response, number = create(client)
    assert response.status_code == 303, response.text
    return invoice_by_number(number)


def upload(client, invoice: Invoice, document_type: str, filename: str, content: bytes):
    return client.post(
        f"/invoices/{invoice.id}/documents",
        data={"document_type": document_type, "csrf_token": token(client)},
        files={"upload": (filename, content, "application/octet-stream")},
        follow_redirects=False,
    )


def load(client, invoice: Invoice, xml: bytes, vobo: bool = True) -> Invoice:
    documents = [("INVOICE_XML", "cfdi.xml", xml), ("INVOICE_PDF", "factura.pdf", PDF)]
    documents.append(("PURCHASE_ORDER", "orden.txt", SUPPORT))
    if vobo:
        documents.append(("APPROVAL", "vobo.txt", SUPPORT))
    for document_type, filename, content in documents:
        assert upload(client, invoice, document_type, filename, content).status_code == 303
    return reload(invoice)


def uploaded_invoice(client, xml: bytes | None = None) -> Invoice:
    return load(client, create_invoice(client), xml or cfdi())


def submit(client, invoice: Invoice):
    return client.post(f"/invoices/{invoice.id}/submit", data={"csrf_token": token(client)}, follow_redirects=False)


def verify(client, invoice: Invoice):
    return client.post(f"/invoices/{invoice.id}/validation", data={"csrf_token": token(client)}, follow_redirects=False)


def reload(invoice: Invoice) -> Invoice:
    with SessionLocal() as db:
        return db.get(Invoice, invoice.id)


def results(invoice: Invoice) -> dict[str, ValidationResult]:
    with SessionLocal() as db:
        rows = db.scalars(select(ValidationResult).where(ValidationResult.invoice_id == invoice.id))
        return {row.rule_code: row for row in rows}


def audits(invoice: Invoice, action: str) -> list[AuditLog]:
    with SessionLocal() as db:
        stmt = select(AuditLog).where(AuditLog.entity == "Invoice", AuditLog.entity_id == str(invoice.id))
        return list(db.scalars(stmt.where(AuditLog.action == action).order_by(AuditLog.id)))


def received_on(invoice: Invoice, day: int) -> None:
    """Fecha de recepcion fija: DAT-001 no depende del dia en que corren las pruebas."""
    with SessionLocal() as db:
        received = datetime(2026, 8, day, 18, 0, tzinfo=timezone.utc)
        db.execute(update(Invoice).where(Invoice.id == invoice.id).values(created_at=received))
        db.commit()


@pytest.fixture()
def provider(client):
    login(client, PROVIDER)
    return client


# --- Registro: "Borrador" y "Cargada" -------------------------------------------------------------------------------


def test_alta_en_borrador_lleva_a_la_carga_documental(provider):
    response, number = create(provider)
    invoice = invoice_by_number(number)
    assert response.status_code == 303
    assert response.headers["location"] == f"/invoices/{invoice.id}/documents"
    assert invoice.status == "DRAFT"


def test_borrador_pasa_a_cargada_al_completar_los_obligatorios(provider):
    invoice = load(provider, create_invoice(provider), cfdi(), vobo=False)
    assert invoice.status == "DRAFT"
    page = provider.get(f"/invoices/{invoice.id}/documents").text
    assert "Falta 1 archivo obligatorio" in page
    assert "Factura cargada" not in page
    assert upload(provider, invoice, "APPROVAL", "vobo.txt", SUPPORT).status_code == 303
    assert reload(invoice).status == "UPLOADED"
    changes = [(a.old_value, a.new_value) for a in audits(invoice, "STATUS_CHANGED")]
    assert changes == [({"status": "DRAFT"}, {"status": "UPLOADED"})]
    assert "Factura cargada. Ya puede enviarla a validación" in provider.get(f"/invoices/{invoice.id}/documents").text


def test_reemplazo_en_cargada(provider):
    invoice = uploaded_invoice(provider)
    assert upload(provider, invoice, "INVOICE_XML", "cfdi2.xml", cfdi()).status_code == 303
    assert reload(invoice).status == "UPLOADED"


def test_etiquetas_del_filtro_de_estatus(provider):
    options = re.findall(r'<option value="[A-Z_]+"[^>]*>([^<]+)</option>', provider.get("/invoices").text)
    assert options == LABELS


# --- Envio ------------------------------------------------------------------------------------------------------------


def test_envio_exitoso_con_advertencias(provider):
    invoice = uploaded_invoice(provider)
    # Recibida despues del dia 20: DAT-001 es WARNING y no impide el envio.
    received_on(invoice, 25)
    response = submit(provider, invoice)
    assert response.status_code == 303
    assert response.headers["location"] == f"/invoices/{invoice.id}?notice=submitted"
    sent = reload(invoice)
    assert sent.status == "UNDER_REVIEW" and sent.submitted_at is not None
    stored = results(invoice)
    assert stored["DAT-001"].status == "WARNING"
    assert not [code for code, r in stored.items() if r.status == "FAIL"]
    assert len(audits(invoice, "INVOICE_SUBMITTED")) == 1
    page = provider.get(response.headers["location"]).text
    assert "Factura enviada a validación" in page and "Enviada" in page
    # Ya no admite cambios de documentos.
    assert upload(provider, invoice, "INVOICE_PDF", "otra.pdf", PDF).status_code == 409


@pytest.mark.parametrize(
    ("attributes", "code", "expected", "detected"),
    [
        ({"DomicilioFiscalReceptor": "06600"}, "XML-010", "03930", "06600"),
        ({"Rfc": "XAXX010101000"}, "XML-002", "ULT940623AG0", "XAXX010101000"),
    ],
)
def test_envio_que_no_procede(provider, attributes, code, expected, detected):
    invoice = uploaded_invoice(provider, cfdi(**attributes))
    response = submit(provider, invoice)
    assert response.status_code == 409
    assert "El envío no procedió" in response.text and "Reglas que impiden el envío" in response.text
    assert code in response.text and expected in response.text and detected in response.text
    assert reload(invoice).status == "UPLOADED"
    assert results(invoice)[code].status == "FAIL"
    assert not audits(invoice, "INVOICE_SUBMITTED")


@pytest.mark.usefixtures("restore_validation_rules")
def test_el_envio_usa_las_reglas_vigentes(provider):
    invoice = uploaded_invoice(provider)
    assert verify(provider, invoice).status_code == 303
    assert results(invoice)["XML-004"].status == "PASS"
    with SessionLocal() as db:
        db.execute(update(ValidationRule).where(ValidationRule.rule_code == "XML-004").values(parameter="03"))
        db.commit()
    assert submit(provider, invoice).status_code == 409
    rule = results(invoice)["XML-004"]
    assert (rule.status, rule.expected_value) == ("FAIL", "03")
    assert reload(invoice).status == "UPLOADED"


def test_envio_desde_borrador(provider):
    invoice = load(provider, create_invoice(provider), cfdi(), vobo=False)
    response = submit(provider, invoice)
    assert response.status_code == 409
    assert "Faltan archivos obligatorios: Vo.Bo. del líder de proyecto. Cárguelos antes de enviar" in response.text
    assert reload(invoice).status == "DRAFT"
    assert results(invoice) == {}
    assert not audits(invoice, "VALIDATION_STARTED")


def test_envio_de_una_factura_enviada(provider):
    invoice = invoice_by_number("REVISION-001")
    before = len(audits(invoice, "VALIDATION_STARTED"))
    response = submit(provider, invoice)
    assert response.status_code == 409
    assert "La factura no puede enviarse en su estatus actual" in response.text
    assert reload(invoice).status == "UNDER_REVIEW"
    assert len(audits(invoice, "VALIDATION_STARTED")) == before


def pmo_decides(client, invoice: Invoice, decision: str) -> None:
    login(client, "pmo@poc.local")
    data = {"decision": decision, "comments": "Corrija el PDF", "csrf_token": token(client)}
    assert client.post(f"/invoices/{invoice.id}/review", data=data, follow_redirects=False).status_code == 303
    login(client, PROVIDER)


def test_observaciones_se_corrigen_y_se_reenvian(provider):
    invoice = uploaded_invoice(provider)
    assert submit(provider, invoice).status_code == 303
    pmo_decides(provider, invoice, "REQUIRES_CORRECTION")
    assert reload(invoice).status == "REQUIRES_CORRECTION"
    assert "Observaciones" in provider.get(f"/invoices/{invoice.id}").text
    # La carga no recalcula "Observaciones".
    assert upload(provider, invoice, "INVOICE_PDF", "corregida.pdf", PDF).status_code == 303
    assert reload(invoice).status == "REQUIRES_CORRECTION"
    assert submit(provider, invoice).status_code == 303
    assert reload(invoice).status == "UNDER_REVIEW"
    assert len(audits(invoice, "INVOICE_SUBMITTED")) == 2


# --- Duplicados (RN-HU13-01) ------------------------------------------------------------------------------------------


def test_uuid_de_otro_proveedor_no_revela_sus_datos(provider):
    taken = new_uuid()
    other = supplier_by_email(OTHER_PROVIDER)
    number = unique("AJENA")
    with SessionLocal() as db:
        foreign = Invoice(
            internal_folio=f"FAC-AJENA-{secrets.token_hex(3)}",
            supplier_id=other.id,
            uploaded_by=db.scalar(select(User.id).where(User.email == OTHER_PROVIDER)),
            contract_id=own_contract_id(OTHER_PROVIDER),
            invoice_number=number,
            uuid=taken,
            service_period="08/2026",
            project_name="Servicios de Analitica 2026",
            status="UNDER_REVIEW",
        )
        db.add(foreign)
        db.commit()
        folio = foreign.internal_folio
    invoice = uploaded_invoice(provider, cfdi(taken))
    response = submit(provider, invoice)
    assert response.status_code == 409
    assert results(invoice)["FIN-004"].status == "FAIL"
    assert reload(invoice).uuid is None
    for secret in (folio, number, other.business_name):
        assert secret not in response.text


def test_uuid_de_una_factura_rechazada(provider):
    rejected = invoice_by_number("C-RFC-ERROR")
    assert rejected.status == "REJECTED" and rejected.uuid
    invoice = uploaded_invoice(provider, cfdi(rejected.uuid))
    assert submit(provider, invoice).status_code == 409
    rule = results(invoice)["FIN-004"]
    assert (rule.status, rule.severity) == ("FAIL", "CRITICAL")


# --- Solo el proveedor registra y envia (DT-04) -----------------------------------------------------------------------


@pytest.mark.parametrize("email", ["pmo@poc.local", "admin@poc.local"])
def test_internos_sin_alta_carga_verificacion_ni_envio(client, email):
    invoice = invoice_by_number("A-CORRECTA")
    login(client, email)
    csrf_token = token(client)
    assert client.get("/invoices/new").status_code == 403
    data = {"contract_id": invoice.contract_id, "invoice_number": unique("INT"), "service_period": "08/2026"}
    response = client.post("/invoices/new", data={**data, "project_name": PROJECT, "csrf_token": csrf_token})
    assert response.status_code == 403
    assert invoice_by_number(data["invoice_number"]) is None
    assert client.get(f"/invoices/{invoice.id}/documents").status_code == 403
    response = client.post(
        f"/invoices/{invoice.id}/documents",
        data={"document_type": "INVOICE_PDF", "csrf_token": csrf_token},
        files={"upload": ("f.pdf", PDF, "application/pdf")},
    )
    assert response.status_code == 403
    for action in ("validation", "submit"):
        response = client.post(f"/invoices/{invoice.id}/{action}", data={"csrf_token": csrf_token})
        assert response.status_code == 403, action
    assert reload(invoice).status == "UPLOADED"


def test_detalle_del_pmo_sin_acciones_del_proveedor(client):
    login(client, "pmo@poc.local")
    page = client.get(f"/invoices/{invoice_by_number('A-CORRECTA').id}")
    assert page.status_code == 200
    for action in ("Verificar", "Gestionar documentos", "Enviar a validación", "Nueva factura"):
        assert action not in page.text


def test_envio_de_la_factura_de_otro_proveedor(client):
    login(client, OTHER_PROVIDER)
    invoice = invoice_by_number("A-CORRECTA")
    assert submit(client, invoice).status_code == 404
    assert reload(invoice).status == "UPLOADED"


# --- Contratos del proveedor (DT-05) ----------------------------------------------------------------------------------


def test_formulario_sin_contratos_de_otros_proveedores(provider):
    foreign = own_contract_id(OTHER_PROVIDER)
    page = provider.get("/invoices/new").text
    assert "Servicios de Analitica 2026" not in page
    assert f'<option value="{foreign}"' not in page
    assert "75,000.00" not in page
    assert f'<option value="{own_contract_id()}"' in page
    assert 'name="supplier_id"' not in page


def test_supplier_id_manipulado_se_ignora(provider):
    other = supplier_by_email(OTHER_PROVIDER)
    response, number = create(provider, supplier_id=other.id)
    assert response.status_code == 303
    assert invoice_by_number(number).supplier_id == supplier_by_email(PROVIDER).id


def test_contrato_de_otro_proveedor(provider):
    response, number = create(provider, contract_id=own_contract_id(OTHER_PROVIDER))
    assert response.status_code == 400
    assert "Contrato no corresponde al proveedor" in response.text
    assert invoice_by_number(number) is None


@pytest.fixture()
def inactive_contract():
    supplier = supplier_by_email(PROVIDER)
    with SessionLocal() as db:
        contract = Contract(
            supplier_id=supplier.id,
            project_name="Proyecto concluido",
            project_leader="Lider",
            authorized_technology="N/A",
            authorized_amount=Decimal("1000.00"),
            currency="MXN",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            status="INACTIVE",
        )
        db.add(contract)
        db.commit()
        contract_id = contract.id
    yield contract_id
    with SessionLocal() as db:
        db.execute(delete(Contract).where(Contract.id == contract_id))
        db.commit()


def test_contrato_inactivo(provider, inactive_contract):
    assert "Proyecto concluido" not in provider.get("/invoices/new").text
    response, number = create(provider, contract_id=inactive_contract)
    assert response.status_code == 400
    assert "El contrato no está activo" in response.text
    assert invoice_by_number(number) is None


@pytest.fixture()
def inactive_supplier():
    supplier = supplier_by_email(OTHER_PROVIDER)
    with SessionLocal() as db:
        db.execute(update(Supplier).where(Supplier.id == supplier.id).values(status="INACTIVE"))
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(update(Supplier).where(Supplier.id == supplier.id).values(status="ACTIVE"))
        db.commit()


@pytest.mark.usefixtures("inactive_supplier")
def test_proveedor_inactivo_no_registra(client):
    login(client, OTHER_PROVIDER)
    page = client.get("/invoices/new")
    assert page.status_code == 409
    assert "Su proveedor no está autorizado para registrar facturas" in page.text
    number = unique("INACTIVO")
    data = {"contract_id": own_contract_id(OTHER_PROVIDER), "invoice_number": number, "service_period": "08/2026"}
    response = client.post("/invoices/new", data={**data, "project_name": PROJECT, "csrf_token": token(client)})
    assert response.status_code == 409
    assert invoice_by_number(number) is None


# --- Verificar --------------------------------------------------------------------------------------------------------


def test_verificar_no_cambia_el_estatus(provider):
    invoice = uploaded_invoice(provider, cfdi(source=EXCEEDED))
    response = verify(provider, invoice)
    assert response.status_code == 303
    assert reload(invoice).status == "UPLOADED"
    assert results(invoice)["FIN-001"].status == "FAIL"
    page = provider.get(f"/invoices/{invoice.id}").text
    blocking = page.split('id="blocking"')[1].split("</section>")[0]
    assert "FIN-001" in blocking


def test_verificar_una_factura_enviada(provider):
    invoice = invoice_by_number("REVISION-001")
    before = {code: r.id for code, r in results(invoice).items()}
    assert verify(provider, invoice).status_code == 409
    assert {code: r.id for code, r in results(invoice).items()} == before


# --- Archivos obligatorios en la transicion a "Enviada" (ajustes-finales-configuracion) ---------------------------


def test_envio_por_peticion_directa_con_varios_faltantes(provider):
    invoice = create_invoice(provider)
    assert upload(provider, invoice, "INVOICE_XML", "cfdi.xml", cfdi()).status_code == 303
    response = submit(provider, invoice)
    assert response.status_code == 409
    assert (
        "Faltan archivos obligatorios: PDF del CFDI, Orden de compra, Vo.Bo. del líder de proyecto. "
        "Cárguelos antes de enviar"
    ) in response.text


def test_transicion_directa_sin_archivos_obligatorios(provider):
    """La regla vive en el servicio de transicion: ni una llamada directa envia sin los obligatorios (409)."""
    from app.core.constants import InvoiceStatus
    from app.core.errors import BusinessRuleError
    from app.services.invoice_service import transition_invoice

    invoice = load(provider, create_invoice(provider), cfdi(), vobo=False)
    with SessionLocal() as db:
        db.execute(update(Invoice).where(Invoice.id == invoice.id).values(status="REQUIRES_CORRECTION"))
        db.commit()
        stored = db.get(Invoice, invoice.id)
        with pytest.raises(BusinessRuleError) as error:
            transition_invoice(db, stored, InvoiceStatus.UNDER_REVIEW)
        db.rollback()
    assert error.value.status_code == 409
    assert (
        error.value.message == "Faltan archivos obligatorios: Vo.Bo. del líder de proyecto. Cárguelos antes de enviar"
    )
    assert reload(invoice).status == "REQUIRES_CORRECTION"


@pytest.fixture()
def approval_deleted():
    from app.models import InvoiceDocumentType, now_utc

    approval = InvoiceDocumentType.code == "APPROVAL"
    with SessionLocal() as db:
        db.execute(update(InvoiceDocumentType).where(approval).values(is_active=False, deleted_at=now_utc()))
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(update(InvoiceDocumentType).where(approval).values(is_active=True, deleted_at=None, deleted_by=None))
        db.commit()


def test_tipo_eliminado_deja_de_exigirse_al_enviar(provider, approval_deleted):
    invoice = load(provider, create_invoice(provider), cfdi(), vobo=False)
    assert reload(invoice).status == "UPLOADED"
    assert submit(provider, invoice).status_code == 303
    assert reload(invoice).status == "UNDER_REVIEW"


def test_requisito_nuevo_no_afecta_a_una_factura_enviada(provider):
    from app.models import InvoiceDocumentType

    invoice = uploaded_invoice(provider)
    assert submit(provider, invoice).status_code == 303
    contract = InvoiceDocumentType.code == "CONTRACT"
    with SessionLocal() as db:
        db.execute(update(InvoiceDocumentType).where(contract).values(national_requirement="REQUIRED"))
        db.commit()
    try:
        assert reload(invoice).status == "UNDER_REVIEW"
        pmo_decides(provider, invoice, "ACCEPTED")
        assert reload(invoice).status == "ACCEPTED"
    finally:
        with SessionLocal() as db:
            db.execute(update(InvoiceDocumentType).where(contract).values(national_requirement="OPTIONAL"))
            db.commit()
