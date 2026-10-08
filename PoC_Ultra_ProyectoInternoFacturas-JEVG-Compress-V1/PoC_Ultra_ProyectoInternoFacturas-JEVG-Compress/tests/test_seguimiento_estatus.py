"""Seguimiento del estatus por el proveedor (HU-17, RF-16; specs flujo-facturas y revision-pmo)."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.core.constants import InvoiceStatus
from app.core.database import SessionLocal
from app.main import app
from app.models import Invoice, Review, Supplier, User
from tests.conftest import csrf, login
from tests.test_acceso_proveedores import messages
from tests.test_cancelacion import PROVIDER_EMAIL, business, cancel, logout, provider_invoice, reload
from tests.test_factura_internacional import INTERNATIONAL

pytestmark = pytest.mark.usefixtures("restore_notification_recipients")

PMO = "pmo@poc.local"


def name_of(email: str) -> str:
    with SessionLocal() as db:
        return db.scalar(select(User.name).where(User.email == email))


def decide(client, invoice_id: int, decision: str, comments: str = "") -> None:
    data = {"decision": decision, "comments": comments, "csrf_token": csrf(client, "/")}
    assert client.post(f"/invoices/{invoice_id}/review", data=data, follow_redirects=False).status_code == 303


def decided(decision: str, comments: str) -> Invoice:
    """Factura del proveedor 1 enviada y decidida por el PMO con `comments`."""
    invoice = provider_invoice()
    with TestClient(app) as client:
        login(client, PMO)
        decide(client, invoice.id, decision, comments)
    return reload(invoice.id)


def history_section(page: str) -> str:
    return page.split('id="history"', 1)[1].split("</section>", 1)[0]


def add_comment(invoice_id: int, text: str) -> None:
    """Revision COMMENT del PoC (comentario interno del PMO)."""
    with SessionLocal() as db:
        pmo = db.scalar(select(User.id).where(User.email == PMO))
        db.add(Review(invoice_id=invoice_id, reviewer_id=pmo, decision="COMMENT", comments=text))
        db.commit()


# --- Seguimiento ---------------------------------------------------------------------------------------------------


def test_seguimiento_del_proveedor_sin_revisor_ni_comentarios(client):
    invoice = decided("REQUIRES_CORRECTION", "Falta el Vo.Bo. firmado")
    add_comment(invoice.id, "Nota interna del PMO")
    login(client, PROVIDER_EMAIL)
    page = client.get(f"/invoices/{invoice.id}").text
    section = history_section(page)
    assert "<h2>Seguimiento</h2>" in section and "Observaciones" in section and "Falta el Vo.Bo. firmado" in section
    assert "<small>PMO</small>" in section and name_of(PMO) not in page
    assert "Comentario" not in section and "Nota interna del PMO" not in page
    # El proveedor no ve el bloque "Proveedor" del PMO.
    assert 'id="supplier"' not in page


def test_historial_del_pmo_conserva_revisor_y_comentarios(client):
    invoice = decided("REQUIRES_CORRECTION", "Falta el Vo.Bo. firmado")
    add_comment(invoice.id, "Nota interna del PMO")
    login(client, PMO)
    section = history_section(client.get(f"/invoices/{invoice.id}").text)
    assert "<h2>Historial</h2>" in section and name_of(PMO) in section
    assert "Comentario" in section and "Nota interna del PMO" in section


def test_cancelacion_en_el_historial(client):
    invoice = provider_invoice()
    login(client, PROVIDER_EMAIL)
    assert cancel(client, invoice.id).status_code == 303
    deadline = business(reload(invoice.id).cancellation_deadline)
    for email in (PROVIDER_EMAIL, PMO):
        logout(client)
        login(client, email)
        section = history_section(client.get(f"/invoices/{invoice.id}").text)
        events = re.findall(r"<strong>([^<]+)</strong>", section)
        assert events[-1] == "Cancelada", email
        assert name_of(PROVIDER_EMAIL) in section and f"Fecha límite de aceptación: {deadline}" in section


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("OBSERVACIONES-001", ["Enviada a validación", "Observaciones"]),
        ("C-RFC-ERROR", ["Enviada a validación", "Rechazada"]),
        ("CANCELADA-001", ["Enviada a validación", "Cancelada"]),
    ],
)
def test_seguimiento_de_la_demo(client, number, expected):
    login(client, PROVIDER_EMAIL)
    listing = client.get("/invoices", params={"status": "", "q": number}).text
    invoice_id = re.search(r'href="/invoices/(\d+)" aria-label', listing).group(1)
    section = history_section(client.get(f"/invoices/{invoice_id}").text)
    assert re.findall(r"<strong>([^<]+)</strong>", section) == expected


def test_sin_eventos(client):
    invoice = provider_invoice(InvoiceStatus.DRAFT)
    login(client, PROVIDER_EMAIL)
    assert "Sin envíos ni revisiones" in history_section(client.get(f"/invoices/{invoice.id}").text)


# --- Causa de la decision ------------------------------------------------------------------------------------------


def cause(page: str) -> str:
    return page.split('id="decision-cause"', 1)[1].split("</div>", 1)[0]


def test_motivo_del_rechazo_igual_al_correo(client):
    text = "El RFC del receptor no corresponde.\nEmita un CFDI nuevo."
    invoice = decided("REJECTED", text)
    [message] = [m for m in messages() if invoice.invoice_number in m["Subject"]]
    assert text in message.get_body(("plain",)).get_content()
    login(client, PROVIDER_EMAIL)
    shown = cause(client.get(f"/invoices/{invoice.id}").text)
    assert "Motivo del rechazo" in shown and text in shown and "Corrija lo indicado" not in shown


def test_observaciones_con_acceso_a_corregir(client):
    invoice = decided("REQUIRES_CORRECTION", "Falta el Vo.Bo. firmado")
    login(client, PROVIDER_EMAIL)
    shown = cause(client.get(f"/invoices/{invoice.id}").text)
    assert "Observaciones del PMO" in shown and "Falta el Vo.Bo. firmado" in shown
    assert "Corrija lo indicado y vuelva a enviar la factura" in shown
    assert f'href="/invoices/{invoice.id}/documents"' in shown
    logout(client)
    login(client, PMO)
    shown = cause(client.get(f"/invoices/{invoice.id}").text)
    assert "Falta el Vo.Bo. firmado" in shown and "Corrija lo indicado" not in shown


def test_causa_de_la_ultima_decision(client):
    invoice = decided("REQUIRES_CORRECTION", "Primera ronda")
    # Segunda ronda: reenviada y devuelta otra vez.
    with SessionLocal() as db:
        db.execute(update(Invoice).where(Invoice.id == invoice.id).values(status=InvoiceStatus.UNDER_REVIEW))
        db.commit()
    login(client, PMO)
    decide(client, invoice.id, "REQUIRES_CORRECTION", "Segunda ronda")
    logout(client)
    login(client, PROVIDER_EMAIL)
    page = client.get(f"/invoices/{invoice.id}").text
    assert "Segunda ronda" in cause(page) and "Primera ronda" not in cause(page)
    assert "Primera ronda" in history_section(page)


def test_sin_aviso_tras_reenviar(client):
    invoice = decided("REQUIRES_CORRECTION", "Falta el Vo.Bo. firmado")
    # El reenvio deja la factura "Enviada" y conserva invoices.comments de la ronda anterior.
    with SessionLocal() as db:
        db.execute(update(Invoice).where(Invoice.id == invoice.id).values(status=InvoiceStatus.UNDER_REVIEW))
        db.commit()
    login(client, PROVIDER_EMAIL)
    page = client.get(f"/invoices/{invoice.id}").text
    assert 'id="decision-cause"' not in page and "Falta el Vo.Bo. firmado" in history_section(page)


def cancelled_values() -> dict:
    with SessionLocal() as db:
        provider = db.scalar(select(User.id).where(User.email == PROVIDER_EMAIL))
    now = datetime.now(timezone.utc)
    return {"cancelled_at": now, "cancelled_by": provider, "cancellation_deadline": now + timedelta(hours=72)}


@pytest.mark.parametrize("status", [InvoiceStatus.DRAFT, InvoiceStatus.ACCEPTED, InvoiceStatus.CANCELLED])
def test_notas_fuera_de_rechazo_u_observaciones(client, status):
    # Las notas de escenario de la demo viven en invoices.comments: ya no se muestran como observaciones.
    values = {"comments": "Nota de escenario"}
    if status == InvoiceStatus.CANCELLED:
        values = {**values, **cancelled_values()}
    invoice = provider_invoice(status, **values)
    login(client, PROVIDER_EMAIL)
    page = client.get(f"/invoices/{invoice.id}").text
    assert 'id="decision-cause"' not in page and "Nota de escenario" not in page


def test_rechazada_sin_revisiones_usa_el_comentario_de_la_factura(client):
    invoice = provider_invoice(InvoiceStatus.REJECTED, comments="Rechazada antes del historial")
    login(client, PROVIDER_EMAIL)
    assert "Rechazada antes del historial" in cause(client.get(f"/invoices/{invoice.id}").text)


# --- Listado y alcance ---------------------------------------------------------------------------------------------


def other_supplier_invoice(status: InvoiceStatus) -> Invoice:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == INTERNATIONAL))
        invoice = Invoice(
            internal_folio=f"FAC-S-{uuid4().hex[:10]}",
            supplier_id=user.supplier_id,
            uploaded_by=user.id,
            invoice_number=f"HU17-{uuid4().hex[:8]}",
            service_period="09/2026",
            project_name="Proyecto ajeno",
            subtotal=Decimal("1.00"),
            tax=Decimal("0.00"),
            total=Decimal("1.00"),
            currency="USD",
            status=status,
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return invoice


def test_filtro_observaciones_con_alcance(client):
    mine = provider_invoice(InvoiceStatus.REQUIRES_CORRECTION)
    other = other_supplier_invoice(InvoiceStatus.REQUIRES_CORRECTION)
    login(client, PROVIDER_EMAIL)
    page = client.get("/invoices", params={"status": "REQUIRES_CORRECTION"}).text
    body = page.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    assert mine.internal_folio in body and other.internal_folio not in body
    statuses = re.findall(r'class="status status-([a-z_]+)"', body)
    assert statuses and set(statuses) == {"requires_correction"}
    assert client.get(f"/invoices/{other.id}").status_code == 404


# --- Tablero -------------------------------------------------------------------------------------------------------


def supplier_counts(email: str) -> dict[str, int]:
    with SessionLocal() as db:
        supplier_id = db.scalar(select(Supplier.id).where(Supplier.email == email))
        rows = db.execute(
            select(Invoice.status, func.count()).where(Invoice.supplier_id == supplier_id).group_by(Invoice.status)
        )
        return {status.value: count for status, count in rows}


def kpi(page: str, key: str) -> tuple[str, int]:
    match = re.search(rf'<a class="kpi-card[^"]*" href="([^"]+)" id="kpi-{key}"><span>[^<]+</span><strong>(\d+)', page)
    assert match, key
    return match.group(1), int(match.group(2))


def test_indicadores_del_tablero_del_proveedor(client):
    provider_invoice(InvoiceStatus.REJECTED)
    login(client, PROVIDER_EMAIL)
    page = client.get("/").text
    counts = supplier_counts(PROVIDER_EMAIL)
    assert kpi(page, "total") == ("/invoices?status=", sum(counts.values()))
    for status, label in [
        ("UNDER_REVIEW", "Enviadas"),
        ("REQUIRES_CORRECTION", "Observaciones"),
        ("ACCEPTED", "Autorizadas"),
        ("REJECTED", "Rechazadas"),
        ("CANCELLED", "Canceladas"),
    ]:
        assert kpi(page, status.lower()) == (f"/invoices?status={status}", counts.get(status, 0)), label
        assert f"<span>{label}</span>" in page


def test_indicador_lleva_al_listado_filtrado(client):
    provider_invoice(InvoiceStatus.REJECTED)
    login(client, PROVIDER_EMAIL)
    href, count = kpi(client.get("/").text, "rejected")
    body = client.get(href).text.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    statuses = re.findall(r'class="status status-([a-z_]+)"', body)
    assert set(statuses) == {"rejected"} and len(statuses) == min(count, 25)
