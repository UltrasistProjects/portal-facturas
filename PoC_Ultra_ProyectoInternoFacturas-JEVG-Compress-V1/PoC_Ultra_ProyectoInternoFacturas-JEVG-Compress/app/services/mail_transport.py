"""Transporte de correo (HU-08): arma el mensaje y lo entrega por SMTP, o lo escribe como archivo .eml sin enviarlo.

Solo usa la biblioteca estandar (D1). Este modulo no registra nada en el log: notification_service decide que se
registra y nunca incluye destinatarios, asunto ni cuerpo.
"""

import os
import smtplib
import ssl
from collections.abc import Sequence
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from app.core.config import settings
from app.services import mail_layout

# Errores de entrega que se registran como envio fallido en lugar de propagarse (D5). ssl.SSLError y los de red
# (ConnectionRefusedError, TimeoutError, socket.gaierror) derivan de OSError.
TRANSPORT_ERRORS = (smtplib.SMTPException, OSError)
FALLBACK_DOMAIN = "portal.local"


def build_message(sender: str, to: Sequence[str], cc: Sequence[str], subject: str, body: str) -> EmailMessage:
    """Mensaje multipart/alternative UTF-8: el texto plano y su version HTML (mail_layout), con el logo como parte
    relacionada del HTML. Un cliente sin HTML muestra el texto plano. EmailMessage rechaza saltos de linea en las
    cabeceras."""
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    message["Date"] = formatdate(usegmt=True)
    domain = parseaddr(sender)[1].rpartition("@")[2] or FALLBACK_DOMAIN
    message["Message-ID"] = make_msgid(domain=domain)
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(body, charset="utf-8")
    logo_cid = make_msgid(domain=domain)
    message.add_alternative(
        mail_layout.render_html(subject, body, f"cid:{logo_cid[1:-1]}"), subtype="html", charset="utf-8"
    )
    html_part = message.get_payload()[1]
    html_part.add_related(mail_layout.logo(), maintype="image", subtype="png", cid=logo_cid)
    return message


class Transport(Protocol):
    name: str

    def send(self, message: EmailMessage) -> None: ...


class SmtpTransport:
    name = "smtp"

    def __init__(self, host: str, port: int, security: str, username: str, password: str, timeout: int):
        self.host = host
        self.port = port
        self.security = security
        self.username = username
        self.password = password
        self.timeout = timeout

    def send(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()  # verifica el certificado y el nombre del servidor
        if self.security == "ssl":
            client = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=context)
        else:
            client = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        with client:
            if self.security == "starttls":
                client.starttls(context=context)
            if self.username:
                client.login(self.username, self.password)
            refused = client.send_message(message)
        if refused:  # el servidor acepto a unos destinatarios y rechazo a otros
            raise smtplib.SMTPRecipientsRefused(refused)


class FileTransport:
    """Escribe cada correo en el buzon de salida con permisos 0600. No envia nada: desarrollo y pruebas."""

    name = "file"

    def __init__(self, outbox: Path):
        self.outbox = outbox

    def send(self, message: EmailMessage) -> None:
        self.outbox.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = self.outbox / f"{stamp}_{uuid4().hex}.eml"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(message.as_bytes())


def transport_from_settings() -> Transport:
    if settings.mail_backend == "smtp":
        return SmtpTransport(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_security,
            settings.smtp_username,
            settings.smtp_password.get_secret_value(),
            settings.smtp_timeout,
        )
    return FileTransport(settings.mail_outbox_dir)
