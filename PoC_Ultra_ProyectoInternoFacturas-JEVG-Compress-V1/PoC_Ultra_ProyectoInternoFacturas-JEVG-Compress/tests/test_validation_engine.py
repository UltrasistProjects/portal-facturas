from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from app.core.constants import InvoiceStatus
from app.rules.date_rules import date_rules
from app.schemas import ValidationOutcome
from app.services.invoice_service import transition_invoice
from app.services.validation_score_service import calculate_score


def result(status, severity):
    return ValidationOutcome(rule_code="T-1", category="SYS", status=status, severity=severity, message="test")


def test_regla_fecha_despues_del_20_es_warning():
    invoice = SimpleNamespace(created_at=datetime(2026, 8, 21, tzinfo=timezone.utc))
    check = date_rules(invoice)[0]
    assert check.status == "WARNING"
    assert "siguiente ciclo" in check.message


def test_score_explicable_y_bloqueo():
    summary = calculate_score([result("PASS", "CRITICAL"), result("FAIL", "ERROR"), result("WARNING", "WARNING")])
    assert 0 <= summary["score"] < 100
    assert summary["errors"] == 1 and summary["warnings"] == 1
    blocked = calculate_score([result("FAIL", "CRITICAL")])
    assert blocked["blockers"] == 1 and blocked["score"] == 0


def test_transicion_invalida_rechazada():
    class FakeDB:
        def add(self, value): pass
    invoice = SimpleNamespace(status=InvoiceStatus.DRAFT, id=1, submitted_at=None, reviewed_at=None, reviewed_by=None)
    with pytest.raises(ValueError): transition_invoice(FakeDB(), invoice, InvoiceStatus.ACCEPTED, 1)

