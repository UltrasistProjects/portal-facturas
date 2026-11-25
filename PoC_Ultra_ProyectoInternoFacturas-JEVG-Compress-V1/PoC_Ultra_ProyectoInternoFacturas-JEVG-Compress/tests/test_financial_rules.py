from decimal import Decimal
from types import SimpleNamespace

from app.rules.financial_rules import financial_rules


def test_reglas_financieras_y_duplicado_uuid():
    invoice = SimpleNamespace(
        subtotal=Decimal("100"), tax=Decimal("16"), total=Decimal("116"), currency="MXN", uuid="U", invoice_number="F"
    )
    results = {x.rule_code: x for x in financial_rules(invoice, None, True, False)}
    assert results["FIN-002"].status == "PASS"
    assert results["FIN-004"].status == "FAIL"
    assert results["FIN-005"].status == "PASS"


def test_uuid_detectado_en_el_comprobante():
    invoice = SimpleNamespace(
        subtotal=Decimal("0"), tax=Decimal("0"), total=Decimal("0"), uuid=None, invoice_number="F"
    )
    data = {"subtotal": "100.00", "tax": "16.00", "total": "116.00", "uuid": "AAAA"}
    fin_004 = next(x for x in financial_rules(invoice, data, True, False) if x.rule_code == "FIN-004")
    assert (fin_004.status, fin_004.detected_value) == ("FAIL", "AAAA")
