import re
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select

from app.core.config import settings
from app.core.constants import InvoiceStatus
from app.core.database import SessionLocal
from app.models import Document, Invoice, ValidationResult
from app.rules.date_rules import date_rules
from app.rules.financial_rules import financial_rules
from app.services.validation_engine import run_validation
from tests.conftest import ROOT, csrf, invoice_by_number, login, supplier_by_email

CFDI = (ROOT / "data" / "demo_documents" / "cfdi_demo_correcto.xml").read_text(encoding="utf-8")
PDF = (ROOT / "data" / "demo_documents" / "factura_demo.pdf").read_bytes()


def dat_001(created_at):
    return date_rules(SimpleNamespace(created_at=created_at))[0]


# --- DAT-001 en la zona horaria de negocio ---------------------------------------------------------------


def test_ultimo_minuto_del_dia_20():
    # 20 de agosto 23:00 en Ciudad de Mexico = 21 de agosto 05:00 UTC
    result = dat_001(datetime(2026, 8, 21, 5, 0, tzinfo=timezone.utc))
    assert result.status == "PASS"
    assert result.detected_value == "20"


def test_primer_minuto_del_dia_21():
    # 21 de agosto 00:30 en Ciudad de Mexico = 21 de agosto 06:30 UTC
    result = dat_001(datetime(2026, 8, 21, 6, 30, tzinfo=timezone.utc))
    assert result.status == "WARNING"
    assert "siguiente ciclo" in result.message


def test_zona_configurable(monkeypatch):
    monkeypatch.setattr(settings, "business_timezone", "UTC")
    assert dat_001(datetime(2026, 8, 21, 5, 0, tzinfo=timezone.utc)).status == "WARNING"


# --- UUID duplicado --------------------------------------------------------------------------------------


def create_invoice_with_xml(client, number: str, uuid: str) -> Invoice:
    supplier = supplier_by_email("proveedor1@poc.local")
    contract_id = invoice_by_number("A-CORRECTA").contract_id
    data = {
        "supplier_id": supplier.id,
        "contract_id": contract_id,
        "invoice_number": number,
        "service_period": "08/2026",
        "project_name": "Automatizacion Operativa 2026",
        "csrf_token": csrf(client, "/invoices/new"),
    }
    assert client.post("/invoices/new", data=data, follow_redirects=False).status_code == 303
    invoice = invoice_by_number(number)
    xml = re.sub(r'UUID="[^"]*"', f'UUID="{uuid}"', CFDI).encode()
    for document_type, filename, content in (("INVOICE_XML", "cfdi.xml", xml), ("INVOICE_PDF", "factura.pdf", PDF)):
        response = client.post(
            f"/invoices/{invoice.id}/documents",
            data={"document_type": document_type, "csrf_token": csrf(client, f"/invoices/{invoice.id}")},
            files={"upload": (filename, content, "application/octet-stream")},
            follow_redirects=False,
        )
        assert response.status_code == 303
    return invoice


def validate(client, invoice):
    token = csrf(client, f"/invoices/{invoice.id}")
    return client.post(f"/invoices/{invoice.id}/validation", data={"csrf_token": token}, follow_redirects=False)


def rule(invoice_id: int, code: str) -> ValidationResult | None:
    with SessionLocal() as db:
        return db.scalar(
            select(ValidationResult).where(
                ValidationResult.invoice_id == invoice_id, ValidationResult.rule_code == code
            )
        )


def test_cfdi_ya_registrado_en_otra_factura(client):
    taken = invoice_by_number("A-CORRECTA").uuid
    login(client, "proveedor1@poc.local")
    invoice = create_invoice_with_xml(client, "DUP-UUID-1", taken)
    assert validate(client, invoice).status_code == 303
    fin_004 = rule(invoice.id, "FIN-004")
    assert (fin_004.status, fin_004.severity, fin_004.detected_value) == ("FAIL", "CRITICAL", taken)
    with SessionLocal() as db:
        stored = db.get(Invoice, invoice.id)
        xml_doc = db.scalar(
            select(Document).where(Document.invoice_id == invoice.id, Document.document_type == "INVOICE_XML")
        )
        assert stored.status == InvoiceStatus.DRAFT
        assert stored.uuid is None
        assert xml_doc.metadata_json["uuid"] == taken


