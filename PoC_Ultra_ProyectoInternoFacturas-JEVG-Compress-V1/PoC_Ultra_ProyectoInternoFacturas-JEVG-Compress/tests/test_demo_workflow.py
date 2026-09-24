from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import AuditLog, Invoice, ValidationResult
from app.services.ai.mock_analyzer import LocalMockAnalyzer
from tests.conftest import invoice_by_number, login, supplier_by_email


def test_paginas_principales_renderizan(client):
    login(client)
    invoice = invoice_by_number("A-CORRECTA")
    supplier = supplier_by_email("proveedor1@poc.local")
    paths = (
        "/",
        "/invoices",
        f"/invoices/{invoice.id}",
        "/suppliers",
        f"/suppliers/{supplier.id}",
        "/contracts",
        "/admin/users",
        "/admin/rules",
        "/admin/audit",
    )
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        assert "Invoice Portal" in response.text


def test_seed_contiene_caso_pass_fail_y_audit():
    with SessionLocal() as db:
        correct = db.scalar(select(Invoice).where(Invoice.invoice_number == "A-CORRECTA"))
        exceeded = db.scalar(select(Invoice).where(Invoice.invoice_number == "B-EXCEDE"))
        assert (
            db.scalar(
                select(ValidationResult).where(
                    ValidationResult.invoice_id == correct.id, ValidationResult.rule_code == "FIN-001"
                )
            ).status
            == "PASS"
        )
        assert (
            db.scalar(
                select(ValidationResult).where(
                    ValidationResult.invoice_id == exceeded.id, ValidationResult.rule_code == "FIN-001"
                )
            ).status
            == "FAIL"
        )
        assert db.scalar(select(AuditLog.id).limit(1)) is not None


def test_ai_mock_semantico_sin_red():
    analyzer = LocalMockAnalyzer()
    result = analyzer.semantic_compare("Microsoft Power Platform", "08 Servicios desarrollo Power Automate")
    assert analyzer.health_check()["external_calls"] is False
    assert result["result"] == "MATCH"
    assert result["confidence"] == 0.93
