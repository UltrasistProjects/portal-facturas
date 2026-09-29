import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.core.constants import InvoiceStatus
from app.core.database import SessionLocal, engine
from app.core.errors import BusinessRuleError
from app.models import AuditLog, Invoice, Review, User, ValidationResult
from app.services.invoice_service import ensure_can_accept, validation_summary
from tests.conftest import csrf, invoice_by_number, login, supplier_by_email

PAGINATED = 30


@pytest.fixture(scope="module")
def provider2_invoices():
    """30 facturas del proveedor 2 (sin facturas en el seed), con fechas y montos conocidos."""
    supplier = supplier_by_email("proveedor2@poc.local")
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(Invoice).where(Invoice.supplier_id == supplier.id)) == 0:
            uploader = db.scalar(select(User.id).where(User.email == "proveedor2@poc.local"))
            start = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
            for index in range(PAGINATED):
                db.add(
                    Invoice(
                        internal_folio=f"FAC-PAG-{index:05d}",
                        supplier_id=supplier.id,
                        uploaded_by=uploader,
                        invoice_number=f"PAG-{index:02d}",
                        service_period="07/2026",
                        project_name="Servicios de Analitica 2026",
                        subtotal=Decimal("0.10"),
                        tax=Decimal("0"),
                        total=Decimal("0.10"),
                        created_at=start + timedelta(hours=index),
                    )
                )
            db.commit()
    return [f"PAG-{index:02d}" for index in range(PAGINATED)]


def count_queries(action) -> int:
    statements = []

    def listener(*_args):
        statements.append(1)

    event.listen(engine, "before_cursor_execute", listener)
    try:
        action()
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return len(statements)


# --- Reglas de estado --------------------------------------------------------------------------------------


def test_aceptar_con_bloqueo_critico_desde_el_servicio():
    invoice = SimpleNamespace(validations=[SimpleNamespace(status="FAIL", severity="CRITICAL")])
    with pytest.raises(BusinessRuleError, match="bloqueos criticos"):
        ensure_can_accept(invoice)


def test_aceptar_con_bloqueo_critico_desde_http(client):
    invoice = invoice_by_number("B-EXCEDE")  # FIN-001 FAIL CRITICAL
    with SessionLocal() as db:
        db.get(Invoice, invoice.id).status = InvoiceStatus.UNDER_REVIEW
        db.commit()
        reviews = db.scalar(select(func.count()).select_from(Review).where(Review.invoice_id == invoice.id))
    try:
        login(client, "pmo@poc.local")
        token = csrf(client, f"/invoices/{invoice.id}")
        response = client.post(
            f"/invoices/{invoice.id}/review", data={"decision": "ACCEPTED", "comments": "", "csrf_token": token}
        )
        assert response.status_code == 409
        assert "No se puede aceptar con bloqueos criticos" in response.text
        with SessionLocal() as db:
            assert db.get(Invoice, invoice.id).status == InvoiceStatus.UNDER_REVIEW
            assert db.scalar(select(func.count()).select_from(Review).where(Review.invoice_id == invoice.id)) == reviews
    finally:
        with SessionLocal() as db:
            db.get(Invoice, invoice.id).status = InvoiceStatus.REQUIRES_CORRECTION
            db.commit()


def test_decision_invalida(client):
    invoice = invoice_by_number("REVISION-001")
    login(client, "pmo@poc.local")
    token = csrf(client, f"/invoices/{invoice.id}")
    response = client.post(f"/invoices/{invoice.id}/review", data={"decision": "QUIZAS", "csrf_token": token})
    assert response.status_code == 400


def test_resumen_del_detalle_usa_calculate_score(client):
    invoice = invoice_by_number("B-EXCEDE")
    with SessionLocal() as db:
        results = db.scalars(select(ValidationResult).where(ValidationResult.invoice_id == invoice.id)).all()
    summary = validation_summary(results)
    login(client)
    page = client.get(f"/invoices/{invoice.id}").text
    for key, label in (
        ("pass", "Correctas"),
        ("warnings", "Advertencias"),
        ("errors", "Errores"),
        ("blockers", "Criticos"),
    ):
        assert f"<strong>{summary[key]}</strong><span>{label}</span>" in page
    assert summary["blockers"] >= 1


# --- Listado ---------------------------------------------------------------------------------------------


