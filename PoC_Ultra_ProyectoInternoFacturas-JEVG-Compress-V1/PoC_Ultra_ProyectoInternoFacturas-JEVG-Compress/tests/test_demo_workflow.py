import pytest
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
        "/purchase-orders",
        "/admin/users",
        "/admin/rules",
        "/admin/audit",
    )
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        assert "Portal de Facturas" in response.text


def rule_status(db, invoice_id: int, code: str) -> str:
    return db.scalar(
        select(ValidationResult.status).where(
            ValidationResult.invoice_id == invoice_id, ValidationResult.rule_code == code
        )
    )


def test_seed_contiene_caso_pass_fail_y_audit():
    """A-CORRECTA cuadra con su orden de compra; B-EXCEDE factura mas que su orden (HU-24)."""
    with SessionLocal() as db:
        correct = db.scalar(select(Invoice).where(Invoice.invoice_number == "A-CORRECTA"))
        exceeded = db.scalar(select(Invoice).where(Invoice.invoice_number == "B-EXCEDE"))
        assert [rule_status(db, correct.id, code) for code in ("OC-001", "OC-002", "OC-005", "OC-009")] == ["PASS"] * 4
        assert [rule_status(db, exceeded.id, code) for code in ("OC-005", "OC-006", "OC-009")] == ["FAIL"] * 3
        failures = db.scalars(
            select(ValidationResult.rule_code).where(
                ValidationResult.invoice_id == correct.id, ValidationResult.status == "FAIL"
            )
        ).all()
        assert failures == []
        assert db.scalar(select(AuditLog.id).limit(1)) is not None


def test_seed_con_el_modelo_de_estatus_del_ers():
    expected = {
        "BORRADOR-001": "DRAFT",
        "A-CORRECTA": "UPLOADED",
        "B-EXCEDE": "UPLOADED",
        "E-SEMANTICO": "UPLOADED",
        "D-SIN-VOBO": "DRAFT",
        "REVISION-001": "UNDER_REVIEW",
        "ACEPTADA-001": "ACCEPTED",
        "C-RFC-ERROR": "REJECTED",
        # HU-20: los escenarios de ClickBalance se reemplazaron por una devuelta y una segunda por decidir.
        "OBSERVACIONES-001": "REQUIRES_CORRECTION",
        "ENVIADA-002": "UNDER_REVIEW",
    }
    for number, status in expected.items():
        invoice = invoice_by_number(number)
        assert invoice.status == status, number
        # Solo las facturas enviadas o posteriores tienen fecha de envio.
        assert (invoice.submitted_at is not None) == (status not in {"DRAFT", "UPLOADED"}), number


def test_ai_mock_sin_red_ni_datos_inventados(tmp_path):
    from app.services.ai import AnalyzerUnavailable

    analyzer = LocalMockAnalyzer()
    assert analyzer.health_check()["external_calls"] is False
    with pytest.raises(AnalyzerUnavailable):
        analyzer.extract_invoice(tmp_path / "escaneado.pdf")
