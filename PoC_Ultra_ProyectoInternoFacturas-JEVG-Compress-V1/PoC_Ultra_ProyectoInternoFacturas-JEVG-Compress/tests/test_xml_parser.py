from decimal import Decimal
from pathlib import Path
import pytest
from app.services.xml_service import XMLParseError, parse_cfdi

DEMO = Path(__file__).resolve().parents[1] / "data" / "demo_documents"


def test_parser_cfdi_40_extrae_campos():
    data = parse_cfdi(DEMO / "cfdi_demo_correcto.xml")
    assert data["version"] == "4.0"
    assert data["receiver_rfc"] == "ULT940623AG0"
    assert data["payment_method"] == "PPD"
    assert data["payment_form"] == "99"
    assert data["subtotal"] == Decimal("100000.00")
    assert data["concepts"][0]["description"].startswith("08")


def test_parser_detecta_rfc_incorrecto_y_xml_corrupto():
    assert parse_cfdi(DEMO / "cfdi_demo_rfc_incorrecto.xml")["receiver_rfc"] != "ULT940623AG0"
    with pytest.raises(XMLParseError): parse_cfdi(b"<broken")

