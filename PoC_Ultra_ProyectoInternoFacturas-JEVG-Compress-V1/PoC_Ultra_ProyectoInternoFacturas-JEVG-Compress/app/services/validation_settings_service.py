"""Reglas de Validacion (HU-06): datos de ULTRASIST y parametros del CFDI que compara el motor.

Una sola fila (validation_settings.id = 1), creada por la migracion. El motor la lee en cada prevalidacion con
`rule_parameters()`, sin cache (D3). El guardado sigue el patron de las plantillas de HU-05: todos los errores juntos
(400), UPDATE condicionado a la version (409), un guardado sin cambios no escribe ni audita, y el evento de log se
registra despues del commit sin los valores de los campos.
"""

import logging
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.constants import CatalogType, Severity
from app.core.errors import BusinessRuleError, InvalidInputError
from app.models import User, ValidationSettings, now_utc
from app.services import catalog_service
from app.services.audit_service import audit

logger = logging.getLogger(__name__)

SETTINGS_ID = 1
AUDIT_ACTION = "VALIDATION_SETTINGS_UPDATED"
ENTITY = "ValidationSettings"
RFC_MORAL = re.compile(r"^[A-ZÑ&]{3}[0-9]{6}[A-Z0-9]{3}$")
POSTAL_CODE = re.compile(r"^[0-9]{5}$")
SPACES = re.compile(r"\s+")
NAME_MAX_LENGTH = 254
ADDRESS_MAX_LENGTH = 300
CONCURRENT_EDIT_MESSAGE = (
    "Otro administrador modificó las Reglas de Validación mientras usted las editaba. Recargue la página."
)
INACTIVE_CODE = "la clave no está activa en el catálogo"


@dataclass(frozen=True)
class Check:
    """Comparacion activable: interruptor, regla XML, lo que compara y su severidad."""

    field: str
    rule_code: str
    label: str
    severity: Severity


# En el orden de la pantalla. La Direccion y el regimen no tienen interruptor: son datos de referencia (S3, S4).
CHECKS = (
    Check("check_receiver_rfc", "XML-002", "RFC del receptor", Severity.CRITICAL),
    Check("check_receiver_name", "XML-009", "Razón social del receptor", Severity.ERROR),
    Check("check_receiver_postal_code", "XML-010", "Código postal del receptor", Severity.ERROR),
    Check("check_payment_method", "XML-003", "Método de pago", Severity.ERROR),
    Check("check_payment_form", "XML-004", "Forma de pago", Severity.ERROR),
    Check("check_cfdi_use", "XML-005", "Uso de CFDI", Severity.ERROR),
)
CHECK_FIELDS = tuple(check.field for check in CHECKS)
LABELS = {
    "receiver_rfc": "RFC",
    "receiver_name": "Razón social",
    "receiver_address": "Dirección",
    "receiver_postal_code": "Código postal",
    "receiver_tax_regime": "Régimen fiscal",
    "payment_method": "Método de pago",
    "payment_form": "Forma de pago",
    "allowed_cfdi_uses": "Usos de CFDI",
}
# Campo -> catalogo cuyas claves activas acepta.
CATALOG_FIELDS = {
    "receiver_tax_regime": CatalogType.TAX_REGIME,
    "payment_method": CatalogType.PAYMENT_METHOD,
    "payment_form": CatalogType.PAYMENT_FORM,
}
FIELDS = (*LABELS, *CHECK_FIELDS)


# --- Lectura para el motor ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleParameters:
    """Configuracion vigente que aplican las reglas XML en una prevalidacion."""

    receiver_rfc: str
    receiver_name: str
    receiver_postal_code: str
    payment_method: str
    payment_form: str
    allowed_cfdi_uses: tuple[str, ...]
    currencies: frozenset[str]
    check_receiver_rfc: bool = True
    check_receiver_name: bool = True
    check_receiver_postal_code: bool = True
    check_payment_method: bool = True
    check_payment_form: bool = True
    check_cfdi_use: bool = True


def current(db: Session) -> ValidationSettings:
    return db.get(ValidationSettings, SETTINGS_ID)


def rule_parameters(db: Session) -> RuleParameters:
    settings = current(db)
    return RuleParameters(
        receiver_rfc=settings.receiver_rfc,
        receiver_name=settings.receiver_name,
        receiver_postal_code=settings.receiver_postal_code,
        payment_method=settings.payment_method,
        payment_form=settings.payment_form,
        allowed_cfdi_uses=tuple(settings.allowed_cfdi_uses),
        currencies=frozenset(catalog_service.active_codes(db, CatalogType.CURRENCY)),
        **{field: getattr(settings, field) for field in CHECK_FIELDS},
    )