def test_busqueda_por_razon_social(client):
    login(client, "pmo@poc.local")
    # status vacio = "Todos los estados": sin el, el PMO abre su bandeja de Enviadas (HU-18).
    page = client.get("/invoices", params={"q": "tecnologia INTEGRAL", "status": ""}).text
    # Cada fila es de ese proveedor (la primera celda del PMO es la razon social); otras pruebas agregan facturas
    # suyas, asi que una factura concreta del seed puede no estar en la primera pagina.
    suppliers = re.findall(r"<tr><td><strong>([^<]+)</strong>", page)
    assert suppliers and set(suppliers) == {"Tecnologia Integral del Centro SA de CV"}


def test_comodines_literales(client):
    login(client, "pmo@poc.local")
    assert "No hay facturas para mostrar" in client.get("/invoices", params={"q": "%"}).text
    assert "No hay facturas para mostrar" in client.get("/invoices", params={"q": "_"}).text


def test_estado_invalido_no_devuelve_resultados(client):
    login(client, "pmo@poc.local")
    assert "No hay facturas para mostrar" in client.get("/invoices", params={"status": "APROBADA"}).text


def test_paginacion(client, provider2_invoices):
    login(client, "proveedor2@poc.local")
    first = client.get("/invoices").text
    second = client.get("/invoices", params={"page": 2}).text
    assert "Pagina 2 de 2" in second and "30 registros" in second
    oldest = provider2_invoices[:5]
    for number in oldest:
        assert f"<small>{number}</small>" in second
        assert f"<small>{number}</small>" not in first
    assert second.count('class="icon-action"') == 5
    assert first.count('class="icon-action"') == 25
    assert "Pagina 2 de 2" in client.get("/invoices", params={"page": 99}).text


def test_sin_n_mas_uno(client, provider2_invoices):
    login(client, "proveedor2@poc.local")
    full_page = count_queries(lambda: client.get("/invoices"))
    single = count_queries(lambda: client.get("/invoices", params={"q": "PAG-07"}))
    assert full_page == single


def test_alcance_del_proveedor(client, provider2_invoices):
    login(client, "proveedor2@poc.local")
    page = client.get("/invoices", params={"q": "A-CORRECTA"}).text
    assert "No hay facturas para mostrar" in page


def test_kpis_del_proveedor(client, provider2_invoices):
    login(client, "proveedor2@poc.local")
    page = client.get("/").text
    assert "<strong>30</strong><small>Expedientes visibles</small>" in page.replace("\n", "")
    assert "$3.00 acumulado" in page  # 30 x 0.10 exacto


# --- Transacciones y auditoria ---------------------------------------------------------------------------


def test_fallo_despues_de_validar_no_persiste_nada(monkeypatch):
    import app.routers.invoices as invoices_router
    from app.main import app

    invoice = invoice_by_number("D-SIN-VOBO")
    original_run = invoices_router.run_validation

    def run_then_fail(*args, **kwargs):
        original_run(*args, **kwargs)
        raise RuntimeError("fallo posterior a la validacion")

    monkeypatch.setattr(invoices_router, "run_validation", run_then_fail)
    with SessionLocal() as db:
        before = db.scalars(
            select(ValidationResult.id).where(ValidationResult.invoice_id == invoice.id).order_by(ValidationResult.id)
        ).all()
    with TestClient(app, raise_server_exceptions=False) as client:
        login(client, "proveedor1@poc.local")
        token = csrf(client, f"/invoices/{invoice.id}")
        assert client.post(f"/invoices/{invoice.id}/validation", data={"csrf_token": token}).status_code == 500
    with SessionLocal() as db:
        assert db.get(Invoice, invoice.id).status == invoice.status
        after = db.scalars(
            select(ValidationResult.id).where(ValidationResult.invoice_id == invoice.id).order_by(ValidationResult.id)
        ).all()
    assert after == before


def test_registro_de_auditoria_paginado(client):
    with SessionLocal() as db:
        oldest = datetime(2020, 1, 1, tzinfo=timezone.utc)
        for index in range(600):
            db.add(
                AuditLog(
                    action="PAGINACION",
                    entity="Prueba",
                    entity_id=f"P{index:04d}",
                    timestamp=oldest + timedelta(minutes=index),
                )
            )
        db.commit()
        total = db.scalar(select(func.count()).select_from(AuditLog))
    last_page = -(-total // 50)
    login(client)
    first = client.get("/admin/audit").text
    last = client.get("/admin/audit", params={"page": last_page}).text
    assert f"Pagina 1 de {last_page}" in first
    assert "#P0000" in last and "#P0000" not in first
