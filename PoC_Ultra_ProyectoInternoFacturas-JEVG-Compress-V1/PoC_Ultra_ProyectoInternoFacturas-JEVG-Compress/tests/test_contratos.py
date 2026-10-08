from datetime import timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import AuditLog, Contract, ContractAmendment, User, ValidationResult
from app.rules.financial_rules import financial_rules
from app.services.contract_service import amend_authorized_amount
from tests.conftest import csrf, invoice_by_number, login, supplier_by_email


def user_id(email: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == email))


@pytest.fixture()
def contract(client):
    """Contrato propio de la prueba: enmendar los del seed alteraria las validaciones de otras pruebas."""
    supplier = supplier_by_email("proveedor2@poc.local")
    name = f"Trazable {uuid4().hex[:8]}"
    login(client)
    data = {
        "supplier_id": supplier.id,
        "project_name": name,
        "project_leader": "Lider",
        "authorized_technology": "Python",
        "authorized_amount": "100000.00",
        "currency": "MXN",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "csrf_token": csrf(client, "/contracts"),
    }
    assert client.post("/contracts", data=data, follow_redirects=False).status_code == 303
    with SessionLocal() as db:
        return db.scalar(select(Contract).where(Contract.project_name == name))


def amend(client, contract_id: int, amount: str, reason: str):
    token = csrf(client, "/contracts")
    return client.post(
        f"/contracts/{contract_id}/amendments", data={"new_amount": amount, "reason": reason, "csrf_token": token}
    )


def test_campos_de_auditoria_en_el_alta(contract):
    admin = user_id("admin@poc.local")
    assert contract.created_at.tzinfo == timezone.utc
    assert (contract.created_by, contract.updated_by) == (admin, admin)
    assert contract.updated_at == contract.created_at or contract.updated_at >= contract.created_at


def test_enmienda_valida(client, contract):
    response = amend(client, contract.id, "120000.00", "Ampliacion de alcance")
    assert response.status_code == 200
    with SessionLocal() as db:
        stored = db.get(Contract, contract.id)
        amendment = db.scalar(select(ContractAmendment).where(ContractAmendment.contract_id == contract.id))
        entry = db.scalar(
            select(AuditLog).where(AuditLog.action == "CONTRACT_AMOUNT_CHANGED", AuditLog.entity_id == str(contract.id))
        )
    assert stored.authorized_amount == Decimal("120000.00")
    assert stored.updated_by == user_id("admin@poc.local")
    assert (amendment.previous_amount, amendment.new_amount, amendment.reason) == (
        Decimal("100000.00"),
        Decimal("120000.00"),
        "Ampliacion de alcance",
    )
    assert amendment.created_by == user_id("admin@poc.local")
    assert entry.old_value == {"authorized_amount": "100000.00"}
    assert entry.new_value["authorized_amount"] == "120000.00"


@pytest.mark.parametrize("email", ["pmo@poc.local", "proveedor2@poc.local"])
def test_usuario_sin_permiso(client, contract, email):
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, email)
    token = csrf(client, "/")
    response = client.post(
        f"/contracts/{contract.id}/amendments", data={"new_amount": "1.00", "reason": "x" * 5, "csrf_token": token}
    )
    assert response.status_code == 403
    with SessionLocal() as db:
        assert db.get(Contract, contract.id).authorized_amount == Decimal("100000.00")


@pytest.mark.parametrize(
    ("amount", "reason", "message"), [("5000.00", "", "Motivo"), ("0", "Ajuste", "mayor que cero")]
)
def test_enmienda_invalida(client, contract, amount, reason, message):
    response = amend(client, contract.id, amount, reason)
    assert response.status_code == 400
    assert message in response.text
    with SessionLocal() as db:
        assert db.scalar(select(ContractAmendment).where(ContractAmendment.contract_id == contract.id)) is None


def test_historial_visible_para_internal(client, contract):
    amend(client, contract.id, "120000.00", "Ampliacion de alcance")
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, "pmo@poc.local")
    page = client.get("/contracts").text
    assert "Ampliacion de alcance" in page
    assert "$120,000.00" in page
    assert "Modificar monto" not in page  # el formulario es solo para Administrador


def test_fin_001_registra_el_monto_y_la_enmienda_vigentes(client, contract):
    amend(client, contract.id, "120000.00", "Ampliacion de alcance")
    with SessionLocal() as db:
        stored = db.get(Contract, contract.id)
        amendment_id = stored.amendments[-1].id
        invoice = SimpleNamespace(
            subtotal=Decimal("110000"),
            tax=Decimal("0"),
            total=Decimal("110000"),
            currency="MXN",
            uuid="U",
            invoice_number="N",
        )
        fin_001 = financial_rules(invoice, stored, None, False, False)[0]
    assert fin_001.status == "PASS"
    assert fin_001.evidence["authorized_amount"] == "120000.00"
    assert fin_001.evidence["amendment_id"] == amendment_id


def test_evidencia_historica_se_conserva():
    invoice = invoice_by_number("A-CORRECTA")
    with SessionLocal() as db:
        fin_001 = db.scalar(
            select(ValidationResult).where(
                ValidationResult.invoice_id == invoice.id, ValidationResult.rule_code == "FIN-001"
            )
        )
        assert fin_001.evidence_json["authorized_amount"] == "100000.00"
        assert fin_001.evidence_json["amendment_id"] is None
        amend_authorized_amount(
            db, db.get(Contract, invoice.contract_id), Decimal("150000.00"), "Prueba", invoice.uploaded_by
        )
        db.flush()
        db.refresh(fin_001)
        assert fin_001.evidence_json["authorized_amount"] == "100000.00"
        db.rollback()
