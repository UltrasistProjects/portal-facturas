"""Reglas de Validacion configurables por origen de proveedor (ajustes-finales-configuracion).

Cada regla del catalogo validation_rules tiene aqui su definicion: origen, codigo, nombre inicial, lo que compara, su
severidad y el tipo de su valor esperado. La tabla guarda lo que el Administrador cambia (nombre, valor esperado y
baja logica); el motor y la pantalla leen ambas cosas con validation_rules_service.rule_set, de modo que lo que se ve
es exactamente lo que se aplica.

Las demas reglas del motor (DOC, SUP, FIN, CON, DAT, SEM y XML-001, XML-006, XML-007 y XML-008) no se configuran.
XML-007 compara la moneda con el catalogo de monedas: es la regla inviolable de la moneda y no se puede eliminar.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.core.constants import CatalogType, Severity, SupplierOrigin


class ParameterKind(StrEnum):
    """Tipo del valor esperado de una regla: decide como se captura y se valida."""

    NONE = "NONE"
    RFC = "RFC"
    TEXT = "TEXT"
    ADDRESS = "ADDRESS"
    POSTAL_CODE = "POSTAL_CODE"
    CATALOG_CODE = "CATALOG_CODE"
    CATALOG_CODES = "CATALOG_CODES"


@dataclass(frozen=True)
class RuleDefinition:
    origin: SupplierOrigin
    code: str
    name: str
    compares: str
    severity: Severity
    kind: ParameterKind
    label: str = ""
    catalog: CatalogType | None = None


NATIONAL, INTERNATIONAL = SupplierOrigin.NATIONAL, SupplierOrigin.INTERNATIONAL
RULE_DEFINITIONS = (
    RuleDefinition(
        NATIONAL, "XML-002", "RFC del receptor", "Receptor.Rfc", Severity.CRITICAL, ParameterKind.RFC, "RFC"
    ),
    RuleDefinition(
        NATIONAL,
        "XML-003",
        "Método de pago",
        "MetodoPago",
        Severity.ERROR,
        ParameterKind.CATALOG_CODE,
        "Método de pago",
        CatalogType.PAYMENT_METHOD,
    ),
    RuleDefinition(
        NATIONAL,
        "XML-004",
        "Forma de pago",
        "FormaPago",
        Severity.ERROR,
        ParameterKind.CATALOG_CODE,
        "Forma de pago",
        CatalogType.PAYMENT_FORM,
    ),
    RuleDefinition(
        NATIONAL,
        "XML-005",
        "Usos de CFDI",
        "Receptor.UsoCFDI",
        Severity.ERROR,
        ParameterKind.CATALOG_CODES,
        "Usos de CFDI",
        CatalogType.CFDI_USE,
    ),
    RuleDefinition(
        NATIONAL,
        "XML-009",
        "Razón social del receptor",
        "Receptor.Nombre",
        Severity.ERROR,
        ParameterKind.TEXT,
        "Razón social",
    ),
    RuleDefinition(
        NATIONAL,
        "XML-010",
        "Código postal del receptor",
        "Receptor.DomicilioFiscalReceptor",
        Severity.ERROR,
        ParameterKind.POSTAL_CODE,
        "Código postal",
    ),
    RuleDefinition(
        NATIONAL,
        "XML-011",
        "Régimen fiscal del receptor",
        "Receptor.RegimenFiscalReceptor",
        Severity.ERROR,
        ParameterKind.CATALOG_CODE,
        "Régimen fiscal",
        CatalogType.TAX_REGIME,
    ),
    RuleDefinition(
        INTERNATIONAL,
        "INT-001",
        "Identificador fiscal del proveedor",
        "Identificador fiscal del proveedor en el texto del Invoice",
        Severity.WARNING,
        ParameterKind.NONE,
    ),
    RuleDefinition(
        INTERNATIONAL,
        "INT-002",
        "Razón social de ULTRASIST",
        "Razón social en el texto del Invoice",
        Severity.WARNING,
        ParameterKind.TEXT,
        "Razón social",
    ),
    RuleDefinition(
        INTERNATIONAL,
        "INT-003",
        "Código postal de ULTRASIST",
        "Código postal en el texto del Invoice",
        Severity.WARNING,
        ParameterKind.POSTAL_CODE,
        "Código postal",
    ),
    RuleDefinition(
        INTERNATIONAL,
        "INT-004",
        "Dirección de ULTRASIST",
        "Dirección en el texto del Invoice",
        Severity.WARNING,
        ParameterKind.ADDRESS,
        "Dirección",
    ),
)
DEFINITIONS = {(definition.origin, definition.code): definition for definition in RULE_DEFINITIONS}


@dataclass(frozen=True)
class ConfiguredRule:
    """Estado vigente de una regla: si esta activa y su valor esperado."""

    active: bool
    parameter: Any = None


@dataclass(frozen=True)
class RuleSet:
    """Reglas de un origen que aplica una prevalidacion, y las monedas activas del catalogo (XML-007)."""

    rules: Mapping[str, ConfiguredRule] = field(default_factory=dict)
    currencies: frozenset[str] = frozenset()

    def active(self, code: str) -> bool:
        rule = self.rules.get(code)
        return bool(rule and rule.active)

    def parameter(self, code: str) -> Any:
        rule = self.rules.get(code)
        return rule.parameter if rule else None
