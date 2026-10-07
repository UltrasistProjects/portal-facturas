"""Plantillas de correo de los eventos de estatus de factura (HU-05) y de las credenciales del proveedor (HU-03).

Catalogo de eventos y variables, textos predeterminados, validacion, vista previa, guardado con bloqueo optimista y
composicion del correo para las HU que envian notificaciones (HU-20, HU-14, HU-03 y HU Complemento de Pagos). El
texto del Administrador nunca pasa por Jinja2: una expresion regular sustituye cada {{variable}} por su valor en una
sola pasada (D2). Este modulo no envia correos ni registra en el log el texto de las plantillas o los valores de las
variables.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.core.constants import NotificationEvent
from app.core.errors import BusinessRuleError, InvalidInputError, NotFoundError
from app.core.timeutils import to_business
from app.models import NotificationTemplate, User, now_utc
from app.services.audit_service import audit

logger = logging.getLogger(__name__)

SUBJECT_MAX_LENGTH = 200
BODY_MAX_LENGTH = 5000
COMPOSED_SUBJECT_MAX_LENGTH = 255
DATE_FORMAT = "%d/%m/%Y %H:%M"
# Una variable ocupa una sola linea: sin DOTALL, "." no cruza saltos de linea.
VARIABLE_PATTERN = re.compile(r"\{\{(.*?)\}\}")
LINE_BREAK = re.compile(r"\r\n|[\r\n]")
CONCURRENT_EDIT_MESSAGE = (
    "Otro administrador modificó esta plantilla mientras usted la editaba. "
    "Revise la versión vigente y vuelva a aplicar sus cambios."
)
AUDIT_ACTION = "NOTIFICATION_TEMPLATE_UPDATED"


# Valor de {{aviso_complemento}} en una factura que requiere Complemento de Pago (HU Complemento de Pagos).
COMPLEMENT_NOTICE = (
    "Es importante que adjunte su “Complemento de Pago” a dicha factura pagada antes del {fecha}. "
    "Mientras no lo adjunte, el portal no le permitirá enviar nuevas facturas a validación."
)


@dataclass(frozen=True)
class Variable:
    name: str
    description: str
    example: str


# Orden de la HU (seccion 6.2): es el de la tabla de variables y el del mensaje "Variables disponibles".
VARIABLES = {
    variable.name: variable
    for variable in (
        Variable("numero_factura", "Número de la factura que capturó el proveedor", "A-1024"),
        Variable("folio_interno", "Folio interno del portal", "FAC-2026-00042"),
        Variable("proveedor", "Razón social del proveedor", "Servicios Digitales del Norte SA de CV"),
        Variable("monto", "Total de la factura con su moneda", "$116,000.00 MXN"),
        Variable("estatus", "Nombre del evento", ""),  # el ejemplo es el nombre del evento que se edita
        Variable("fecha_estatus", "Fecha y hora del cambio de estatus, en la zona de negocio", "25/09/2026 10:30"),
        Variable(
            "observaciones",
            "Causa que capturó el PMO",
            "El subtotal del XML no coincide con el de la orden de compra.",
        ),
        Variable(
            "fecha_limite_cancelacion",
            "Fecha límite para aceptar la cancelación: fecha de la solicitud + 72 horas",
            "28/09/2026 10:30",
        ),
        Variable(
            "aviso_complemento",
            "Aviso del Complemento de Pago con su fecha límite; sólo aparece en las facturas nacionales con método "
            "de pago PPD",
            COMPLEMENT_NOTICE.format(fecha="28/09/2026 10:30"),
        ),
        # Credenciales de acceso (HU-03). El ejemplo de la contrasena es ficticio: nunca se leen datos reales.
        Variable("usuario", "Correo con el que el proveedor inicia sesión", "contacto@serviciosdelnorte.mx"),
        Variable("contrasena_temporal", "Contraseña temporal generada al autorizar", "Ejemplo#Temporal2026"),
        Variable(
            "url_portal", "Dirección de inicio de sesión del portal", "https://proveedores.ultrasist.com.mx/login"
        ),
    )
}
COMMON_VARIABLES = {"numero_factura", "folio_interno", "proveedor", "monto", "estatus", "fecha_estatus"}
# Variables que el sistema solo llena cuando aplican: obligatorias en el cuerpo (el Administrador no puede quitar el
# aviso), pero pueden llegar vacias al componer. Vacias, la linea que solo las contenia desaparece (D7).
CONDITIONAL_VARIABLES = {"aviso_complemento"}


def tag(name: str) -> str:
    return "{{" + name + "}}"


class Recipient(StrEnum):
    """Destinatario principal de un evento, fijado por su regla de negocio (RD-03). El valor es el texto de la
    pantalla; las direcciones las resuelve notification_service con la configuracion de HU-08."""

    RECEPTION = "Recepción de Facturas"
    SUPPLIER = "Proveedor (correo del catálogo)"


@dataclass(frozen=True)
class EventSpec:
    """Lo que el Administrador no puede cambiar de una plantilla: nombre, destinatario (RD-03), variables disponibles
    y obligatorias (RD-04) y texto predeterminado (RD-08). `supplier_copy`: el correo dirigido a Recepcion de Facturas
    va tambien con copia al proveedor de la factura."""

    event: NotificationEvent
    label: str
    recipient: Recipient
    variables: tuple[str, ...]
    required: tuple[str, ...]
    default_subject: str
    default_body: str
    supplier_copy: bool = False

    @property
    def recipient_label(self) -> str:
        """Destinatario que muestran las pantallas de plantillas y de notificaciones."""
        return f"{self.recipient} con copia al proveedor" if self.supplier_copy else self.recipient

    def example(self, name: str) -> str:
        return self.label if name == "estatus" else VARIABLES[name].example

    def variable_rows(self) -> list[dict]:
        return [
            {
                "tag": tag(name),
                "description": VARIABLES[name].description,
                "example": self.example(name),
                "required": name in self.required,
            }
            for name in self.variables
        ]


def _variables(*extra: str) -> tuple[str, ...]:
    return tuple(name for name in VARIABLES if name in COMMON_VARIABLES or name in extra)


RECEPTION = Recipient.RECEPTION
SUPPLIER = Recipient.SUPPLIER
RECEPTION_FOOTER = "Este es un mensaje automático del Portal de Proveedores ULTRASIST. No responda a este correo."
SUPPLIER_FOOTER = (
    "Puede consultar el detalle en el Portal de Proveedores ULTRASIST. "
    "Este es un mensaje automático; no responda a este correo."
)
SUPPLIER_DETAILS = (
    "{{observaciones}}\n\nFolio interno: {{folio_interno}}\nFecha: {{fecha_estatus}}\n\n" + SUPPLIER_FOOTER
)

# Textos predeterminados (HU, seccion 6.4). Las migraciones 0004, 0006 (credenciales, HU-03) y 0018 (pago y
# complemento) los copian; una prueba verifica que coinciden. El orden es el del listado de plantillas.
EVENTS: dict[NotificationEvent, EventSpec] = {
    spec.event: spec
    for spec in (
        EventSpec(
            NotificationEvent.INVOICE_AUTHORIZED,
            "Autorizada",
            RECEPTION,
            _variables(),
            ("numero_factura", "proveedor", "monto"),
            "Factura {{numero_factura}} autorizada para pago",
            "Recepción de Facturas:\n\n"
            "La factura número {{numero_factura}} del proveedor {{proveedor}} por el monto {{monto}} "
            "ha sido Autorizada para su pago.\n\n"
            "Folio interno: {{folio_interno}}\n"
            "Fecha de autorización: {{fecha_estatus}}\n\n" + RECEPTION_FOOTER,
            supplier_copy=True,
        ),
        EventSpec(
            NotificationEvent.INVOICE_REJECTED,
            "Rechazada",
            SUPPLIER,
            _variables("observaciones"),
            ("numero_factura", "observaciones"),
            "Factura {{numero_factura}} rechazada",
            "{{proveedor}}:\n\n"
            "La factura número {{numero_factura}} ha sido “Rechazada” por la siguiente causa:\n\n" + SUPPLIER_DETAILS,
        ),
        EventSpec(
            NotificationEvent.INVOICE_OBSERVATIONS,
            "Observaciones",
            SUPPLIER,
            _variables("observaciones"),
            ("numero_factura", "observaciones"),
            "Factura {{numero_factura}} con observaciones",
            "{{proveedor}}:\n\n"
            "La factura número {{numero_factura}} tiene “Observaciones” por la siguiente causa:\n\n" + SUPPLIER_DETAILS,
        ),
        EventSpec(
            NotificationEvent.INVOICE_CANCELLED,
            "Cancelada",
            RECEPTION,
            _variables("fecha_limite_cancelacion"),
            ("numero_factura", "proveedor", "fecha_limite_cancelacion"),
            "Cancelación de la factura {{numero_factura}} de {{proveedor}}",
            "Recepción de Facturas:\n\n"
            "La factura número {{numero_factura}} del proveedor {{proveedor}} ha sido cancelada. "
            "Por favor acepte la “Cancelación” antes del {{fecha_limite_cancelacion}}.\n\n"
            "Folio interno: {{folio_interno}}\n"
            "Monto: {{monto}}\n"
            "Fecha de la solicitud: {{fecha_estatus}}\n\n" + RECEPTION_FOOTER,
        ),
        EventSpec(
            NotificationEvent.INVOICE_PAID,
            "Pagada",
            SUPPLIER,
            _variables("aviso_complemento"),
            ("numero_factura", "aviso_complemento"),
            "Factura {{numero_factura}} pagada",
            "{{proveedor}}:\n\n"
            "Su factura número {{numero_factura}} ha sido pagada.\n\n"
            "{{aviso_complemento}}\n\n"
            "Folio interno: {{folio_interno}}\n"
            "Monto: {{monto}}\n"
            "Fecha de pago: {{fecha_estatus}}\n\n" + SUPPLIER_FOOTER,
        ),
        EventSpec(
            NotificationEvent.PAYMENT_COMPLEMENT,
            "Complemento de pago adjuntado",
            RECEPTION,
            _variables(),
            ("numero_factura", "proveedor"),
            "Complemento de pago de la factura {{numero_factura}}",
            "Recepción de Facturas:\n\n"
            "El Complemento de Pago ha sido adjuntado a la factura {{numero_factura}} del proveedor {{proveedor}}.\n\n"
            "Folio interno: {{folio_interno}}\n"
            "Monto: {{monto}}\n"
            "Fecha de carga: {{fecha_estatus}}\n\n" + RECEPTION_FOOTER,
        ),
        EventSpec(
            NotificationEvent.SUPPLIER_CREDENTIALS,
            "Credenciales de acceso",
            SUPPLIER,
            ("proveedor", "usuario", "contrasena_temporal", "url_portal"),
            ("usuario", "contrasena_temporal", "url_portal"),
            "Acceso al Portal de Proveedores ULTRASIST",
            "{{proveedor}}:\n\n"
            "Su registro como proveedor de ULTRASIST fue autorizado. Estos son sus datos para ingresar por primera vez "
            "al Portal de Proveedores:\n\n"
            "Portal: {{url_portal}}\n"
            "Usuario: {{usuario}}\n"
            "Contraseña temporal: {{contrasena_temporal}}\n\n"
            "Por seguridad, no comparta esta contraseña y cámbiela al ingresar por primera vez.\n\n"
            "Este es un mensaje automático del Portal de Proveedores ULTRASIST. No responda a este correo.",
        ),
    )
}


def spec_for_code(code: str) -> EventSpec:
    """Evento de la ruta; un codigo fuera del catalogo es un 404 (no un 422 de FastAPI)."""
    try:
        return EVENTS[NotificationEvent(code)]
    except ValueError:
        raise NotFoundError("La plantilla de correo no existe.") from None


# --- Validacion -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Draft:
    """Texto normalizado de una plantilla y sus errores de validacion ("Campo: mensaje")."""

    subject: str
    body: str
    errors: list[str]


def normalize(text: str) -> str:
    return LINE_BREAK.sub("\n", text).strip()


def _check_text(label: str, text: str, max_length: int, spec: EventSpec, errors: list[str]) -> set[str]:
    """Reglas comunes al asunto y al cuerpo. Devuelve los nombres de las variables que usa el texto."""
    if not text:
        errors.append(f"{label}: es obligatorio")
        return set()
    if len(text) > max_length:
        errors.append(f"{label}: admite hasta {max_length} caracteres")
    if "{{" in VARIABLE_PATTERN.sub("", text):
        errors.append(f"{label}: hay una variable sin cerrar; falta }}}}")
    names = [match.group(1).strip() for match in VARIABLE_PATTERN.finditer(text)]
    available = ", ".join(tag(name) for name in spec.variables)
    for name in dict.fromkeys(names):
        if name not in spec.variables:
            errors.append(
                f"{label}: la variable {tag(name)} no existe en esta plantilla. Variables disponibles: {available}"
            )
    return set(names)


def check_draft(spec: EventSpec, subject: str, body: str) -> Draft:
    """Normaliza (extremos y CRLF) y valida con todas las reglas; reporta todos los errores juntos."""
    subject, body = normalize(subject), normalize(body)
    errors: list[str] = []
    _check_text("Asunto", subject, SUBJECT_MAX_LENGTH, spec, errors)
    if "\n" in subject:
        errors.append("Asunto: debe ocupar una sola línea")
    used = _check_text("Cuerpo", body, BODY_MAX_LENGTH, spec, errors)
    if body:
        errors.extend(
            f"Cuerpo: debe incluir la variable obligatoria {tag(name)}" for name in spec.required if name not in used
        )
    return Draft(subject, body, errors)


# --- Composicion -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ComposedEmail:
    subject: str
    body: str


class NotificationDataError(ValueError):
    """La HU que compone el correo no entrego un valor que el evento necesita. Es un error de programacion."""


def render(text: str, values: dict[str, str]) -> str:
    """Sustitucion literal en una sola pasada: un valor que contiene {{...}} no se vuelve a sustituir."""
    return VARIABLE_PATTERN.sub(lambda match: values[match.group(1).strip()], text)


BLANK_LINES = re.compile(r"\n{3,}")


def _drop_empty_conditionals(body: str, values: dict[str, str]) -> str:
    """Quita las lineas que solo contienen una variable condicional vacia y reduce a una las lineas en blanco
    consecutivas que resulten. Sin variables condicionales vacias, el cuerpo no cambia."""
    empty = {name for name in CONDITIONAL_VARIABLES if name in values and not values[name].strip()}
    if not empty:
        return body
    kept = [
        line
        for line in body.split("\n")
        if not ((match := VARIABLE_PATTERN.fullmatch(line.strip())) is not None and match.group(1).strip() in empty)
    ]
    return BLANK_LINES.sub("\n\n", "\n".join(kept))


def _compose_text(subject: str, body: str, values: dict[str, str]) -> ComposedEmail:
    single_line = LINE_BREAK.sub(" ", render(subject, values))
    return ComposedEmail(
        single_line[:COMPOSED_SUBJECT_MAX_LENGTH], render(_drop_empty_conditionals(body, values), values)
    )


def sample_values(spec: EventSpec) -> dict[str, str]:
    """Datos ficticios fijos de la vista previa: nunca se leen facturas reales."""
    return {name: spec.example(name) for name in spec.variables}


def compose_sample(spec: EventSpec, draft: Draft) -> ComposedEmail:
    return _compose_text(draft.subject, draft.body, sample_values(spec))


def format_amount(amount: Decimal, currency: str) -> str:
    return f"${amount:,.2f} {currency}"


def format_datetime(value: datetime) -> str:
    return to_business(value).strftime(DATE_FORMAT)


def _current_text(db: Session, spec: EventSpec) -> tuple[str, str]:
    """Texto vigente; si falta o no es valido (p. ej. modificado por SQL), el predeterminado (RD-10, D8)."""
    template = db.scalar(select(NotificationTemplate).where(NotificationTemplate.event == spec.event))
    if template is None:
        reason, errors = "missing", 0
    else:
        draft = check_draft(spec, template.subject, template.body)
        if not draft.errors:
            return draft.subject, draft.body
        # Los mensajes de validacion no se registran: citan fragmentos del texto de la plantilla.
        reason, errors = "invalid", len(draft.errors)
    logger.warning(
        "notification.template_fallback",
        extra={
            "event": "notification.template_fallback",
            "event_code": spec.event.value,
            "reason": reason,
            "errors": errors,
        },
    )
    return spec.default_subject, spec.default_body


def compose(
    db: Session,
    event: NotificationEvent,
    *,
    numero_factura: str | None = None,
    folio_interno: str | None = None,
    proveedor: str | None = None,
    monto: Decimal | None = None,
    moneda: str | None = None,
    fecha_estatus: datetime | None = None,
    observaciones: str | None = None,
    fecha_limite_cancelacion: datetime | None = None,
    aviso_complemento: str | None = None,
    usuario: str | None = None,
    contrasena_temporal: str | None = None,
    url_portal: str | None = None,
) -> ComposedEmail:
    """Asunto y cuerpo del correo de `event` con la plantilla vigente (D10). Falla con NotificationDataError, sin
    componer nada, si falta el valor de una variable del evento o si una obligatoria llega vacia (salvo las
    condicionales, que pueden llegar vacias). Los valores de variables que el evento no admite se ignoran. No envia
    el correo."""
    spec = EVENTS[NotificationEvent(event)]
    provided = {
        "numero_factura": numero_factura,
        "folio_interno": folio_interno,
        "proveedor": proveedor,
        "monto": format_amount(monto, moneda) if monto is not None and moneda else None,
        "estatus": spec.label,
        "fecha_estatus": format_datetime(fecha_estatus) if fecha_estatus is not None else None,
        "observaciones": observaciones,
        "fecha_limite_cancelacion": (
            format_datetime(fecha_limite_cancelacion) if fecha_limite_cancelacion is not None else None
        ),
        "aviso_complemento": aviso_complemento,
        "usuario": usuario,
        "contrasena_temporal": contrasena_temporal,
        "url_portal": url_portal,
    }
    values: dict[str, str] = {}
    for name in spec.variables:
        value = provided[name]
        if value is None:
            raise NotificationDataError(f"Falta el valor de la variable {name} para el evento {spec.event.value}")
        if name in spec.required and name not in CONDITIONAL_VARIABLES and not value.strip():
            raise NotificationDataError(f"La variable obligatoria {name} llegó vacía para el evento {spec.event.value}")
        values[name] = value
    subject, body = _current_text(db, spec)
    return _compose_text(subject, body, values)


# --- Consulta y guardado ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TemplateRow:
    spec: EventSpec
    template: NotificationTemplate
    modified_at: str | None
    modified_by: str | None


def list_templates(db: Session) -> list[TemplateRow]:
    """Las plantillas en el orden del catalogo: Autorizada, Rechazada, Observaciones, Cancelada, Pagada, Complemento
    de pago adjuntado y Credenciales de acceso."""
    stmt = select(NotificationTemplate).options(joinedload(NotificationTemplate.updater))
    templates = {template.event: template for template in db.scalars(stmt)}
    rows = []
    for event, spec in EVENTS.items():
        template = templates.get(event)
        if template is None:
            continue
        modified = template.updater is not None
        rows.append(
            TemplateRow(
                spec,
                template,
                format_datetime(template.updated_at) if modified else None,
                template.updater.name if modified else None,
            )
        )
    return rows


def get_template(db: Session, spec: EventSpec) -> NotificationTemplate:
    template = db.scalar(select(NotificationTemplate).where(NotificationTemplate.event == spec.event))
    if template is None:
        raise NotFoundError("La plantilla de correo no existe.")
    return template


class TemplateValidationError(InvalidInputError):
    """El borrador no cumple las reglas de validacion (HTTP 400). Lleva el borrador normalizado y sus errores."""

    def __init__(self, draft: Draft):
        super().__init__("; ".join(draft.errors))
        self.draft = draft


class ConcurrentEditError(BusinessRuleError):
    """Otro Administrador guardo la plantilla despues de que se abrio el formulario (HTTP 409)."""

    def __init__(self):
        super().__init__(CONCURRENT_EDIT_MESSAGE)


@dataclass(frozen=True)
class SaveResult:
    changed: bool
    version: int


def save_template(db: Session, spec: EventSpec, subject: str, body: str, version: int, user: User) -> SaveResult:
    """Guarda el borrador si es valido y `version` es la vigente (D6). Sin cambios no escribe ni audita. Confirma la
    transaccion y, despues, registra el evento de log (D13)."""
    draft = check_draft(spec, subject, body)
    if draft.errors:
        raise TemplateValidationError(draft)
    current = get_template(db, spec)
    if version != current.version:
        raise ConcurrentEditError()
    if (draft.subject, draft.body) == (current.subject, current.body):
        return SaveResult(False, current.version)
    old = {"subject": current.subject, "body": current.body, "version": current.version}
    new_version = version + 1
    result = db.execute(
        update(NotificationTemplate)
        .where(NotificationTemplate.event == spec.event, NotificationTemplate.version == version)
        .values(
            subject=draft.subject,
            body=draft.body,
            version=new_version,
            updated_at=now_utc(),
            updated_by=user.id,
        )
    )
    if result.rowcount != 1:  # otro Administrador guardo entre la lectura y el UPDATE
        db.rollback()
        raise ConcurrentEditError()
    new = {"subject": draft.subject, "body": draft.body, "version": new_version}
    audit(db, AUDIT_ACTION, "NotificationTemplate", spec.event.value, user.id, old, new)
    db.commit()
    logger.info(
        "notification_template.updated",
        extra={"event": "notification_template.updated", "event_code": spec.event.value, "version": new_version},
    )
    return SaveResult(True, new_version)
