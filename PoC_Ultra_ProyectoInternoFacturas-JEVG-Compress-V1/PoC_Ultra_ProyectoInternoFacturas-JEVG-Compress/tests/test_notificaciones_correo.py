"""Destinatarios y envio de notificaciones por correo (HU-08, spec notificaciones-correo)."""

import html
import re
import smtplib
import socket
import ssl
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from email import policy
from email.parser import BytesParser

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.constants import DeliveryStatus, NotificationEvent
from app.core.database import SessionLocal
from app.models import AuditLog, EmailDelivery, NotificationCopy, NotificationMailbox, User
from app.services import mail_layout
from app.services import notification_service as ns
from tests.conftest import OUTBOX, RECEPTION_SEED, csrf, login

pytestmark = pytest.mark.usefixtures("restore_notification_recipients")

URL = "/admin/notifications"
RECEPTION = "INVOICE_RECEPTION"
AUTHORIZED = NotificationEvent.INVOICE_AUTHORIZED
REJECTED = NotificationEvent.INVOICE_REJECTED
OBSERVATIONS = NotificationEvent.INVOICE_OBSERVATIONS
CANCELLED = NotificationEvent.INVOICE_CANCELLED
# Valores completos de un correo de factura; cada prueba cambia solo lo que le interesa.
VALUES = {
    "numero_factura": "A-1024",
    "folio_interno": "FAC-2026-00042",
    "proveedor": "Servicios Digitales del Norte SA de CV",
    "monto": Decimal("116000.00"),
    "moneda": "MXN",
    "fecha_estatus": datetime(2026, 9, 25, 16, 30, tzinfo=timezone.utc),
    "observaciones": "El subtotal del XML no coincide con el de la orden de compra.",
    "fecha_limite_cancelacion": datetime(2026, 9, 28, 16, 30, tzinfo=timezone.utc),
}


# --- Utilidades ---------------------------------------------------------------------------------------------------


def configuration() -> dict[str, list[str]]:
    with SessionLocal() as db:
        config = ns.load(db)
        return {item.key: item.addresses for item in ns.recipient_lists(config)}


def set_lists(**lists: list[str]) -> None:
    """Escribe listas directamente en la base de datos (INVOICE_RECEPTION o el codigo de un evento)."""
    with SessionLocal() as db:
        for key, addresses in lists.items():
            if key == RECEPTION:
                db.execute(update(NotificationMailbox).values(addresses=addresses))
            else:
                db.execute(update(NotificationCopy).where(NotificationCopy.event == key).values(addresses=addresses))
        db.commit()


def current_version() -> str:
    with SessionLocal() as db:
        return ns.config_version(ns.load(db))


def form_data(client, **fields) -> dict:
    """Formulario con la configuracion y la huella vigentes, y las listas indicadas cambiadas (texto libre)."""
    data = {key: "\n".join(addresses) for key, addresses in configuration().items()}
    return {**data, "config_version": current_version(), "csrf_token": csrf(client, "/"), **fields}


def save(client, **fields):
    return client.post(URL, data=form_data(client, **fields), follow_redirects=False)


def send_test(client, address: str):
    return client.post(
        f"{URL}/test", data={"address": address, "csrf_token": csrf(client, "/")}, follow_redirects=False
    )


def deliveries() -> list[EmailDelivery]:
    with SessionLocal() as db:
        return list(db.scalars(select(EmailDelivery).order_by(EmailDelivery.id)))


def audit_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(AuditLog.id)))


def outbox_messages() -> list:
    files = sorted(OUTBOX.glob("*.eml")) if OUTBOX.exists() else []
    return [BytesParser(policy=policy.default).parsebytes(path.read_bytes()) for path in files]


def notify(event: NotificationEvent, **overrides):
    with SessionLocal() as db:
        return ns.notify(db, event, **{**VALUES, **overrides})


def admin() -> User:
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.email == "admin@poc.local"))


