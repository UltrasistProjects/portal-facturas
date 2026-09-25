from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.constants import BUSINESS_RULES
from app.core.database import SessionLocal
from app.core.timeutils import to_business
from app.models import Contract, ValidationSettings
from app.rules.xml_rules import xml_rules
from app.services.invoice_service import internal_folio
from app.services.validation_settings_service import CHECK_FIELDS, LABELS, rule_parameters
from tests.conftest import csrf, invoice_by_number, login, supplier_by_email


def create_invoice(client, invoice_number: str):
    supplier = supplier_by_email("proveedor1@poc.local")
    with SessionLocal() as db:
        contract = db.scalar(select(Contract).where(Contract.supplier_id == supplier.id))
    data = {
        "supplier_id": supplier.id,
        "contract_id": contract.id,
        "invoice_number": invoice_number,
        "service_period": "09/2026",
        "project_name": contract.project_name,
        "csrf_token": csrf(client, "/invoices/new"),
    }
    return client.post("/invoices/new", data=data, follow_redirects=False)


def test_folio_derivado_del_id(client):
    login(client, "proveedor1@poc.local")
    assert create_invoice(client, "FOLIO-001").status_code == 303
    invoice = invoice_by_number("FOLIO-001")
    assert invoice.internal_folio == f"FAC-{to_business(invoice.created_at).year}-{invoice.id:05d}"


def test_ano_del_folio_en_zona_de_negocio():
    # 31 de diciembre 20:00 en Ciudad de Mexico = 1 de enero 02:00 UTC
    assert internal_folio(12, datetime(2027, 1, 1, 2, 0, tzinfo=timezone.utc)) == "FAC-2026-00012"
    assert internal_folio(12, datetime(2027, 1, 1, 7, 0, tzinfo=timezone.utc)) == "FAC-2027-00012"


def test_altas_concurrentes_con_folios_distintos():
    from app.main import app

    def worker(index: int) -> int:
        with TestClient(app) as client:
            login(client, "proveedor1@poc.local")
            return create_invoice(client, f"CONCURRENTE-{index}").status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(worker, range(4)))
    assert statuses == [303] * 4
    folios = {invoice_by_number(f"CONCURRENTE-{index}").internal_folio for index in range(4)}
    assert len(folios) == 4


def test_vista_de_reglas_muestra_los_pesos_del_score(client):
    login(client)
    page = client.get("/admin/rules").text
    for severity, weight in BUSINESS_RULES["score_weights"].items():
        assert f"<dt>{severity.value}</dt><dd>{weight}</dd>" in page
    with SessionLocal() as db:
        assert f'value="{rule_parameters(db).receiver_rfc}"' in page
    assert set(BUSINESS_RULES) == {"score_weights"}  # los demas parametros viven en Reglas de Validacion (HU-06)


def test_un_cambio_de_parametro_se_refleja_en_motor_y_vista(client, restore_validation_rules):
    login(client)
    data = {
        **{name: value for name, value in form_values().items() if name != "allowed_cfdi_uses"},
        "allowed_cfdi_uses": form_values()["allowed_cfdi_uses"],
        "payment_form": "03",
        "csrf_token": csrf(client, "/"),
    }
    assert client.post("/admin/rules", data=data, follow_redirects=False).status_code == 303
    assert '<option value="03" selected>' in client.get("/admin/rules").text
    with SessionLocal() as db:
        results = {
            r.rule_code: r for r in xml_rules({"payment_form": "03", "receiver_rfc": "X"}, None, rule_parameters(db))
        }
    assert results["XML-004"].status == "PASS"
    assert results["XML-004"].expected_value == "03"


def form_values() -> dict:
    with SessionLocal() as db:
        settings = db.get(ValidationSettings, 1)
        values = {name: getattr(settings, name) for name in LABELS} | {"version": settings.version}
        values |= {name: "on" for name in CHECK_FIELDS if getattr(settings, name)}
    return values
