"""Validacion 2: la factura contra su orden de compra (HU-24, OC-001 a OC-012; secciones 6.4 y 6.7 de la HU).

Funciones puras: reciben los datos del comprobante, la orden ya leida (OrderView) y los folios de las otras facturas
vigentes de la orden; purchase_order_service hace las consultas. Cada resultado guarda en su evidencia el encabezado
de la orden y, por concepto, la partida usada, tal como se leyeron (RD-15).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.core.constants import (
    AMOUNT_TOLERANCE,
    IVA_RATE,
    IVA_TAX,
    PO_CURRENCY,
    PO_MATERIAL_DOC,
    PO_NET_PRICE,
    PO_POSTING_DATE,
    PO_QUANTITY,
    PO_TEXT,
    PO_UNIT,
    UNIT_EQUIVALENCES,
)
from app.rules.base import not_applicable, outcome
from app.rules.text import compact, same_name
from app.schemas import ValidationOutcome

CATEGORY = "OC"
SEVERITIES = {
    "OC-001": "CRITICAL",
    "OC-002": "CRITICAL",
    "OC-003": "CRITICAL",
    "OC-004": "ERROR",
    "OC-005": "ERROR",
    "OC-006": "ERROR",
    "OC-007": "ERROR",
    "OC-008": "ERROR",
    "OC-009": "ERROR",
    "OC-010": "ERROR",
    "OC-011": "ERROR",
    "OC-012": "CRITICAL",
}
NO_ORDER = "Sin orden de compra"
NOT_FOR_INTERNATIONAL = "No aplica para proveedores internacionales"
NO_ITEMS = "Sin partidas en el Invoice"
# OC seguido de "/", "-", ":" o espacios y de 6 a 10 digitos, con o sin parentesis (RD-06).
ORDER_NUMBER = re.compile(r"(?<![A-Z0-9])OC(?:\s*[/:\-]\s*|\s+)(\d{6,10})(?!\d)", re.IGNORECASE)
CAPTURED_NUMBER = re.compile(r"\d{6,10}")


def to_decimal(value) -> Decimal | None:
    """Decimal de un valor de la orden o de la factura (texto con punto); None si no es un numero."""
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def quantity_text(value: Decimal | None) -> str:
    """Cantidad sin ceros sobrantes: 2.00 -> "2", 1.50 -> "1.5"."""
    if value is None:
        return "—"
    text = format(value.normalize(), "f")
    return text


def money_text(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def close(first: Decimal | None, second: Decimal | None) -> bool:
    """Montos iguales redondeados a centavos, con la tolerancia de redondeo (RD-12)."""
    if first is None or second is None:
        return False
    cents = Decimal("0.01")
    return abs(first.quantize(cents) - second.quantize(cents)) <= AMOUNT_TOLERANCE


# --- Orden de compra leida --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderItem:
    """Partida de la orden con las etiquetas de SAP; `position` es su lugar en data["items"], desde 1."""

    position: int
    values: Mapping[str, str]

    def _text(self, key: str) -> str:
        return str(self.values.get(key) or "").strip()

    @property
    def text(self) -> str:
        return self._text(PO_TEXT)

    @property
    def quantity(self) -> Decimal | None:
        return to_decimal(self.values.get(PO_QUANTITY))

    @property
    def unit(self) -> str:
        return self._text(PO_UNIT)

    @property
    def net_price(self) -> Decimal | None:
        return to_decimal(self.values.get(PO_NET_PRICE))

    @property
    def currency(self) -> str:
        return self._text(PO_CURRENCY).upper()

    @property
    def delivered(self) -> bool:
        """Entrada de mercancia registrada: documento de material y fecha contable con dato (RN-HU24-12)."""
        return bool(self._text(PO_MATERIAL_DOC) and self._text(PO_POSTING_DATE))


@dataclass(frozen=True)
class OrderView:
    id: int
    convenio: int
    rfc: str
    supplier_name: str
    order_date: date
    total: Decimal
    taxes: Decimal
    items: tuple[OrderItem, ...]

    def header(self) -> dict:
        """Encabezado leido, para la evidencia de cada resultado."""
        return {
            "purchase_order_id": self.id,
            "convenio": self.convenio,
            "rfc": self.rfc,
            "supplier_name": self.supplier_name,
            "total": f"{self.total:.2f}",
            "taxes": f"{self.taxes:.2f}",
        }


def order_items(data: Mapping | None) -> tuple[OrderItem, ...]:
    items = (data or {}).get("items") or []
    return tuple(OrderItem(index, item) for index, item in enumerate(items, 1) if isinstance(item, Mapping))


# --- Numero de la orden en los conceptos (RD-06) ----------------------------------------------------------------------


@dataclass(frozen=True)
class OrderReference:
    """Numeros de orden citados, en orden de aparicion y sin repetir. `number` es el unico citado."""

    cited: tuple[str, ...] = ()

    @property
    def number(self) -> str | None:
        return self.cited[0] if len(self.cited) == 1 else None

    @property
    def conflict(self) -> bool:
        return len(self.cited) > 1


def order_numbers(text: str | None) -> list[str]:
    """Numeros de orden de un texto, sin ceros a la izquierda."""
    return [str(int(match)) for match in ORDER_NUMBER.findall(text or "")]


def detect_order_number(descriptions: Iterable[str | None]) -> OrderReference:
    cited: list[str] = []
    for description in descriptions:
        for number in order_numbers(description):
            if number not in cited:
                cited.append(number)
    return OrderReference(tuple(cited))


def captured_reference(number: str | None) -> OrderReference:
    """Numero capturado por el proveedor internacional: valido si tiene de 6 a 10 digitos."""
    value = (number or "").strip()
    return OrderReference((str(int(value)),)) if CAPTURED_NUMBER.fullmatch(value) else OrderReference()


# --- Emparejamiento de partidas (RD-08, RD-09) y unidades (RD-10) -----------------------------------------------------


@dataclass(frozen=True)
class ItemMatch:
    concept: int
    item: OrderItem | None
    ambiguous: bool = False


def concept_text(concept: Mapping) -> str:
    """Descripcion del concepto con su numero de identificacion: el corte entre ambos en el PDF es heuristico."""
    return f"{concept.get('identification') or ''} {concept.get('description') or ''}"


def match_items(concepts: Sequence[Mapping], items: Sequence[OrderItem]) -> list[ItemMatch]:
    """La partida de cada concepto: su Txt.brv compactado debe estar contenido en la descripcion compactada. Entre las
    partidas aun libres gana la de Txt.brv mas largo; un empate es ambiguo. Una partida se usa una sola vez."""
    used: set[int] = set()
    matches = []
    for number, concept in enumerate(concepts, 1):
        haystack = compact(concept_text(concept))
        candidates = [
            item
            for item in items
            if item.position not in used and compact(item.text) and compact(item.text) in haystack
        ]
        if not candidates:
            matches.append(ItemMatch(number, None))
            continue
        longest = max(len(compact(item.text)) for item in candidates)
        best = [item for item in candidates if len(compact(item.text)) == longest]
        if len(best) > 1:
            matches.append(ItemMatch(number, None, ambiguous=True))
            continue
        used.add(best[0].position)
        matches.append(ItemMatch(number, best[0]))
    return matches


def _unit_group(unit: str) -> set[str]:
    group = {unit}
    for sap_unit, equivalents in UNIT_EQUIVALENCES.items():
        if unit == sap_unit or unit in equivalents:
            group |= equivalents | {sap_unit}
    return group


def units_match(unit_key: str | None, unit: str | None, sap_unit: str | None) -> bool:
    """La clave de unidad o la unidad de la factura equivale a la unidad de la orden (tabla de la seccion 6.5)."""
    expected = (sap_unit or "").strip().upper()
    invoice_units = {value.strip().upper() for value in (unit_key, unit) if value and value.strip()}
    return bool(expected) and bool(invoice_units & _unit_group(expected))


def unit_label(concept: Mapping) -> str:
    parts = [value for value in (concept.get("unit_key"), concept.get("unit")) if value]
    return " - ".join(parts) or "—"


# --- Datos de la factura que se comparan ------------------------------------------------------------------------------


def is_iva(tax: Mapping) -> bool:
    rate = to_decimal(tax.get("rate"))
    return (
        (tax.get("kind") or "Traslado") == "Traslado"
        and str(tax.get("tax") or "") == IVA_TAX
        and rate is not None
        and rate == IVA_RATE
    )


def concept_iva(concept: Mapping) -> Decimal:
    return sum(
        (to_decimal(t.get("amount")) or Decimal("0") for t in concept.get("taxes") or [] if is_iva(t)), Decimal()
    )


def invoice_iva(data: Mapping) -> Decimal | None:
    """IVA de la factura (RD-13): los traslados 002 a 0.160000 de los conceptos o, si ningun concepto trae
    impuestos, el total trasladado del comprobante."""
    concepts = data.get("concepts") or []
    if any(concept.get("taxes") for concept in concepts):
        return sum((concept_iva(concept) for concept in concepts), Decimal())
    return to_decimal(data.get("tax"))


@dataclass(frozen=True)
class InvoiceFacts:
    subtotal: Decimal | None
    iva: Decimal | None
    currency: str | None
    issuer_rfc: str | None = None
    issuer_name: str | None = None
    concepts: tuple[Mapping, ...] = ()


def national_facts(data: Mapping | None) -> InvoiceFacts:
    data = data or {}
    return InvoiceFacts(
        subtotal=to_decimal(data.get("subtotal")),
        iva=invoice_iva(data),
        currency=(data.get("currency") or "").upper() or None,
        issuer_rfc=(data.get("issuer_rfc") or "").strip().upper() or None,
        issuer_name=data.get("issuer_name"),
        concepts=tuple(data.get("concepts") or ()),
    )


def international_facts(invoice, supplier) -> InvoiceFacts:
    """Importes y moneda capturados del Invoice; el nombre que se compara es la razon social del proveedor."""
    return InvoiceFacts(
        subtotal=invoice.subtotal,
        iva=invoice.tax,
        currency=invoice.currency,
        issuer_name=supplier.business_name,
    )


# --- Reglas -----------------------------------------------------------------------------------------------------------


def _rest_not_applicable(codes: Iterable[str], message: str) -> list[ValidationOutcome]:
    return [not_applicable(code, CATEGORY, SEVERITIES[code], message) for code in codes]


def _number_rule(reference: OrderReference, international: bool) -> ValidationOutcome:
    if international:
        return outcome(
            "OC-001",
            CATEGORY,
            reference.number is not None,
            "CRITICAL",
            f"Orden de compra {reference.number} capturada",
            "Capture el número de orden de compra",
            detected=reference.number,
        )
    if reference.conflict:
        message = f"Los conceptos citan órdenes de compra distintas: {', '.join(reference.cited)}"
    else:
        message = "No se encontró el número de orden de compra en los conceptos"
    return outcome(
        "OC-001",
        CATEGORY,
        reference.number is not None,
        "CRITICAL",
        f"Orden de compra {reference.number} detectada",
        message,
        detected=", ".join(reference.cited) or None,
        source_reference="Conceptos",
    )


def _amount_rule(code: str, detected, expected, message_pass: str, label: str, evidence: dict) -> ValidationOutcome:
    return outcome(
        code,
        CATEGORY,
        close(detected, expected),
        SEVERITIES[code],
        message_pass,
        f"{label} {money_text(detected)} distinto {_order_label(code)} {money_text(expected)}",
        money_text(expected),
        money_text(detected),
        evidence=evidence,
    )


def _order_label(code: str) -> str:
    return "del total de la orden de compra" if code == "OC-005" else "de los impuestos de la orden de compra"


def _concept_rules(facts: InvoiceFacts, order: OrderView, header: dict) -> tuple[list, list[OrderItem]]:
    """OC-007, OC-008, OC-009 y OC-011, un resultado por concepto; y las partidas usadas."""
    by_code: dict[str, list[ValidationOutcome]] = {"OC-007": [], "OC-008": [], "OC-009": [], "OC-011": []}
    used: list[OrderItem] = []
    if not facts.concepts:
        by_code["OC-007"].append(
            outcome("OC-007", CATEGORY, False, "ERROR", "", "La factura no tiene conceptos", evidence=header)
        )
    for match in match_items(facts.concepts, order.items):
        concept = facts.concepts[match.concept - 1]
        reference = f"Concepto {match.concept}"
        prefix = f"{reference}: "
        item = match.item
        if item is None:
            failure = "coincide con varias partidas" if match.ambiguous else "sin partida en la orden de compra"
            by_code["OC-007"].append(
                outcome(
                    "OC-007",
                    CATEGORY,
                    False,
                    "ERROR",
                    "",
                    prefix + failure,
                    detected=concept.get("description"),
                    source_reference=reference,
                    evidence=header,
                )
            )
            for code in ("OC-008", "OC-009", "OC-011"):
                by_code[code].append(
                    not_applicable(code, CATEGORY, "ERROR", prefix + "sin partida", source_reference=reference)
                )
            continue
        used.append(item)
        evidence = {**header, "item": dict(item.values)}
        by_code["OC-007"].append(
            outcome(
                "OC-007",
                CATEGORY,
                True,
                "ERROR",
                f"{prefix}partida {item.text}",
                "",
                item.text,
                concept.get("description"),
                source_reference=reference,
                evidence=evidence,
            )
        )
        quantity = to_decimal(concept.get("quantity"))
        problems = []
        if quantity is None or item.quantity is None or quantity != item.quantity:
            problems.append(f"cantidad {quantity_text(quantity)} vs {quantity_text(item.quantity)}")
        if not units_match(concept.get("unit_key"), concept.get("unit"), item.unit):
            problems.append(f"unidad {unit_label(concept)} vs {item.unit or '—'}")
        by_code["OC-008"].append(
            outcome(
                "OC-008",
                CATEGORY,
                not problems,
                "ERROR",
                f"{prefix}cantidad y unidad coinciden",
                prefix + "; ".join(problems),
                f"{quantity_text(item.quantity)} {item.unit}",
                f"{quantity_text(quantity)} {unit_label(concept)}",
                source_reference=reference,
                evidence=evidence,
            )
        )
        amount, price = to_decimal(concept.get("amount")), to_decimal(concept.get("unit_value"))
        expected_amount = item.quantity * item.net_price if item.quantity and item.net_price else None
        if not close(amount, expected_amount):
            failure = f"importe {money_text(amount)} vs {money_text(expected_amount)}"
        else:
            failure = f"precio unitario {money_text(price)} vs {money_text(item.net_price)}"
        by_code["OC-009"].append(
            outcome(
                "OC-009",
                CATEGORY,
                close(amount, expected_amount) and close(price, item.net_price),
                "ERROR",
                f"{prefix}importe coincide",
                prefix + failure,
                money_text(expected_amount),
                money_text(amount),
                source_reference=reference,
                evidence=evidence,
            )
        )
        by_code["OC-011"].append(
            outcome(
                "OC-011",
                CATEGORY,
                item.delivered,
                "ERROR",
                f"{prefix}entrega registrada",
                f"{prefix}la partida no tiene entrada de mercancía",
                "Docto Material y Fecha Conta",
                " / ".join(filter(None, (item.values.get(PO_MATERIAL_DOC), item.values.get(PO_POSTING_DATE))))
                or "Sin entrada de mercancía",
                source_reference=reference,
                evidence=evidence,
            )
        )
    return [result for code in ("OC-007", "OC-008", "OC-009", "OC-011") for result in by_code[code]], used


def _currency_rule(currency: str | None, items: Sequence[OrderItem], header: dict) -> ValidationOutcome:
    currencies = sorted({item.currency for item in items})
    detected = (currency or "").upper()
    return outcome(
        "OC-010",
        CATEGORY,
        bool(detected) and currencies == [detected],
        "ERROR",
        "Moneda coincide con la orden de compra",
        f"Moneda {detected or '—'} distinta de la orden de compra {', '.join(currencies) or '—'}",
        ", ".join(currencies),
        detected or None,
        evidence=header,
    )


def _invoiced_rule(invoiced: Sequence[str], header: dict) -> ValidationOutcome:
    return outcome(
        "OC-012",
        CATEGORY,
        not invoiced,
        "CRITICAL",
        "Orden de compra sin otra factura vigente",
        f"La orden de compra ya tiene la factura {', '.join(invoiced)}",
        "Sin otra factura vigente",
        ", ".join(invoiced) or None,
        evidence={**header, "invoices": list(invoiced)},
    )


def purchase_order_rules(
    facts: InvoiceFacts,
    reference: OrderReference,
    order: OrderView | None,
    invoiced: Sequence[str] = (),
    international: bool = False,
) -> list[ValidationOutcome]:
    """OC-001 a OC-012 (nacional, seccion 6.4) o su variante internacional (seccion 6.7). `invoiced` son los folios
    de las otras facturas vigentes ligadas a la orden (RD-16)."""
    codes = list(SEVERITIES)
    results = [_number_rule(reference, international)]
    if reference.number is None:
        return results + _rest_not_applicable(codes[1:], NO_ORDER)
    results.append(
        outcome(
            "OC-002",
            CATEGORY,
            order is not None,
            "CRITICAL",
            f"Orden de compra {reference.number} encontrada",
            f"La orden de compra {reference.number} no existe para el proveedor",
            detected=reference.number,
            evidence=order.header() if order else None,
        )
    )
    if order is None:
        return results + _rest_not_applicable(codes[2:], NO_ORDER)
    header = order.header()
    if international:
        results.append(not_applicable("OC-003", CATEGORY, "CRITICAL", NOT_FOR_INTERNATIONAL))
    else:
        results.append(
            outcome(
                "OC-003",
                CATEGORY,
                facts.issuer_rfc is not None and facts.issuer_rfc == order.rfc.upper(),
                "CRITICAL",
                "RFC coincide con la orden de compra",
                "RFC no coincide con la orden de compra",
                order.rfc,
                facts.issuer_rfc,
                evidence=header,
            )
        )
    results.append(
        outcome(
            "OC-004",
            CATEGORY,
            same_name(facts.issuer_name, order.supplier_name),
            "WARNING" if international else "ERROR",
            "Nombre coincide con la orden de compra",
            "Nombre no coincide con la orden de compra",
            order.supplier_name,
            facts.issuer_name,
            evidence=header,
            warning=international,
        )
    )
    results.append(
        _amount_rule(
            "OC-005", facts.subtotal, order.total, "Subtotal igual al total de la orden de compra", "Subtotal", header
        )
    )
    label = "Impuestos" if international else "IVA"
    results.append(
        _amount_rule(
            "OC-006", facts.iva, order.taxes, f"{label} igual a los impuestos de la orden de compra", label, header
        )
    )
    if international:
        results += _rest_not_applicable(("OC-007", "OC-008", "OC-009"), NO_ITEMS)
        results.append(_currency_rule(facts.currency, order.items, header))
        pending = [item.text for item in order.items if not item.delivered]
        results.append(
            outcome(
                "OC-011",
                CATEGORY,
                not pending,
                "ERROR",
                "Entrega registrada en todas las partidas",
                f"Partidas sin entrada de mercancía: {', '.join(pending)}",
                "Docto Material y Fecha Conta",
                ", ".join(pending) or "Todas entregadas",
                evidence=header,
            )
        )
    else:
        concept_results, used = _concept_rules(facts, order, header)
        results += concept_results
        results.append(_currency_rule(facts.currency, used or order.items, header))
    results.append(_invoiced_rule(invoiced, header))
    return results
