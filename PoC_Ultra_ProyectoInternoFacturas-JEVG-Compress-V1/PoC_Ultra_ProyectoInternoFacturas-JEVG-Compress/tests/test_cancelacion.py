"""Cancelacion de la factura por el proveedor con su acuse y aviso a Recepcion de Facturas (HU-14, RF-09; specs
cancelacion-facturas, flujo-facturas, archivos-minimos-factura, revision-pmo y factura-internacional)."""

import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.constants import InvoiceStatus
from app.core.database import SessionLocal
from app.core.timeutils import to_business
from app.main import app
from app.models import AuditLog, Document, EmailDelivery, Invoice, Supplier, User
from tests.conftest import csrf, login
from tests.test_acceso_proveedores import closed_port, messages
from tests.test_factura_internacional import INTERNATIONAL, INVOICE_TEXT, complete, new_invoice, pdf, results, upload

pytestmark = pytest.mark.usefixtures("restore_notification_recipients")

RECEPTION = "recepcionfacturas@ultrasist.com.mx"
PROVIDER_EMAIL = "proveedor1@poc.local"
PROVIDER_NAME = "Tecnologia Integral del Centro SA de CV"
PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
# Acuse de cancelacion que entrega el SAT: un XML que no es un CFDI.
SAT_ACK = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<Acuse Fecha="2026-09-25T10:30:00" RfcEmisor="TIC200101AB1">'
    b"<Folios><UUID>6F1E6A7C-0000-4000-8000-000000000001</UUID><EstatusUUID>201</EstatusUUID></Folios></Acuse>"
)
CONFIRM_LABEL = "Confirmo que la factura se canceló y adjunto su acuse"


# --- Datos de prueba ----------------------------------------------------------------------------------------------


def provider_invoice(status: InvoiceStatus = InvoiceStatus.UNDER_REVIEW, **values) -> Invoice:
    """Factura del proveedor 1 en `status`, sin documentos."""
    with SessionLocal() as db:
        supplier_id = db.scalar(select(Supplier.id).where(Supplier.email == PROVIDER_EMAIL))
        uploader = db.scalar(select(User.id).where(User.email == PROVIDER_EMAIL))
        invoice = Invoice(
            internal_folio=f"FAC-C-{uuid4().hex[:10]}",
            supplier_id=supplier_id,
            uploaded_by=uploader,
            invoice_number=f"HU14-{uuid4().hex[:8]}",
            service_period="09/2026",
            project_name="Proyecto a cancelar",
            subtotal=Decimal("100000.00"),
            tax=Decimal("16000.00"),
            total=Decimal("116000.00"),
            currency="MXN",
            status=status,
            **values,
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return invoice


def user_id(email: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == email))


def cancel(client, invoice_id: int, filename: str | None = "acuse.pdf", content: bytes = PDF, confirm: bool = True):
    data = {"csrf_token": csrf(client, "/")}
    if confirm:
        data["confirm"] = "1"
    files = {"upload": (filename, content, "application/octet-stream")} if filename is not None else None
    return client.post(f"/invoices/{invoice_id}/cancel", data=data, files=files, follow_redirects=False)


def reload(invoice_id: int) -> Invoice:
    with SessionLocal() as db:
        return db.get(Invoice, invoice_id)


def acknowledgments(invoice_id: int) -> list[Document]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(Document).where(Document.invoice_id == invoice_id, Document.document_type == "CANCELLATION_ACK")
            )
        )


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


def stored_files(invoice_id: int) -> list:
    folder = settings.storage_path / "invoices" / str(invoice_id)
    return sorted(folder.iterdir()) if folder.exists() else []


def business(value: datetime) -> str:
    return to_business(value).strftime("%d/%m/%Y %H:%M")


def logout(client) -> None:
    client.post("/logout", data={"csrf_token": csrf(client, "/")})


@pytest.fixture()
def smtp_down(monkeypatch):
    monkeypatch.setattr(settings, "mail_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", closed_port())
    monkeypatch.setattr(settings, "smtp_timeout", 2)


# --- Seccion "Cancelar factura" -----------------------------------------------------------------------------------


def test_seccion_para_el_proveedor(client):
    invoice = provider_invoice()
    login(client, PROVIDER_EMAIL)
    page = client.get(f"/invoices/{invoice.id}").text
    assert 'id="cancellation"' in page and "Cancelar factura" in page and CONFIRM_LABEL in page
    assert f'action="/invoices/{invoice.id}/cancel"' in page and 'enctype="multipart/form-data"' in page
    assert 'accept=".pdf,.xml"' in page and "Formatos admitidos: PDF, XML" in page
    # Cerrada mientras no haya un error que mostrar.
    assert 'id="cancellation" open' not in page


