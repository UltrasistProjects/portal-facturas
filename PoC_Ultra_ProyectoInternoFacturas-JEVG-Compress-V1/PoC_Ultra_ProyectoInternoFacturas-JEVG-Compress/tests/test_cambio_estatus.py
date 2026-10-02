"""Decision del PMO con tres botones y sus correos (HU-20, RF-10, RN-HU20-01 a RN-HU20-03; spec revision-pmo)."""

import threading
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.constants import InvoiceStatus
from app.core.database import SessionLocal
from app.main import app
from app.models import AuditLog, EmailDelivery, Invoice, Review, Supplier, User, ValidationResult
from tests.conftest import csrf, invoice_by_number, login
from tests.test_acceso_proveedores import closed_port, messages

pytestmark = pytest.mark.usefixtures("restore_notification_recipients")

RECEPTION = "recepcionfacturas@ultrasist.com.mx"
PROVIDER_EMAIL = "proveedor1@poc.local"


# --- Datos de prueba ----------------------------------------------------------------------------------------------


def sent_invoice(**values) -> Invoice:
    """Factura "Enviada" del proveedor 1, lista para decidir."""
    with SessionLocal() as db:
        supplier_id = db.scalar(select(Supplier.id).where(Supplier.email == PROVIDER_EMAIL))
        uploader = db.scalar(select(User.id).where(User.email == PROVIDER_EMAIL))
        invoice = Invoice(
            internal_folio=f"FAC-D-{uuid4().hex[:10]}",
            supplier_id=supplier_id,
            uploaded_by=uploader,
            invoice_number=f"HU20-{uuid4().hex[:8]}",
            service_period="09/2026",
            project_name="Proyecto de decision",
            subtotal=Decimal("100000.00"),
            tax=Decimal("16000.00"),
            total=Decimal("116000.00"),
            currency="MXN",
            status=InvoiceStatus.UNDER_REVIEW,
            submitted_at=datetime.now(timezone.utc),
            **values,
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return invoice


def decide(client, invoice_id: int, decision: str, comments: str = ""):
    data = {"decision": decision, "comments": comments, "csrf_token": csrf(client, f"/invoices/{invoice_id}")}
    return client.post(f"/invoices/{invoice_id}/review", data=data, follow_redirects=False)


def reload(invoice_id: int) -> Invoice:
    with SessionLocal() as db:
        return db.get(Invoice, invoice_id)


def reviews(invoice_id: int) -> list[Review]:
    with SessionLocal() as db:
        return list(db.scalars(select(Review).where(Review.invoice_id == invoice_id)))


def deliveries(invoice_id: int) -> list[EmailDelivery]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(EmailDelivery)
                .where(EmailDelivery.entity == "Invoice", EmailDelivery.entity_id == str(invoice_id))
                .order_by(EmailDelivery.id)
            )
        )


def audits(invoice_id: int, action: str) -> list[AuditLog]:
    with SessionLocal() as db:
        return list(
            db.scalars(select(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == str(invoice_id)))
        )


def mail_for(number: str):
    [message] = [m for m in messages() if number in m["Subject"]]
    return message


@pytest.fixture()
def smtp_down(monkeypatch):
    monkeypatch.setattr(settings, "mail_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", closed_port())
    monkeypatch.setattr(settings, "smtp_timeout", 2)


# --- Panel de decision --------------------------------------------------------------------------------------------


def test_panel_para_el_pmo_en_una_factura_enviada(client):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    page = client.get(f"/invoices/{invoice.id}").text
    assert 'id="decision"' in page and 'href="#decision"' in page
    for value, label in (("ACCEPTED", "Autorizar"), ("REQUIRES_CORRECTION", "Observaciones"), ("REJECTED", "Rechazar")):
        assert f'name="decision" value="{value}"' in page and label in page
    assert 'value="COMMENT"' not in page and "/static/js/review_decision.js" in page


def test_sin_panel_para_el_proveedor_ni_en_otros_estatus(client):
    invoice = sent_invoice()
    login(client, PROVIDER_EMAIL)
    assert 'id="decision"' not in client.get(f"/invoices/{invoice.id}").text
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, "pmo@poc.local")
    assert 'id="decision"' not in client.get(f"/invoices/{invoice_by_number('ACEPTADA-001').id}").text


