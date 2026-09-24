from decimal import Decimal
from types import SimpleNamespace

from app.rules.financial_rules import financial_rules
from app.services.reconciliation_service import reconcile_amount


def test_monto_dentro_y_excedido():
    assert reconcile_amount(Decimal("100000"), Decimal("100000")).result == "PASS"
    exceeded = reconcile_amount(Decimal("100000"), Decimal("118000"))
    assert exceeded.result == "FAIL"
    assert exceeded.difference == Decimal("18000")
    assert exceeded.percentage == Decimal("18.00")


def test_reglas_financieras_y_duplicado_uuid():
    invoice = SimpleNamespace(
        subtotal=Decimal("100"), tax=Decimal("16"), total=Decimal("116"), currency="MXN", uuid="U", invoice_number="F"
    )
    contract = SimpleNamespace(authorized_amount=Decimal("100"), currency="MXN")
    results = financial_rules(invoice, contract, None, True, False)
    assert next(x for x in results if x.rule_code == "FIN-001").status == "PASS"
    assert next(x for x in results if x.rule_code == "FIN-004").status == "FAIL"