@pytest.mark.parametrize("email", ["pmo@poc.local", "admin@poc.local"])
def test_sin_cancelacion_para_el_pmo_ni_el_administrador(client, email):
    invoice = provider_invoice()
    login(client, email)
    assert 'id="cancellation"' not in client.get(f"/invoices/{invoice.id}").text
    assert cancel(client, invoice.id).status_code == 403
    assert reload(invoice.id).status == InvoiceStatus.UNDER_REVIEW and acknowledgments(invoice.id) == []


def test_factura_de_otro_proveedor(client):
    invoice = provider_invoice()
    login(client, INTERNATIONAL)
    assert cancel(client, invoice.id).status_code == 404
    assert reload(invoice.id).status == InvoiceStatus.UNDER_REVIEW and stored_files(invoice.id) == []


# --- Acuse obligatorio y confirmacion -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "confirm", "message"),
    [
        ("acuse.pdf", False, "Confirme la cancelación"),
        # Sin archivo ni confirmacion: primero la confirmacion.
        (None, False, "Confirme la cancelación"),
        # Sin el campo del archivo, y con el campo vacio que envia el navegador.
        (None, True, "Cargue el Acuse de cancelación"),
        ("", True, "Cargue el Acuse de cancelación"),
        ("acuse.png", True, "Formato no admitido para Acuse de cancelación. Formatos admitidos: PDF, XML"),
    ],
)
def test_validaciones_antes_de_escribir(client, filename, confirm, message):
    invoice = provider_invoice()
    login(client, PROVIDER_EMAIL)
    content = b"" if filename == "" else PDF
    response = cancel(client, invoice.id, filename, content, confirm)
    assert response.status_code == 400 and message in response.text
    # El detalle vuelve con la seccion abierta y el error dentro de ella.
    section = response.text.split('id="cancellation" open>', 1)[1]
    assert message in section.split("</details>", 1)[0]
    assert reload(invoice.id).status == InvoiceStatus.UNDER_REVIEW
    assert acknowledgments(invoice.id) == [] and stored_files(invoice.id) == []


def test_contenido_que_no_corresponde(client):
    invoice = provider_invoice()
    login(client, PROVIDER_EMAIL)
    response = cancel(client, invoice.id, "acuse.pdf", b"no es un PDF")
    assert response.status_code == 400 and "El contenido no corresponde a un PDF" in response.text
    assert reload(invoice.id).status == InvoiceStatus.UNDER_REVIEW
    assert acknowledgments(invoice.id) == [] and stored_files(invoice.id) == []


def test_acuse_xml_del_sat(client):
    invoice = provider_invoice()
    login(client, PROVIDER_EMAIL)
    assert cancel(client, invoice.id, "acuse_sat.xml", SAT_ACK).status_code == 303
    [ack] = acknowledgments(invoice.id)
    assert (ack.original_filename, ack.mime_type, ack.metadata_json) == ("acuse_sat.xml", "application/xml", {})
    assert reload(invoice.id).status == InvoiceStatus.CANCELLED


# --- Registro de la cancelacion -----------------------------------------------------------------------------------


def test_cancelar_una_factura_enviada(client):
    invoice = provider_invoice()
    login(client, PROVIDER_EMAIL)
    response = cancel(client, invoice.id, "Acuse A-2001.pdf")
    [delivery] = deliveries(invoice.id)
    assert response.status_code == 303
    assert response.headers["location"] == f"/invoices/{invoice.id}?notification={delivery.id}#cancellation-result"
    cancelled = reload(invoice.id)
    assert cancelled.status == InvoiceStatus.CANCELLED and cancelled.cancelled_by == user_id(PROVIDER_EMAIL)
    assert cancelled.cancellation_deadline - cancelled.cancelled_at == timedelta(hours=72)
    [ack] = acknowledgments(invoice.id)
    assert (ack.original_filename, ack.is_current) == ("Acuse A-2001.pdf", True)
    assert ack.uploaded_by == user_id(PROVIDER_EMAIL)
    [changed] = audits(invoice.id, "STATUS_CHANGED")
    assert (changed.old_value, changed.new_value) == ({"status": "UNDER_REVIEW"}, {"status": "CANCELLED"})
    [entry] = audits(invoice.id, "INVOICE_CANCELLED")
    assert entry.old_value == {"status": "UNDER_REVIEW"}
    assert entry.new_value == {"document_id": ack.id, "deadline": cancelled.cancellation_deadline.isoformat()}
    page = client.get(response.headers["location"]).text
    assert "Acuse de cancelación" in page and f"/invoices/{invoice.id}/documents/{ack.id}/download" in page
    assert client.get(f"/invoices/{invoice.id}/documents/{ack.id}/download").content == PDF