def closed_port() -> int:
    """Puerto local sin servicio: la conexion SMTP se rechaza de inmediato."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture()
def smtp_settings(monkeypatch):
    """Transporte SMTP hacia un puerto cerrado de localhost, con usuario y contrasena."""
    monkeypatch.setattr(settings, "mail_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", closed_port())
    monkeypatch.setattr(settings, "smtp_security", "starttls")
    monkeypatch.setattr(settings, "smtp_username", "usuario-smtp-secreto")
    monkeypatch.setattr(settings, "smtp_password", SecretStr("Clave#Smtp#Secreta"))
    monkeypatch.setattr(settings, "smtp_timeout", 2)
    monkeypatch.setattr(settings, "mail_from", "Portal ULTRASIST <portal@ultrasist.com.mx>")


class FakeSMTP:
    """Sustituto de smtplib.SMTP / SMTP_SSL que registra las llamadas."""

    calls: list = []
    refused: dict = {}

    def __init__(self, host, port, timeout=None, context=None):
        FakeSMTP.calls.append(("connect", host, port, timeout, context))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        FakeSMTP.calls.append(("quit",))

    def starttls(self, context=None):
        FakeSMTP.calls.append(("starttls", context))

    def login(self, user, password):
        FakeSMTP.calls.append(("login", user, password))

    def send_message(self, message):
        FakeSMTP.calls.append(("send", message["To"]))
        return FakeSMTP.refused


@pytest.fixture()
def fake_smtp(monkeypatch, smtp_settings):
    FakeSMTP.calls, FakeSMTP.refused = [], {}
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


# --- Acceso -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("email", ["pmo@poc.local", "proveedor1@poc.local"])
def test_sin_acceso_para_pmo_ni_proveedor(client, email):
    login(client, email)
    token = csrf(client, "/")
    responses = [
        client.get(URL),
        client.post(URL, data={RECEPTION: "otro@ultrasist.com.mx", "config_version": "x", "csrf_token": token}),
        client.post(f"{URL}/test", data={"address": "otro@ultrasist.com.mx", "csrf_token": token}),
    ]
    assert [response.status_code for response in responses] == [403, 403, 403]
    assert configuration()[RECEPTION] == RECEPTION_SEED
    assert deliveries() == []


@pytest.mark.parametrize("token", [None, "token-invalido"])
def test_guardado_sin_token_csrf(client, token):
    login(client)
    data = form_data(client, **{RECEPTION: "otro@ultrasist.com.mx"})
    if token:
        data["csrf_token"] = token
    else:
        del data["csrf_token"]
    assert client.post(URL, data=data, follow_redirects=False).status_code == 403
    assert configuration()[RECEPTION] == RECEPTION_SEED


def test_opcion_en_el_menu(client):
    login(client)
    assert 'href="/admin/notifications"' in client.get("/").text
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    login(client, "pmo@poc.local")
    assert 'href="/admin/notifications"' not in client.get("/").text


# --- Buzon y copias -----------------------------------------------------------------------------------------------


def test_instalacion_nueva():
    lists = configuration()
    assert lists[RECEPTION] == RECEPTION_SEED
    assert [key for key in lists if key != RECEPTION] == [
        e.value for e in (AUTHORIZED, REJECTED, OBSERVATIONS, CANCELLED)
    ]
    assert all(addresses == [] for key, addresses in lists.items() if key != RECEPTION)


def test_cambio_del_buzon(client):
    login(client)
    response = save(client, **{RECEPTION: "facturas@ultrasist.com.mx\ncxp@ultrasist.com.mx"})
    assert response.status_code == 303 and response.headers["location"] == f"{URL}?ok=saved"
    assert "Configuración guardada" in client.get(response.headers["location"]).text
    assert configuration()[RECEPTION] == ["facturas@ultrasist.com.mx", "cxp@ultrasist.com.mx"]
    with SessionLocal() as db:
        mailbox = ns.load(db).mailbox
        assert mailbox.updated_by == admin().id


def test_buzon_vacio(client):
    login(client)
    response = save(client, **{RECEPTION: "  \n "})
    assert response.status_code == 400
    assert "Recepción de Facturas: indique al menos un correo" in response.text
    assert configuration()[RECEPTION] == RECEPTION_SEED


def test_copias_iniciales(client):
    login(client)
    page = client.get(URL).text
    rows = re.findall(r"<tr><td><strong>([^<]+)</strong></td><td>([^<]+)</td>", page)
    assert rows == [
        ("Autorizada", "Recepción de Facturas"),
        ("Rechazada", "Proveedor (correo del catálogo)"),
        ("Observaciones", "Proveedor (correo del catálogo)"),
        ("Cancelada", "Recepción de Facturas"),
    ]
    for event in (AUTHORIZED, REJECTED, OBSERVATIONS, CANCELLED):
        assert re.search(rf'name="{event}"[^>]*></textarea>', page)


def test_copia_agregada(client):
    login(client)
    assert save(client, **{REJECTED.value: "pmo@ultrasist.com.mx"}).status_code == 303
    lists = configuration()
    assert lists[REJECTED] == ["pmo@ultrasist.com.mx"]
    assert lists[AUTHORIZED] == lists[OBSERVATIONS] == lists[CANCELLED] == []
    assert lists[RECEPTION] == RECEPTION_SEED


# --- Validacion ---------------------------------------------------------------------------------------------------


def test_normalizacion(client):
    login(client)
    raw = " Facturas@Ultrasist.com.mx ; cxp@ultrasist.com.mx,facturas@ultrasist.com.mx "
    assert save(client, **{RECEPTION: raw}).status_code == 303
    assert configuration()[RECEPTION] == ["facturas@ultrasist.com.mx", "cxp@ultrasist.com.mx"]


def test_direccion_invalida(client):
    login(client)
    response = save(client, **{AUTHORIZED.value: "recepcion@"})
    assert response.status_code == 400
    assert "Copias de Autorizada: «recepcion@» no es un correo válido" in html.unescape(response.text)
    assert configuration()[AUTHORIZED] == []


def test_demasiadas_direcciones(client):
    login(client)
    many = "\n".join(f"buzon{i}@ultrasist.com.mx" for i in range(11))
    response = save(client, **{RECEPTION: many})
    assert response.status_code == 400
    assert "Recepción de Facturas: admite hasta 10 correos" in response.text
    assert configuration()[RECEPTION] == RECEPTION_SEED


def test_varios_errores_conservan_lo_capturado(client):
    login(client)
    response = save(client, **{RECEPTION: "", CANCELLED.value: "x@"})
    assert response.status_code == 400
    text = html.unescape(response.text)
    assert "Recepción de Facturas: indique al menos un correo" in text
    assert "Copias de Cancelada: «x@» no es un correo válido" in text
    assert re.search(rf'name="{CANCELLED}"[^>]*>x@</textarea>', text)
    assert configuration()[CANCELLED] == []


# --- Concurrencia -------------------------------------------------------------------------------------------------


def test_edicion_concurrente(client):
    login(client)
    stale = form_data(client)
    assert save(client, **{RECEPTION: "primero@ultrasist.com.mx"}).status_code == 303
    response = client.post(URL, data={**stale, RECEPTION: "segundo@ultrasist.com.mx"}, follow_redirects=False)
    assert response.status_code == 409
    assert "La configuración cambió mientras la editaba. Recargue la página." in response.text
    assert configuration()[RECEPTION] == ["primero@ultrasist.com.mx"]


def test_sin_cambios(client):
    login(client)
    before = audit_count()
    response = save(client)
    assert response.headers["location"] == f"{URL}?ok=unchanged"
    assert "Sin cambios" in client.get(response.headers["location"]).text
    assert audit_count() == before
    with SessionLocal() as db:
        assert ns.load(db).mailbox.updated_by is None


# --- Destinatarios ------------------------------------------------------------------------------------------------


def test_evento_dirigido_al_buzon():
    set_lists(
        INVOICE_RECEPTION=["facturas@ultrasist.com.mx", "cxp@ultrasist.com.mx"],
        INVOICE_AUTHORIZED=["cxp@ultrasist.com.mx", "pmo@ultrasist.com.mx"],
    )
    with SessionLocal() as db:
        recipients = ns.recipients_for(db, AUTHORIZED)
    assert recipients.to == ("facturas@ultrasist.com.mx", "cxp@ultrasist.com.mx")
    assert recipients.cc == ("pmo@ultrasist.com.mx",)


def test_evento_dirigido_al_proveedor():
    set_lists(INVOICE_REJECTED=["pmo@ultrasist.com.mx"])
    with SessionLocal() as db:
        recipients = ns.recipients_for(db, REJECTED, " Contacto@Proveedor.mx ")
    assert recipients.to == ("contacto@proveedor.mx",)
    assert recipients.cc == ("pmo@ultrasist.com.mx",)


@pytest.mark.parametrize("supplier_email", [None, "  "])
def test_proveedor_sin_correo(supplier_email):
    with pytest.raises(ns.NotificationDataError, match="correo del proveedor"):
        notify(OBSERVATIONS, supplier_email=supplier_email)
    assert deliveries() == []
    assert outbox_messages() == []


# --- Envio --------------------------------------------------------------------------------------------------------


def test_envio_al_buzon_con_el_transporte_de_archivo():
    delivery = notify(AUTHORIZED, entity="Invoice", entity_id=42)
    assert delivery.status == DeliveryStatus.SENT and delivery.transport == "file"
    [message] = outbox_messages()
    assert message["To"] == "recepcionfacturas@ultrasist.com.mx"
    assert message["Cc"] is None
    assert message["From"] == settings.mail_from
    assert message["Subject"] == "Factura A-1024 autorizada para pago"
    assert message["Auto-Submitted"] == "auto-generated"
    assert message["Message-ID"] == delivery.message_id and message["Date"]
    assert message.get_content_type() == "multipart/alternative"
    plain = message.get_body(("plain",))
    assert plain.get_content_charset() == "utf-8"
    body = plain.get_content()
    assert "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV" in body
    assert "$116,000.00 MXN" in body
    assert oct(next(OUTBOX.glob("*.eml")).stat().st_mode & 0o777) == "0o600"


def test_version_html_con_el_logo():
    notify(AUTHORIZED)
    [message] = outbox_messages()
    parts = [part.get_content_type() for part in message.walk()]
    assert parts == ["multipart/alternative", "text/plain", "multipart/related", "text/html", "image/png"]
    page = message.get_body(("html",))
    assert page.get_content_charset() == "utf-8"
    content = page.get_content()
    [logo] = [part for part in message.walk() if part.get_content_type() == "image/png"]
    assert f'src="cid:{logo["Content-ID"][1:-1]}"' in content and logo.get_content_disposition() == "inline"
    assert logo.get_content() == mail_layout.LOGO_PATH.read_bytes()
    assert ">Factura A-1024 autorizada para pago</h1>" in content
    assert "La factura número A-1024 del proveedor Servicios Digitales del Norte SA de CV" in content
    assert ">Folio interno</div>" in content and ">FAC-2026-00042</div>" in content


def test_version_html_escapa_los_valores():
    observaciones = '<b>Urgente</b> <img src="x" onerror="alert(1)">'
    notify(REJECTED, supplier_email="contacto@proveedor.mx", observaciones=observaciones)
    [message] = outbox_messages()
    assert observaciones in message.get_body(("plain",)).get_content()
    content = message.get_body(("html",)).get_content()
    assert "&lt;b&gt;Urgente&lt;/b&gt; &lt;img src=&#34;x&#34; onerror=&#34;alert(1)&#34;&gt;" in content
    assert "<b>" not in content and '<img src="x"' not in content


def test_version_html_enlaces_y_datos():
    body = (
        "Ingrese a https://portal.ultrasist.mx/login?a=1&b=2. Ignore javascript:alert(1).\n\n"
        "Nota: sin datos.\n\n"
        "Portal: http://127.0.0.1:8000/login\nUsuario: contacto@proveedor.mx"
    )
    first, note, fields = mail_layout.blocks(body)
    assert first.lines == [
        [
            mail_layout.Segment("Ingrese a "),
            mail_layout.Segment(
                "https://portal.ultrasist.mx/login?a=1&b=2", "https://portal.ultrasist.mx/login?a=1&b=2"
            ),
            mail_layout.Segment(". Ignore javascript:alert(1)."),
        ]
    ]
    assert note.fields is None and note.lines == [[mail_layout.Segment("Nota: sin datos.")]]
    assert [field.label for field in fields.fields] == ["Portal", "Usuario"]
    content = mail_layout.render_html("Asunto", body, "cid:logo@portal.local")
    assert '<a href="https://portal.ultrasist.mx/login?a=1&amp;b=2"' in content
    assert 'href="javascript' not in content


def test_copias_en_el_mensaje():
    set_lists(INVOICE_OBSERVATIONS=["pmo@ultrasist.com.mx", "calidad@ultrasist.com.mx"])
    delivery = notify(OBSERVATIONS, supplier_email="contacto@proveedor.mx")
    [message] = outbox_messages()
    assert message["To"] == "contacto@proveedor.mx"
    assert message["Cc"] == "pmo@ultrasist.com.mx, calidad@ultrasist.com.mx"
    assert delivery.cc_addresses == ["pmo@ultrasist.com.mx", "calidad@ultrasist.com.mx"]


def test_servidor_de_correo_caido(smtp_settings):
    delivery = notify(REJECTED, supplier_email="contacto@proveedor.mx")
    assert delivery.status == DeliveryStatus.FAILED and delivery.transport == "smtp"
    assert delivery.error.startswith("ConnectionRefusedError:") and len(delivery.error) <= 300
    [stored] = deliveries()
    assert stored.status == DeliveryStatus.FAILED and stored.error == delivery.error


def test_transporte_smtp_con_starttls(fake_smtp):
    notify(AUTHORIZED)
    kinds = [call[0] for call in fake_smtp.calls]
    assert kinds == ["connect", "starttls", "login", "send", "quit"]
    connect, starttls, login_call = fake_smtp.calls[:3]
    assert connect[1:4] == ("127.0.0.1", settings.smtp_port, 2)
    context = starttls[1]
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert login_call[1:] == ("usuario-smtp-secreto", "Clave#Smtp#Secreta")
    assert deliveries()[0].status == DeliveryStatus.SENT


def test_transporte_smtp_con_ssl_y_sin_usuario(fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_security", "ssl")
    monkeypatch.setattr(settings, "smtp_username", "")
    notify(AUTHORIZED)
    kinds = [call[0] for call in fake_smtp.calls]
    assert kinds == ["connect", "send", "quit"]
    assert isinstance(fake_smtp.calls[0][4], ssl.SSLContext)


def test_destinatario_rechazado(fake_smtp):
    fake_smtp.refused = {"contacto@proveedor.mx": (550, b"Mailbox unavailable")}
    delivery = notify(REJECTED, supplier_email="contacto@proveedor.mx")
    assert delivery.status == DeliveryStatus.FAILED
    assert delivery.error.startswith("SMTPRecipientsRefused:")


# --- Bitacora -----------------------------------------------------------------------------------------------------


def test_envio_registrado_sin_contenido():
    delivery = notify(
        REJECTED, supplier_email="contacto@proveedor.mx", entity="Invoice", entity_id=7, user_id=admin().id
    )
    [stored] = deliveries()
    assert (stored.event, stored.entity, stored.entity_id, stored.requested_by) == (
        REJECTED,
        "Invoice",
        "7",
        admin().id,
    )
    assert stored.to_addresses == ["contacto@proveedor.mx"] and stored.id == delivery.id
    [message] = outbox_messages()
    columns = [str(getattr(stored, column.key)) for column in EmailDelivery.__table__.columns]
    for text in (message["Subject"], VALUES["observaciones"], "por la siguiente causa"):
        assert all(text not in value for value in columns), text


def test_envios_en_la_pantalla(client):
    # Bitacora completa y paginada de 25 en 25, del mas reciente al mas antiguo (listados-paginados).
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    with SessionLocal() as db:
        for number in range(30):
            db.add(
                EmailDelivery(
                    event=AUTHORIZED,
                    status=DeliveryStatus.SENT,
                    to_addresses=[f"envio{number:02d}@ultrasist.com.mx"],
                    cc_addresses=[],
                    transport="file",
                    message_id=f"<{number}@portal.local>",
                    created_at=start + timedelta(minutes=number),
                )
            )
        db.commit()
    login(client)
    shown = re.findall(r"envio(\d\d)@ultrasist\.com\.mx", client.get(URL).text)
    assert shown == [f"{number:02d}" for number in range(29, 4, -1)]
    older = re.findall(r"envio(\d\d)@ultrasist\.com\.mx", client.get(URL, params={"page": 2}).text)
    assert older == ["04", "03", "02", "01", "00"]


# --- Correo de prueba ---------------------------------------------------------------------------------------------


def test_prueba_exitosa(client):
    login(client)
    response = send_test(client, "Admin@Ultrasist.com.mx")
    [delivery] = deliveries()
    assert response.status_code == 303 and response.headers["location"] == f"{URL}?test={delivery.id}"
    assert "Correo de prueba enviado a admin@ultrasist.com.mx" in client.get(response.headers["location"]).text
    assert (delivery.event, delivery.status, delivery.requested_by) == (None, DeliveryStatus.SENT, admin().id)
    [message] = outbox_messages()
    assert message["To"] == "admin@ultrasist.com.mx"
    assert message["Subject"] == "Correo de prueba del Portal de Proveedores ULTRASIST"
    assert admin().name in message.get_body(("plain",)).get_content()


def test_prueba_fallida(client, smtp_settings):
    login(client)
    response = send_test(client, "admin@ultrasist.com.mx")
    page = client.get(response.headers["location"]).text
    assert "No se pudo enviar el correo de prueba" in page and "ConnectionRefusedError" in page
    assert [d.status for d in deliveries()] == [DeliveryStatus.FAILED]


@pytest.mark.parametrize(
    ("address", "message"),
    [
        ("admin@", "Correo de prueba: «admin@» no es un correo válido"),
        ("", "Correo de prueba: indique al menos un correo"),
        ("a@ultrasist.com.mx, b@ultrasist.com.mx", "Correo de prueba: indique un solo correo"),
    ],
)
def test_direccion_de_prueba_invalida(client, address, message):
    login(client)
    response = send_test(client, address)
    assert response.status_code == 400
    assert message in html.unescape(response.text)
    assert deliveries() == [] and outbox_messages() == []


def test_resultado_de_prueba_solo_de_correos_de_prueba(client):
    delivery = notify(AUTHORIZED)
    login(client)
    page = client.get(f"{URL}?test={delivery.id}").text
    assert "Correo de prueba enviado" not in page and "No se pudo enviar el correo de prueba" not in page
    assert client.get(f"{URL}?test=999999").status_code == 200


# --- Transporte y auditoria ---------------------------------------------------------------------------------------


def test_transporte_de_archivo_en_solo_lectura(client):
    login(client)
    page = client.get(URL).text
    assert "Archivo (no se envían correos)" in page and html.escape(settings.mail_from) in page


def test_transporte_smtp_sin_credenciales_en_la_pagina(client, smtp_settings):
    login(client)
    page = client.get(URL).text
    assert f"127.0.0.1:{settings.smtp_port}" in page and "STARTTLS" in page
    assert "usuario-smtp-secreto" not in page and "Clave#Smtp#Secreta" not in page


def test_auditoria_de_un_cambio(client):
    login(client)
    assert save(client, **{CANCELLED.value: "cxp@ultrasist.com.mx"}).status_code == 303
    with SessionLocal() as db:
        entry = db.scalar(
            select(AuditLog).where(AuditLog.action == "NOTIFICATION_RECIPIENTS_UPDATED").order_by(AuditLog.id.desc())
        )
    assert (entry.entity, entry.user_id) == ("NotificationRecipients", admin().id)
    assert entry.old_value == {"INVOICE_CANCELLED": []}
    assert entry.new_value == {"INVOICE_CANCELLED": ["cxp@ultrasist.com.mx"]}


def test_acciones_sin_auditoria(client):
    login(client)
    before = audit_count()
    stale = form_data(client)
    assert save(client, **{RECEPTION: ""}).status_code == 400
    assert save(client).status_code == 303  # sin cambios
    assert send_test(client, "admin@ultrasist.com.mx").status_code == 303
    set_lists(INVOICE_REJECTED=["otro@ultrasist.com.mx"])  # cambio fuera de la pantalla: la huella vieja caduca
    assert client.post(URL, data=stale, follow_redirects=False).status_code == 409
    assert audit_count() == before
