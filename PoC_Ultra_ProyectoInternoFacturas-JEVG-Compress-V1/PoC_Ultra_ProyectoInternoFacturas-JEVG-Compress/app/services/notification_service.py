"""Destinatarios y envio de notificaciones por correo (HU-08).

- Configuracion: buzon Recepcion de Facturas y copias por evento, que el Administrador edita en una sola transaccion
  con bloqueo consultivo y huella `config_version`, como los archivos minimos de HU-04 (D3).
- Envio: `notify()` resuelve los destinatarios del evento, compone el correo con la plantilla vigente de HU-05, lo
  entrega y registra el resultado en la bitacora. Se llama despues de confirmar la transaccion de negocio y nunca
  propaga un error de transporte (D5).

Los eventos de log no llevan direcciones, asunto, cuerpo ni el mensaje del error (D10).
"""

import hashlib
import json
import logging
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import MAILBOX_LABELS, DeliveryStatus, Mailbox, NotificationEvent
from app.core.errors import BusinessRuleError, InvalidInputError
from app.models import EmailDelivery, NotificationCopy, NotificationMailbox, User, now_utc
from app.repositories.pagination import Page, paginate
from app.services import mail_transport
from app.services import notification_templates as nt
from app.services.audit_service import audit

logger = logging.getLogger(__name__)

# Clave del bloqueo consultivo que serializa las escrituras de la configuracion (pg_advisory_xact_lock).
CONFIG_LOCK_KEY = 8_0800_0001
MAX_ADDRESSES = 10
MAX_ADDRESS_LENGTH = 254
ERROR_MAX_LENGTH = 300
# Separadores de una lista capturada en un textarea: saltos de linea, comas y punto y coma.
SEPARATORS = re.compile(r"[\r\n,;]+")
EMAIL = TypeAdapter(EmailStr)
# Eventos que admiten copias, en el orden del catalogo de plantillas. Un evento cuyo correo lleve secretos (las
# credenciales de HU-03) no se agrega aqui (S6).
COPY_EVENTS = (
    NotificationEvent.INVOICE_AUTHORIZED,
    NotificationEvent.INVOICE_REJECTED,
    NotificationEvent.INVOICE_OBSERVATIONS,
    NotificationEvent.INVOICE_CANCELLED,
)

MSG_CHANGED = "La configuración cambió mientras la editaba. Recargue la página."
AUDIT_ACTION = "NOTIFICATION_RECIPIENTS_UPDATED"
ENTITY = "NotificationRecipients"
TEST_LABEL = "Correo de prueba"
TEST_SUBJECT = "Correo de prueba del Portal de Proveedores ULTRASIST"
TEST_BODY = (
    "Este es un correo de prueba enviado por {name} el {date} desde Administración › Notificaciones.\n\n"
    "Si lo recibió, el portal puede enviar correos con la configuración vigente.\n\n"
    "Este es un mensaje automático del Portal de Proveedores ULTRASIST. No responda a este correo."
)
SECURITY_LABELS = {"starttls": "STARTTLS", "ssl": "SSL/TLS", "none": "Sin cifrar"}


class NotificationDataError(nt.NotificationDataError):
    """La HU que envia no entrego un dato necesario para el correo. Es un error de programacion."""