def normalize_name(text: str | None) -> str:
    """Razon social comparable: sin acentos, sin distinguir mayusculas y con los espacios colapsados (S6)."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c))
    return SPACES.sub(" ", plain).strip().casefold()


# --- Validacion y guardado ----------------------------------------------------------------------------------------


def _valid_rfc(rfc: str) -> bool:
    if not RFC_MORAL.fullmatch(rfc):
        return False
    try:
        datetime.strptime(rfc[3:9], "%y%m%d")
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class Draft:
    values: dict
    errors: list[str]


def check_form(db: Session, form: Mapping) -> Draft:
    """Normaliza y valida el formulario; reporta todos los errores juntos ("Campo: mensaje")."""
    text = {name: SPACES.sub(" ", str(form.get(name) or "")).strip() for name in LABELS if name != "allowed_cfdi_uses"}
    text["receiver_address"] = str(form.get("receiver_address") or "").strip()
    text["receiver_rfc"] = text["receiver_rfc"].upper()
    uses = sorted({str(code).strip().upper() for code in form.get("allowed_cfdi_uses") or [] if str(code).strip()})
    errors = []
    if not _valid_rfc(text["receiver_rfc"]):
        errors.append("RFC: no es un RFC de persona moral válido")
    if not text["receiver_name"]:
        errors.append("Razón social: es obligatoria")
    elif len(text["receiver_name"]) > NAME_MAX_LENGTH:
        errors.append(f"Razón social: admite hasta {NAME_MAX_LENGTH} caracteres")
    if len(text["receiver_address"]) > ADDRESS_MAX_LENGTH:
        errors.append(f"Dirección: admite hasta {ADDRESS_MAX_LENGTH} caracteres")
    if not POSTAL_CODE.fullmatch(text["receiver_postal_code"]):
        errors.append("Código postal: debe tener 5 dígitos")
    for name, catalog in CATALOG_FIELDS.items():
        if text[name] not in catalog_service.active_codes(db, catalog):
            errors.append(f"{LABELS[name]}: {INACTIVE_CODE}")
    active_uses = catalog_service.active_codes(db, CatalogType.CFDI_USE)
    if not uses:
        errors.append("Usos de CFDI: seleccione al menos uno")
    errors.extend(
        f"Usos de CFDI: la clave {code} no está activa en el catálogo" for code in uses if code not in active_uses
    )
    values = {**text, "allowed_cfdi_uses": uses}
    values.update({field: form.get(field) in {"on", "true", "1"} for field in CHECK_FIELDS})
    return Draft(values, errors)


class SettingsValidationError(InvalidInputError):
    """El formulario no cumple las reglas (HTTP 400). Lleva el borrador normalizado y sus errores."""

    def __init__(self, draft: Draft):
        super().__init__("; ".join(draft.errors))
        self.draft = draft


class ConcurrentEditError(BusinessRuleError):
    """Otro Administrador guardo despues de que se abrio el formulario (HTTP 409)."""

    def __init__(self):
        super().__init__(CONCURRENT_EDIT_MESSAGE)


def save(db: Session, form: Mapping, version: int, user: User) -> bool:
    """Guarda la configuracion si es valida y `version` es la vigente. True si hubo cambios. Confirma la transaccion
    y despues registra el evento de log."""
    draft = check_form(db, form)
    if draft.errors:
        raise SettingsValidationError(draft)
    settings = current(db)
    if version != settings.version:
        raise ConcurrentEditError()
    changed = [name for name in FIELDS if getattr(settings, name) != draft.values[name]]
    if not changed:
        return False
    old = {name: getattr(settings, name) for name in changed} | {"version": settings.version}
    new = {name: draft.values[name] for name in changed} | {"version": version + 1}
    result = db.execute(
        update(ValidationSettings)
        .where(ValidationSettings.id == SETTINGS_ID, ValidationSettings.version == version)
        .values(
            **{name: draft.values[name] for name in changed},
            version=version + 1,
            updated_at=now_utc(),
            updated_by=user.id,
        )
    )
    if result.rowcount != 1:  # otro Administrador guardo entre la lectura y el UPDATE
        db.rollback()
        raise ConcurrentEditError()
    audit(db, AUDIT_ACTION, ENTITY, SETTINGS_ID, user.id, old, new)
    db.commit()
    logger.info(
        "validation_settings.updated",
        extra={"event": "validation_settings.updated", "fields": changed, "version": version + 1},
    )
    return True


def form_values(settings: ValidationSettings) -> dict:
    return {name: getattr(settings, name) for name in FIELDS}


def updater_name(db: Session, settings: ValidationSettings) -> str | None:
    return db.scalar(select(User.name).where(User.id == settings.updated_by)) if settings.updated_by else None
