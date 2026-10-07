"""Reglas de Validacion por origen de proveedor (ajustes-finales-configuracion).

Unico acceso al catalogo validation_rules: lo usan el motor (`rule_set`, una vez por prevalidacion y sin cache), las
pantallas "Reglas de validacion — Nacionales / Internacionales" y la proteccion de claves en uso de los catalogos.
Asi lo que el Administrador ve es exactamente lo que el motor aplica.

- Edicion del nombre y del valor esperado con la version que se abrio (409 si otro Administrador guardo antes).
- Eliminacion logica y restauracion; restaurar valida el valor esperado como la edicion.
- Todos los errores de validacion juntos (400), cada uno como "<Campo>: <mensaje>".

Ninguna funcion confirma la transaccion: lo hace el router.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import CatalogType, SupplierOrigin
from app.core.errors import BusinessRuleError, InvalidInputError, NotFoundError
from app.models import ValidationRule, now_utc
from app.rules.definitions import DEFINITIONS, ConfiguredRule, ParameterKind, RuleDefinition, RuleSet
from app.services import catalog_service
from app.services.audit_service import audit

ENTITY = "ValidationRule"
RFC_MORAL = re.compile(r"^[A-ZÑ&]{3}[0-9]{6}[A-Z0-9]{3}$")
POSTAL_CODE = re.compile(r"^[0-9]{5}$")
SPACES = re.compile(r"\s+")
NAME_LENGTH = (3, 80)
TEXT_MAX_LENGTH = {ParameterKind.TEXT: 254, ParameterKind.ADDRESS: 300}
MSG_NOT_FOUND = "Regla no encontrada"
MSG_CONCURRENT_EDIT = "Otro administrador modificó esta regla mientras usted la editaba. Recargue la página."
MSG_INACTIVE_CODE = "la clave no está activa en el catálogo"


# --- Lectura ------------------------------------------------------------------------------------------------------


def _rows(db: Session, origin: SupplierOrigin) -> list[ValidationRule]:
    stmt = select(ValidationRule).where(ValidationRule.origin == origin).order_by(ValidationRule.rule_code)
    return list(db.scalars(stmt))


def rule_set(db: Session, origin: SupplierOrigin) -> RuleSet:
    """Reglas del origen que aplica una prevalidacion: activas o no, con su valor esperado, y las monedas activas."""
    return RuleSet(
        rules={row.rule_code: ConfiguredRule(row.is_active, row.parameter) for row in _rows(db, origin)},
        currencies=frozenset(catalog_service.active_codes(db, CatalogType.CURRENCY)),
    )


@dataclass(frozen=True)
class RuleView:
    """Regla de la pantalla: su registro y su definicion (lo que compara, severidad y tipo del valor esperado)."""

    rule: ValidationRule
    definition: RuleDefinition

    @property
    def expected(self) -> str:
        parameter = self.rule.parameter
        if isinstance(parameter, list):
            return ", ".join(parameter)
        return parameter or "—"


def page_rules(db: Session, origin: SupplierOrigin) -> list[RuleView]:
    """Todas las reglas del origen, por codigo, con la misma lectura que usa el motor."""
    return [RuleView(row, DEFINITIONS[origin, row.rule_code]) for row in _rows(db, origin)]


# --- Validacion ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Draft:
    """Valores normalizados del formulario de una regla y sus errores."""

    name: str
    parameter: Any
    errors: list[str]


class RuleValidationError(InvalidInputError):
    """El nombre o el valor esperado no son validos (HTTP 400). Lleva el borrador para volver a pintar el formulario."""

    def __init__(self, rule: ValidationRule, draft: Draft):
        super().__init__("; ".join(draft.errors))
        self.rule = rule
        self.draft = draft


def _valid_rfc(rfc: str) -> bool:
    if not RFC_MORAL.fullmatch(rfc):
        return False
    try:
        datetime.strptime(rfc[3:9], "%y%m%d")
    except ValueError:
        return False
    return True


def _check_parameter(db: Session, definition: RuleDefinition, raw: str | Sequence[str] | None) -> tuple[Any, list[str]]:
    kind, label = definition.kind, definition.label
    if kind == ParameterKind.NONE:
        return None, []
    if kind == ParameterKind.CATALOG_CODES:
        values = [raw] if isinstance(raw, str) else list(raw or [])
        codes = sorted({str(code).strip().upper() for code in values if str(code).strip()})
        if not codes:
            return codes, [f"{label}: seleccione al menos uno"]
        active = catalog_service.active_codes(db, definition.catalog)
        return codes, [
            f"{label}: la clave {code} no está activa en el catálogo" for code in codes if code not in active
        ]
    # El formulario envia una lista: un valor esperado de texto es su primer elemento.
    text = str((raw[0] if raw else "") if isinstance(raw, list) else (raw or ""))
    # La direccion conserva sus saltos de linea; los demas textos colapsan los espacios internos.
    value = text.strip() if kind == ParameterKind.ADDRESS else SPACES.sub(" ", text).strip()
    if kind == ParameterKind.RFC:
        value = value.upper()
        return value, [] if _valid_rfc(value) else [f"{label}: no es un RFC de persona moral válido"]
    if kind == ParameterKind.POSTAL_CODE:
        return value, [] if POSTAL_CODE.fullmatch(value) else [f"{label}: debe tener 5 dígitos"]
    if kind == ParameterKind.CATALOG_CODE:
        value = value.upper()
        active = catalog_service.active_codes(db, definition.catalog)
        return value, [] if value in active else [f"{label}: {MSG_INACTIVE_CODE}"]
    if not value:
        return value, [f"{label}: es obligatoria"]
    limit = TEXT_MAX_LENGTH[kind]
    return value, [] if len(value) <= limit else [f"{label}: admite hasta {limit} caracteres"]


def check_values(db: Session, definition: RuleDefinition, raw_name: str, raw_parameter) -> Draft:
    name = SPACES.sub(" ", raw_name or "").strip()
    errors = []
    low, high = NAME_LENGTH
    if not low <= len(name) <= high:
        errors.append(f"Nombre: debe tener de {low} a {high} caracteres")
    parameter, parameter_errors = _check_parameter(db, definition, raw_parameter)
    return Draft(name, parameter, errors + parameter_errors)


# --- Escritura ----------------------------------------------------------------------------------------------------


def get_rule(db: Session, origin: SupplierOrigin, rule_id: int, *, lock: bool = False) -> ValidationRule:
    """Regla de ese origen; 404 si no existe o es del otro origen."""
    rule = db.get(ValidationRule, rule_id, with_for_update=lock)
    if rule is None or rule.origin != origin:
        raise NotFoundError(MSG_NOT_FOUND)
    return rule


def _touch(rule: ValidationRule, user_id: int) -> None:
    rule.version += 1
    rule.updated_at, rule.updated_by = now_utc(), user_id


def update_rule(
    db: Session, origin: SupplierOrigin, rule_id: int, raw_name: str, raw_parameter, version: int, user_id: int
) -> list[str]:
    """Edita el nombre y el valor esperado de una regla, activa o eliminada. Devuelve los campos que cambiaron (vacio
    si no hubo cambios), sin sus valores: el router los registra en el log despues del commit."""
    rule = get_rule(db, origin, rule_id, lock=True)
    draft = check_values(db, DEFINITIONS[origin, rule.rule_code], raw_name, raw_parameter)
    if draft.errors:
        raise RuleValidationError(rule, draft)
    if version != rule.version:
        raise BusinessRuleError(MSG_CONCURRENT_EDIT)
    changes = {"name": draft.name, "parameter": draft.parameter}
    old = {field: getattr(rule, field) for field, value in changes.items() if getattr(rule, field) != value}
    if not old:
        return []
    new = {field: changes[field] for field in old}
    for field, value in new.items():
        setattr(rule, field, value)
    old["version"], new["version"] = rule.version, rule.version + 1
    _touch(rule, user_id)
    audit(db, "VALIDATION_RULE_UPDATED", ENTITY, rule.id, user_id, old, new)
    return [field for field in changes if field in old]


def delete_rule(db: Session, origin: SupplierOrigin, rule_id: int, user_id: int) -> bool:
    """Baja logica: la regla deja de aplicarse en las prevalidaciones siguientes. False si ya estaba eliminada."""
    rule = get_rule(db, origin, rule_id, lock=True)
    if not rule.is_active:
        return False
    rule.is_active, rule.deleted_at, rule.deleted_by = False, now_utc(), user_id
    _touch(rule, user_id)
    audit(db, "VALIDATION_RULE_DELETED", ENTITY, rule.id, user_id, {"is_active": True}, {"is_active": False})
    return True


def restore_rule(db: Session, origin: SupplierOrigin, rule_id: int, user_id: int) -> bool:
    """Reactiva una regla eliminada si su valor esperado es valido (400 si no). False si ya estaba activa."""
    rule = get_rule(db, origin, rule_id, lock=True)
    if rule.is_active:
        return False
    draft = check_values(db, DEFINITIONS[origin, rule.rule_code], rule.name, rule.parameter)
    if draft.errors:
        raise RuleValidationError(rule, draft)
    rule.is_active, rule.deleted_at, rule.deleted_by = True, None, None
    _touch(rule, user_id)
    audit(db, "VALIDATION_RULE_RESTORED", ENTITY, rule.id, user_id, {"is_active": False}, {"is_active": True})
    return True