def test_pagina_de_revision_redirige_al_panel(client):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    response = client.get(f"/invoices/{invoice.id}/review", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == f"/invoices/{invoice.id}#decision"


# --- Decisiones ---------------------------------------------------------------------------------------------------


def test_autorizar(client):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    response = decide(client, invoice.id, "ACCEPTED")
    [delivery] = deliveries(invoice.id)
    assert response.headers["location"] == f"/invoices/{invoice.id}?notification={delivery.id}#decision-result"
    decided = reload(invoice.id)
    with SessionLocal() as db:
        pmo = db.scalar(select(User.id).where(User.email == "pmo@poc.local"))
    assert (decided.status, decided.reviewed_by, decided.comments) == (InvoiceStatus.ACCEPTED, pmo, None)
    assert [(r.decision, r.comments) for r in reviews(invoice.id)] == [("ACCEPTED", None)]
    assert audits(invoice.id, "STATUS_CHANGED") and audits(invoice.id, "ACCEPTED")
    page = client.get(response.headers["location"]).text
    assert f"Correo enviado a {RECEPTION}" in page and 'id="decision"' not in page


def test_observaciones(client):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    assert decide(client, invoice.id, "REQUIRES_CORRECTION", "  Falta el Vo.Bo. firmado  ").status_code == 303
    decided = reload(invoice.id)
    assert (decided.status, decided.comments) == (InvoiceStatus.REQUIRES_CORRECTION, "Falta el Vo.Bo. firmado")
    assert "Falta el Vo.Bo. firmado" in client.get(f"/invoices/{invoice.id}").text


@pytest.mark.parametrize("decision", ["COMMENT", "QUIZAS"])
def test_decision_invalida(client, decision):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    response = decide(client, invoice.id, decision, "ok")
    assert response.status_code == 400 and "Decisión inválida" in response.text
    assert reload(invoice.id).status == InvoiceStatus.UNDER_REVIEW and reviews(invoice.id) == []


def test_proveedor_no_decide(client):
    invoice = sent_invoice()
    login(client, PROVIDER_EMAIL)
    assert decide(client, invoice.id, "ACCEPTED").status_code == 403
    assert reload(invoice.id).status == InvoiceStatus.UNDER_REVIEW


@pytest.mark.parametrize("decision", ["REJECTED", "REQUIRES_CORRECTION"])
@pytest.mark.parametrize("comments", ["", "   "])
def test_observaciones_obligatorias(client, decision, comments):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    response = decide(client, invoice.id, decision, comments)
    assert response.status_code == 400 and "Capture las observaciones" in response.text
    assert reload(invoice.id).status == InvoiceStatus.UNDER_REVIEW
    assert reviews(invoice.id) == [] and deliveries(invoice.id) == []


def test_observaciones_demasiado_largas(client):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    response = decide(client, invoice.id, "REQUIRES_CORRECTION", "x" * 2001)
    assert response.status_code == 400 and "Las observaciones admiten hasta 2,000 caracteres" in response.text


def test_factura_no_enviada(client):
    login(client, "pmo@poc.local")
    response = decide(client, invoice_by_number("A-CORRECTA").id, "ACCEPTED")
    assert response.status_code == 409 and "La factura no está en revisión" in response.text


def test_decision_repetida(client):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    assert decide(client, invoice.id, "ACCEPTED").status_code == 303
    response = decide(client, invoice.id, "REJECTED", "Tarde")
    assert response.status_code == 409 and "La factura ya fue revisada" in response.text
    assert len(reviews(invoice.id)) == 1 and len(deliveries(invoice.id)) == 1
    assert reload(invoice.id).status == InvoiceStatus.ACCEPTED


def test_decisiones_simultaneas():
    invoice = sent_invoice()
    start, statuses = threading.Barrier(2), []

    def pmo_decides(decision: str, comments: str) -> None:
        with TestClient(app) as client:
            login(client, "pmo@poc.local")
            token = csrf(client, f"/invoices/{invoice.id}")
            start.wait()
            data = {"decision": decision, "comments": comments, "csrf_token": token}
            statuses.append(
                client.post(f"/invoices/{invoice.id}/review", data=data, follow_redirects=False).status_code
            )

    threads = [
        threading.Thread(target=pmo_decides, args=("ACCEPTED", "")),
        threading.Thread(target=pmo_decides, args=("REJECTED", "Duplicada")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(statuses) == [303, 409]
    assert len(reviews(invoice.id)) == 1 and len(deliveries(invoice.id)) == 1


def test_no_se_autoriza_con_bloqueo_critico(client):
    invoice = sent_invoice()
    with SessionLocal() as db:
        db.add(
            ValidationResult(
                invoice_id=invoice.id,
                rule_code="FIN-001",
                category="FIN",
                status="FAIL",
                severity="CRITICAL",
                message="El subtotal excede el monto autorizado",
            )
        )
        db.commit()
    login(client, "pmo@poc.local")
    response = decide(client, invoice.id, "ACCEPTED")
    assert response.status_code == 409 and "No se puede aceptar con bloqueos criticos" in response.text
    assert reload(invoice.id).status == InvoiceStatus.UNDER_REVIEW and deliveries(invoice.id) == []


# --- Correos de la decision ---------------------------------------------------------------------------------------


def test_autorizacion_notificada_a_recepcion(client):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    decide(client, invoice.id, "ACCEPTED")
    message = mail_for(invoice.invoice_number)
    assert message["To"] == RECEPTION and message["Subject"] == f"Factura {invoice.invoice_number} autorizada para pago"
    body = message.get_body(("plain",)).get_content()
    assert (
        f"La factura número {invoice.invoice_number} del proveedor Tecnologia Integral del Centro SA de CV "
        "por el monto $116,000.00 MXN ha sido Autorizada para su pago."
    ) in body


@pytest.mark.parametrize(("decision", "label"), [("REJECTED", "Rechazada"), ("REQUIRES_CORRECTION", "Observaciones")])
def test_rechazo_y_observaciones_notificados_al_proveedor(client, decision, label):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    decide(client, invoice.id, decision, "El RFC del receptor no corresponde")
    message = mail_for(invoice.invoice_number)
    assert message["To"] == PROVIDER_EMAIL
    body = message.get_body(("plain",)).get_content()
    assert f"“{label}”" in body and "El RFC del receptor no corresponde" in body
    [delivery] = deliveries(invoice.id)
    assert delivery.event == ("INVOICE_REJECTED" if decision == "REJECTED" else "INVOICE_OBSERVATIONS")


def test_resultado_de_otro_envio_no_se_muestra(client):
    first, second = sent_invoice(), sent_invoice()
    login(client, "pmo@poc.local")
    decide(client, first.id, "ACCEPTED")
    [other] = deliveries(first.id)
    for value in (str(other.id), "abc", "999999999"):
        page = client.get(f"/invoices/{second.id}", params={"notification": value}).text
        assert "Correo enviado a" not in page and "No se pudo enviar" not in page


def test_servidor_de_correo_caido(client, smtp_down):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    response = decide(client, invoice.id, "ACCEPTED")
    assert reload(invoice.id).status == InvoiceStatus.ACCEPTED
    [delivery] = deliveries(invoice.id)
    assert delivery.status == "FAILED" and delivery.error
    page = client.get(response.headers["location"]).text
    assert "No se pudo enviar el correo" in page and "Reenviar notificación" in page


# --- Reenvio de la notificacion -----------------------------------------------------------------------------------


def resend(client, invoice_id: int):
    token = csrf(client, f"/invoices/{invoice_id}")
    return client.post(f"/invoices/{invoice_id}/notification", data={"csrf_token": token}, follow_redirects=False)


def test_reenvio_tras_una_falla(client, monkeypatch):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    monkeypatch.setattr(settings, "mail_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", closed_port())
    monkeypatch.setattr(settings, "smtp_timeout", 2)
    decide(client, invoice.id, "REQUIRES_CORRECTION", "Corrija el periodo")
    monkeypatch.setattr(settings, "mail_backend", "file")
    response = resend(client, invoice.id)
    failed, sent = deliveries(invoice.id)
    assert (failed.status, sent.status) == ("FAILED", "SENT")
    assert response.headers["location"] == f"/invoices/{invoice.id}?notification={sent.id}#decision-result"
    assert "Corrija el periodo" in mail_for(invoice.invoice_number).get_body(("plain",)).get_content()
    [entry] = audits(invoice.id, "INVOICE_NOTIFICATION_RESENT")
    assert entry.new_value == {"event": "INVOICE_OBSERVATIONS"}
    page = client.get(response.headers["location"]).text
    assert f"Correo enviado a {PROVIDER_EMAIL}" in page and "Reenviar notificación" not in page


def test_reenvio_sin_falla_previa(client):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    decide(client, invoice.id, "ACCEPTED")
    response = resend(client, invoice.id)
    assert response.status_code == 409 and "No hay una notificación fallida que reenviar" in response.text
    assert len(deliveries(invoice.id)) == 1 and audits(invoice.id, "INVOICE_NOTIFICATION_RESENT") == []


def test_reenvio_del_proveedor(client, smtp_down):
    invoice = sent_invoice()
    login(client, "pmo@poc.local")
    decide(client, invoice.id, "ACCEPTED")
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, PROVIDER_EMAIL)
    assert resend(client, invoice.id).status_code == 403