@pytest.mark.parametrize(
    "status",
    [
        InvoiceStatus.DRAFT,
        InvoiceStatus.UPLOADED,
        InvoiceStatus.REQUIRES_CORRECTION,
        InvoiceStatus.ACCEPTED,
        InvoiceStatus.REJECTED,
    ],
)
def test_cancelar_desde_cualquier_estatus(client, status):
    invoice = provider_invoice(status)
    login(client, PROVIDER_EMAIL)
    assert cancel(client, invoice.id).status_code == 303
    assert reload(invoice.id).status == InvoiceStatus.CANCELLED
    [entry] = audits(invoice.id, "INVOICE_CANCELLED")
    assert entry.old_value == {"status": status.value}


def test_cancelacion_repetida(client):
    invoice = provider_invoice()
    login(client, PROVIDER_EMAIL)
    assert cancel(client, invoice.id).status_code == 303
    response = cancel(client, invoice.id)
    assert response.status_code == 409 and "La factura ya está cancelada" in response.text
    assert len(acknowledgments(invoice.id)) == 1 and len(stored_files(invoice.id)) == 1
    assert len(deliveries(invoice.id)) == 1
    # Un formulario viejo sin acuse tampoco da un 400 sin seccion donde mostrarlo.
    stale = cancel(client, invoice.id, None, confirm=False)
    assert stale.status_code == 409 and "La factura ya está cancelada" in stale.text