class RecipientsValidationError(InvalidInputError):
    """Una o mas listas no cumplen las reglas (HTTP 400). Lleva todos los errores."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


# --- Configuracion ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RecipientList:
    """Una lista editable de la pantalla. `key` es el campo del formulario y la clave en la auditoria."""

    key: str
    label: str
    addresses: list[str]
    minimum: int
    event: NotificationEvent | None = None
    event_label: str | None = None
    primary: str | None = None  # destinatario principal del evento, solo lectura


@dataclass
class Configuration:
    mailbox: NotificationMailbox
    copies: dict[NotificationEvent, NotificationCopy] = field(default_factory=dict)


def load(db: Session) -> Configuration:
    mailbox = db.scalar(select(NotificationMailbox).where(NotificationMailbox.code == Mailbox.INVOICE_RECEPTION))
    copies = {copy.event: copy for copy in db.scalars(select(NotificationCopy))}
    return Configuration(mailbox, copies)


def recipient_lists(config: Configuration) -> list[RecipientList]:
    """El buzon y, despues, las copias de cada evento en el orden del catalogo."""
    mailbox = config.mailbox
    lists = [RecipientList(mailbox.code.value, MAILBOX_LABELS[mailbox.code], list(mailbox.addresses), 1)]
    for event in COPY_EVENTS:
        spec = nt.EVENTS[event]
        addresses = list(config.copies[event].addresses) if event in config.copies else []
        label = f"Copias de {spec.label}"
        lists.append(RecipientList(event.value, label, addresses, 0, event, spec.label, spec.recipient))
    return lists


def config_version(config: Configuration) -> str:
    """Huella de la configuracion mostrada: SHA-256 de todas las listas."""
    rows = sorted([item.key, item.addresses] for item in recipient_lists(config))
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def valid_address(address: str) -> bool:
    if len(address) > MAX_ADDRESS_LENGTH:
        return False
    try:
        EMAIL.validate_python(address)
    except ValidationError:
        return False
    return True


def parse_addresses(label: str, raw: str, minimum: int, maximum: int = MAX_ADDRESSES) -> tuple[list[str], list[str]]:
    """Normaliza una lista capturada (D8) y devuelve (direcciones, errores). Minusculas y sin repetidas, en el orden
    de su primera aparicion."""
    items = (item.strip().lower() for item in SEPARATORS.split(raw or ""))
    addresses = list(dict.fromkeys(item for item in items if item))
    errors = [f"{label}: «{address}» no es un correo válido" for address in addresses if not valid_address(address)]
    if len(addresses) < minimum:
        errors.append(f"{label}: indique al menos un correo")
    if len(addresses) > maximum:
        errors.append(f"{label}: admite hasta {maximum} correos")
    return addresses, errors


def _lock(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CONFIG_LOCK_KEY})


def save_recipients(db: Session, form: Mapping[str, str], user: User) -> bool:
    """Guarda el buzon y las copias en una sola transaccion. True si hubo cambios. Orden de las verificaciones:
    huella (409) y listas (400). Confirma la transaccion y, despues, registra el evento de log."""
    _lock(db)
    config = load(db)
    if form.get("config_version") != config_version(config):
        raise BusinessRuleError(MSG_CHANGED)
    received: dict[str, list[str]] = {}
    errors: list[str] = []
    for item in recipient_lists(config):
        addresses, list_errors = parse_addresses(item.label, form.get(item.key, ""), item.minimum)
        received[item.key] = addresses
        errors.extend(list_errors)
    if errors:
        raise RecipientsValidationError(errors)
    old: dict[str, list[str]] = {}
    new: dict[str, list[str]] = {}
    now = now_utc()
    for key, addresses in received.items():
        target = config.mailbox if key == config.mailbox.code.value else config.copies[NotificationEvent(key)]
        if list(target.addresses) != addresses:
            old[key], new[key] = list(target.addresses), addresses
            target.addresses = addresses
            target.updated_at = now
            target.updated_by = user.id
    if not new:
        return False
    audit(db, AUDIT_ACTION, ENTITY, None, user.id, old, new)
    db.commit()
    logger.info(
        "notification_recipients.updated", extra={"event": "notification_recipients.updated", "lists": list(new)}
    )
    return True


# --- Destinatarios y envio ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Recipients:
    to: tuple[str, ...]
    cc: tuple[str, ...] = ()


def recipients_for(db: Session, event: NotificationEvent, supplier_email: str | None = None) -> Recipients:
    """Destinatarios del correo de `event` (D4), leidos de la base de datos en cada envio."""
    spec = nt.EVENTS[NotificationEvent(event)]
    if spec.recipient == nt.Recipient.RECEPTION:
        to = tuple(load(db).mailbox.addresses)
    else:
        if not supplier_email or not supplier_email.strip():
            raise NotificationDataError(f"Falta el correo del proveedor para el evento {spec.event.value}")
        to = (supplier_email.strip().lower(),)
    copies = db.scalar(select(NotificationCopy.addresses).where(NotificationCopy.event == spec.event)) or []
    return Recipients(to, tuple(dict.fromkeys(address for address in copies if address not in to)))


def deliver(
    db: Session,
    event: NotificationEvent | None,
    recipients: Recipients,
    subject: str,
    body: str,
    *,
    entity: str | None = None,
    entity_id: int | str | None = None,
    user_id: int | None = None,
) -> EmailDelivery:
    """Entrega un correo ya compuesto y lo registra en la bitacora (confirma ese registro). Un error de transporte
    deja el envio como FAILED y no se propaga."""
    transport = mail_transport.transport_from_settings()
    message = mail_transport.build_message(settings.mail_from, recipients.to, recipients.cc, subject, body)
    started = time.perf_counter()
    error_type = error = None
    try:
        transport.send(message)
    except mail_transport.TRANSPORT_ERRORS as exc:
        error_type = type(exc).__name__
        error = f"{error_type}: {exc}"[:ERROR_MAX_LENGTH]
    duration_ms = round((time.perf_counter() - started) * 1000)
    delivery = EmailDelivery(
        event=event,
        status=DeliveryStatus.FAILED if error else DeliveryStatus.SENT,
        to_addresses=list(recipients.to),
        cc_addresses=list(recipients.cc),
        transport=transport.name,
        message_id=message["Message-ID"],
        error=error,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        requested_by=user_id,
    )
    db.add(delivery)
    db.commit()
    extra = {
        "event": "notification.failed" if error else "notification.sent",
        "delivery_id": delivery.id,
        "event_code": event.value if event else "TEST",
        "transport": transport.name,
        "recipients": len(recipients.to) + len(recipients.cc),
        "duration_ms": duration_ms,
    }
    if error:
        logger.warning("notification.failed", extra={**extra, "error_type": error_type})
    else:
        logger.info("notification.sent", extra=extra)
    return delivery


def notify(
    db: Session,
    event: NotificationEvent,
    *,
    supplier_email: str | None = None,
    entity: str | None = None,
    entity_id: int | str | None = None,
    user_id: int | None = None,
    **values,
) -> EmailDelivery:
    """Envia el correo de `event` con la plantilla vigente (HU-05) a sus destinatarios configurados. `values` son los
    de `notification_templates.compose()`. Llamar despues de confirmar la transaccion de negocio."""
    recipients = recipients_for(db, event, supplier_email)
    email = nt.compose(db, event, **values)
    return deliver(
        db, event, recipients, email.subject, email.body, entity=entity, entity_id=entity_id, user_id=user_id
    )


def send_test(db: Session, raw_address: str, user: User) -> EmailDelivery:
    """Correo de prueba de texto fijo (D9), registrado en la bitacora sin evento."""
    addresses, errors = parse_addresses(TEST_LABEL, raw_address, minimum=1)
    if len(addresses) > 1:
        errors = [f"{TEST_LABEL}: indique un solo correo"]
    if errors:
        raise RecipientsValidationError(errors)
    body = TEST_BODY.format(name=user.name, date=nt.format_datetime(now_utc()))
    return deliver(db, None, Recipients((addresses[0],)), TEST_SUBJECT, body, user_id=user.id)


# --- Consulta -----------------------------------------------------------------------------------------------------


def deliveries_page(db: Session, page: int = 1) -> Page[EmailDelivery]:
    """Bitacora de envios completa, del mas reciente al mas antiguo, paginada en SQL (listados-paginados)."""
    stmt = select(EmailDelivery).order_by(EmailDelivery.created_at.desc(), EmailDelivery.id.desc())
    return paginate(db, stmt, page)


def delivery_label(delivery: EmailDelivery) -> str:
    return nt.EVENTS[delivery.event].label if delivery.event else "Prueba"


def transport_summary() -> dict:
    """Datos del transporte para la pantalla, sin usuario ni contrasena SMTP."""
    if settings.mail_backend == "smtp":
        details = [
            ("Servidor", f"{settings.smtp_host}:{settings.smtp_port}"),
            ("Cifrado", SECURITY_LABELS[settings.smtp_security]),
            ("Autenticación", "Con usuario" if settings.smtp_username else "Sin autenticación"),
        ]
        return {"label": "SMTP", "details": details, "sender": settings.mail_from}
    details = [("Directorio de salida", str(settings.mail_outbox_dir))]
    return {"label": "Archivo (no se envían correos)", "details": details, "sender": settings.mail_from}