def test_carrera_de_uuid_responde_409_sin_persistir(client, monkeypatch):
    import app.services.validation_engine as engine_module

    taken = invoice_by_number("A-CORRECTA").uuid
    login(client, "proveedor1@poc.local")
    invoice = create_invoice_with_xml(client, "DUP-UUID-2", taken)
    # Simula que la otra factura confirmo su UUID despues de la comprobacion previa.
    monkeypatch.setattr(engine_module, "uuid_owner", lambda *_args: None)
    response = validate(client, invoice)
    assert response.status_code == 409
    assert "El CFDI ya esta registrado en otra factura" in response.text
    with SessionLocal() as db:
        assert db.get(Invoice, invoice.id).status == InvoiceStatus.DRAFT
    assert rule(invoice.id, "FIN-004") is None


def test_revalidar_la_propia_factura():
    invoice = invoice_by_number("D-SIN-VOBO")
    with SessionLocal() as db:
        summary = run_validation(db, db.get(Invoice, invoice.id))
        fin_004 = next(r for r in summary["results"] if r.rule_code == "FIN-004")
        assert fin_004.status == "PASS"
        assert db.get(Invoice, invoice.id).uuid == invoice.uuid
        db.rollback()


def test_numero_de_factura_duplicado_responde_409(client):
    supplier = supplier_by_email("proveedor1@poc.local")
    login(client, "proveedor1@poc.local")
    data = {
        "supplier_id": supplier.id,
        "contract_id": invoice_by_number("A-CORRECTA").contract_id,
        "invoice_number": "A-CORRECTA",
        "service_period": "08/2026",
        "project_name": "Automatizacion Operativa 2026",
        "csrf_token": csrf(client, "/invoices/new"),
    }
    response = client.post("/invoices/new", data=data, follow_redirects=False)
    assert response.status_code == 409
    assert "Ya existe una factura con ese numero para el proveedor" in response.text


# --- Reglas financieras ----------------------------------------------------------------------------------


def financial(invoice=None, contract=None, xml=None, duplicate_uuid=False, duplicate_number=False):
    invoice = invoice or SimpleNamespace(
        subtotal=Decimal("100"), tax=Decimal("16"), total=Decimal("116"), currency="MXN", uuid="U", invoice_number="F"
    )
    contract = contract or SimpleNamespace(authorized_amount=Decimal("100"), currency="MXN")
    return {r.rule_code: r for r in financial_rules(invoice, contract, xml, duplicate_uuid, duplicate_number)}


def test_fin_002_consistencia_de_componentes():
    assert financial()["FIN-002"].status == "PASS"
    assert (
        financial(xml={"subtotal": Decimal("100"), "tax": Decimal("16"), "total": Decimal("116.02")})["FIN-002"].status
        == "PASS"
    )
    assert (
        financial(xml={"subtotal": Decimal("100"), "tax": Decimal("16"), "total": Decimal("116.03")})["FIN-002"].status
        == "FAIL"
    )


def test_fin_003_moneda_del_contrato():
    assert financial()["FIN-003"].status == "PASS"
    usd = SimpleNamespace(authorized_amount=Decimal("100"), currency="USD")
    assert financial(contract=usd)["FIN-003"].status == "FAIL"


def test_fin_005_numero_duplicado():
    assert financial()["FIN-005"].status == "PASS"
    assert financial(duplicate_number=True)["FIN-005"].status == "FAIL"


def test_fin_006_diferencia_contra_autorizado():
    ok = financial()["FIN-006"]
    assert ok.status == "PASS" and ok.evidence["absolute_difference"] == "0"
    over = financial(xml={"subtotal": Decimal("118"), "tax": Decimal("0"), "total": Decimal("118")})["FIN-006"]
    assert (over.status, over.severity) == ("FAIL", "WARNING")
    assert over.evidence == {"absolute_difference": "18", "percentage": "18.00"}