def test_cancelaciones_simultaneas():
    invoice = provider_invoice()
    start, statuses = threading.Barrier(2), []

    def provider_cancels() -> None:
        with TestClient(app) as client:
            login(client, PROVIDER_EMAIL)
            token = csrf(client, f"/invoices/{invoice.id}")
            start.wait()
            response = client.post(
                f"/invoices/{invoice.id}/cancel",
                data={"confirm": "1", "csrf_token": token},
                files={"upload": ("acuse.pdf", PDF, "application/pdf")},
                follow_redirects=False,
            )
            statuses.append(response.status_code)

    threads = [threading.Thread(target=provider_cancels) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(statuses) == [303, 409]
    assert len(acknowledgments(invoice.id)) == 1 and len(stored_files(invoice.id)) == 1
    assert len(audits(invoice.id, "INVOICE_CANCELLED")) == 1 and len(deliveries(invoice.id)) == 1


def test_factura_cancelada_no_admite_cambios(client):
    invoice = provider_invoice(InvoiceStatus.UPLOADED)
    login(client, PROVIDER_EMAIL)
    assert cancel(client, invoice.id).status_code == 303
    token = csrf(client, f"/invoices/{invoice.id}")
    uploaded = client.post(
        f"/invoices/{invoice.id}/documents",
        data={"document_type": "PURCHASE_ORDER", "csrf_token": token},
        files={"upload": ("oc.txt", b"Orden de compra", "text/plain")},
        follow_redirects=False,
    )
    assert uploaded.status_code == 409
    for action in ("validation", "submit"):
        response = client.post(f"/invoices/{invoice.id}/{action}", data={"csrf_token": token}, follow_redirects=False)
        assert response.status_code == 409, action
    assert client.get(f"/invoices/{invoice.id}/documents", follow_redirects=False).status_code == 303
    page = client.get(f"/invoices/{invoice.id}").text
    assert 'id="cancellation"' not in page and "Gestionar documentos" not in page and "Enviar a validación" not in page
    logout(client)
    login(client, "pmo@poc.local")
    data = {"decision": "ACCEPTED", "comments": "", "csrf_token": csrf(client, f"/invoices/{invoice.id}")}
    response = client.post(f"/invoices/{invoice.id}/review", data=data, follow_redirects=False)
    assert response.status_code == 409 and "La factura no está en revisión" in response.text
    assert reload(invoice.id).status == InvoiceStatus.CANCELLED and len(stored_files(invoice.id)) == 1


def test_factura_cancelada_sale_de_la_bandeja(client):
    # Se busca por numero y se revisa el folio: el numero tambien aparece en el campo de busqueda.
    invoice = provider_invoice()
    login(client, "pmo@poc.local")
    assert invoice.internal_folio in client.get("/invoices", params={"q": invoice.invoice_number}).text
    logout(client)
    login(client, PROVIDER_EMAIL)
    cancel(client, invoice.id)
    logout(client)
    login(client, "pmo@poc.local")
    assert invoice.internal_folio not in client.get("/invoices", params={"q": invoice.invoice_number}).text
    listed = client.get("/invoices", params={"q": invoice.invoice_number, "status": "CANCELLED"}).text
    assert invoice.internal_folio in listed and 'class="status status-cancelled">Cancelada' in listed


# --- Factura cancelada en el detalle ------------------------------------------------------------------------------


@pytest.mark.parametrize("email", ["pmo@poc.local", PROVIDER_EMAIL])
def test_aviso_de_factura_cancelada(client, email):
    # 16:30 UTC es 10:30 en la Ciudad de Mexico, sin horario de verano.
    cancelled_at = datetime(2026, 9, 25, 16, 30, tzinfo=timezone.utc)
    invoice = provider_invoice(
        InvoiceStatus.CANCELLED,
        submitted_at=cancelled_at - timedelta(days=1),
        cancelled_at=cancelled_at,
        cancelled_by=user_id(PROVIDER_EMAIL),
        cancellation_deadline=cancelled_at + timedelta(hours=72),
    )
    login(client, email)
    page = client.get(f"/invoices/{invoice.id}").text
    assert (
        "Cancelada el 25/09/2026 10:30. Recepción de Facturas debe aceptar la cancelación antes del 28/09/2026 10:30."
    ) in page
    assert 'class="status status-cancelled"' in page
    assert 'id="cancellation"' not in page and 'id="decision"' not in page


# --- Correo a Recepcion de Facturas -------------------------------------------------------------------------------


def test_aviso_a_recepcion_con_la_fecha_limite(client):
    invoice = provider_invoice()
    login(client, PROVIDER_EMAIL)
    response = cancel(client, invoice.id)
    cancelled = reload(invoice.id)
    [message] = [m for m in messages() if invoice.invoice_number in m["Subject"]]
    assert message["To"] == RECEPTION
    assert message["Subject"] == f"Cancelación de la factura {invoice.invoice_number} de {PROVIDER_NAME}"
    body = message.get_body(("plain",)).get_content()
    assert (
        f"La factura número {invoice.invoice_number} del proveedor {PROVIDER_NAME} ha sido cancelada. "
        f"Por favor acepte la “Cancelación” antes del {business(cancelled.cancellation_deadline)}."
    ) in body
    assert f"Folio interno: {invoice.internal_folio}" in body and "Monto: $116,000.00 MXN" in body
    assert f"Fecha de la solicitud: {business(cancelled.cancelled_at)}" in body
    [delivery] = deliveries(invoice.id)
    assert (delivery.event, delivery.status) == ("INVOICE_CANCELLED", "SENT")
    page = client.get(response.headers["location"]).text
    assert "Se notificó a Recepción de Facturas" in page and RECEPTION not in page


def test_servidor_de_correo_caido_y_reenvio(client, smtp_down, monkeypatch):
    invoice = provider_invoice()
    login(client, PROVIDER_EMAIL)
    response = cancel(client, invoice.id)
    assert reload(invoice.id).status == InvoiceStatus.CANCELLED
    [failed] = deliveries(invoice.id)
    assert failed.status == "FAILED"
    page = client.get(response.headers["location"]).text
    assert "No se pudo notificar a Recepción de Facturas" in page and failed.error not in page
    assert "Reenviar notificación" not in page
    logout(client)
    login(client, "pmo@poc.local")
    page = client.get(f"/invoices/{invoice.id}").text
    assert "El último correo de la cancelación no se envió." in page and "Reenviar notificación" in page
    monkeypatch.setattr(settings, "mail_backend", "file")
    token = csrf(client, f"/invoices/{invoice.id}")
    resent = client.post(f"/invoices/{invoice.id}/notification", data={"csrf_token": token}, follow_redirects=False)
    _, sent = deliveries(invoice.id)
    assert (sent.event, sent.status) == ("INVOICE_CANCELLED", "SENT")
    assert resent.headers["location"] == f"/invoices/{invoice.id}?notification={sent.id}#decision-result"
    [message] = [m for m in messages() if invoice.invoice_number in m["Subject"]]
    deadline = business(reload(invoice.id).cancellation_deadline)
    assert message["To"] == RECEPTION and f"antes del {deadline}." in message.get_body(("plain",)).get_content()
    [entry] = audits(invoice.id, "INVOICE_NOTIFICATION_RESENT")
    assert entry.new_value == {"event": "INVOICE_CANCELLED"}
    page = client.get(resent.headers["location"]).text
    assert f"Correo enviado a {RECEPTION}" in page and "Reenviar notificación" not in page


def test_proveedor_no_ve_otros_correos(client):
    invoice = provider_invoice()
    login(client, "pmo@poc.local")
    data = {"decision": "ACCEPTED", "comments": "", "csrf_token": csrf(client, f"/invoices/{invoice.id}")}
    client.post(f"/invoices/{invoice.id}/review", data=data, follow_redirects=False)
    [authorized] = deliveries(invoice.id)
    logout(client)
    login(client, PROVIDER_EMAIL)
    for value in (str(authorized.id), "error"):
        page = client.get(f"/invoices/{invoice.id}", params={"notification": value}).text
        assert "Factura cancelada." not in page and "Correo enviado a" not in page
        assert 'id="decision-result"' not in page


# --- Catalogo: el acuse no forma parte de la carga documental -----------------------------------------------------


def test_acuse_fuera_de_la_carga_documental(client):
    invoice = provider_invoice(InvoiceStatus.DRAFT)
    login(client, PROVIDER_EMAIL)
    assert "Acuse de cancelación" not in client.get(f"/invoices/{invoice.id}/documents").text
    response = client.post(
        f"/invoices/{invoice.id}/documents",
        data={"document_type": "CANCELLATION_ACK", "csrf_token": csrf(client, f"/invoices/{invoice.id}")},
        files={"upload": ("acuse.pdf", PDF, "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 400 and acknowledgments(invoice.id) == []


def test_acuse_editable_en_la_matriz_del_administrador(client):
    """Ya no hay niveles fijos (ajustes-finales-configuracion): el acuse tiene selectores como cualquier tipo."""
    login(client, "admin@poc.local")
    page = client.get("/admin/required-documents").text
    row = page.split("Acuse de cancelación", 1)[1].split("</tr>", 1)[0]
    assert "bi-lock-fill" not in row and row.count("__CANCELLATION_ACK") == 2
    assert "La cancelación de facturas dejará de pedir el acuse." in row


@pytest.fixture()
def acknowledgment_deleted():
    """Elimina (baja logica) el tipo del acuse y lo restaura al terminar."""
    from sqlalchemy import update

    from app.models import InvoiceDocumentType, now_utc

    ack = InvoiceDocumentType.code == "CANCELLATION_ACK"
    with SessionLocal() as db:
        db.execute(update(InvoiceDocumentType).where(ack).values(is_active=False, deleted_at=now_utc()))
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(update(InvoiceDocumentType).where(ack).values(is_active=True, deleted_at=None, deleted_by=None))
        db.commit()


@pytest.mark.usefixtures("acknowledgment_deleted")
def test_cancelacion_sin_acuse_si_su_tipo_esta_eliminado(client):
    invoice = provider_invoice(InvoiceStatus.UPLOADED)
    login(client, PROVIDER_EMAIL)
    page = client.get(f"/invoices/{invoice.id}").text
    assert 'name="upload"' not in page and "Confirmo que la factura se canceló</label>" in page
    assert cancel(client, invoice.id, filename=None).status_code == 303
    assert reload(invoice.id).status == InvoiceStatus.CANCELLED
    assert acknowledgments(invoice.id) == [] and stored_files(invoice.id) == []
    [entry] = audits(invoice.id, "INVOICE_CANCELLED")
    assert entry.new_value["document_id"] is None


def test_nombre_del_invoice_de_una_factura_cancelada(client):
    login(client, INTERNATIONAL)
    first, second = new_invoice(client), new_invoice(client)
    name = f"INV-{uuid4().hex[:6]}.pdf"
    assert upload(client, first.id, "FOREIGN_INVOICE", name, pdf(INVOICE_TEXT)).status_code == 303
    assert upload(client, second.id, "FOREIGN_INVOICE", name, pdf(INVOICE_TEXT)).status_code == 409
    assert cancel(client, first.id).status_code == 303
    complete(client, second.id, pdf(INVOICE_TEXT), name)
    token = csrf(client, f"/invoices/{second.id}")
    assert client.post(f"/invoices/{second.id}/validation", data={"csrf_token": token}).status_code == 200
    assert results(second.id)["FIN-007"].status == "PASS"
