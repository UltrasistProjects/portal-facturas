"""Normalizacion deterministica de lo que leyo la IA: los mismos tipos y formatos que parse_cfdi (Decimal, RFC y UUID
en mayusculas, fecha ISO, claves del SAT). Un valor con formato invalido queda en None: nunca se corrige adivinando.

`ground` comprueba que los identificadores y los importes que devolvio el modelo aparezcan en el texto del documento;
si no aparecen, los deja en None (un modelo de lenguaje puede completar un dato que no esta impreso).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.rfc import RFC_PATTERN

UUID_PATTERN = re.compile(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}")
TAX_CODES = {"ISR": "001", "IVA": "002", "IEPS": "003"}
TAX_KINDS = {"TRASLADO": "Traslado", "TRASLADOS": "Traslado", "RETENCION": "Retencion", "RETENCIONES": "Retencion"}
# Campos que se comprueban contra el texto del documento.
GROUNDED_TEXT = ("uuid", "issuer_rfc", "receiver_rfc", "folio")
GROUNDED_AMOUNTS = ("subtotal", "tax", "total")


def text(value: Any, limit: int = 1000) -> str | None:
    if value is None:
        return None
    value = " ".join(str(value).split())
    return value[:limit] or None


def code(value: Any, pattern: str) -> str | None:
    """Clave del SAT al inicio del texto ("99 - Por definir" -> "99"); None si no tiene el formato."""
    value = text(value)
    match = re.match(rf"\s*({pattern})(?![A-Z0-9])", value.upper()) if value else None
    return match.group(1) if match else None


def amount(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    raw = str(value).replace(",", "").replace("$", "").replace(" ", "").strip()
    if not raw:
        return None
    try:
        result = Decimal(raw)
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def rfc(value: Any) -> str | None:
    value = text(value)
    if not value:
        return None
    value = re.sub(r"[\s-]", "", value.upper())
    return value if RFC_PATTERN.fullmatch(value) else None


def uuid(value: Any) -> str | None:
    value = text(value)
    if not value:
        return None
    value = value.replace(" ", "").upper()
    return value if UUID_PATTERN.fullmatch(value) else None


def issued_at(value: Any) -> str | None:
    """Fecha de emision en ISO: con hora como parse_cfdi ("2026-01-03T14:24:46") o, si solo trae el dia, el dia."""
    value = text(value)
    if not value:
        return None
    try:
        if len(value) <= 10:
            return date.fromisoformat(value).isoformat()
        return datetime.fromisoformat(value.replace(" ", "T", 1)).replace(tzinfo=None).isoformat()
    except ValueError:
        return None


def rate(value: Any) -> str | None:
    result = amount(value)
    return f"{result:.6f}" if result is not None and 0 <= result <= 1 else None


def tax_line(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    kind = TAX_KINDS.get((text(raw.get("kind")) or "").upper())
    tax = text(raw.get("tax"))
    tax = TAX_CODES.get((tax or "").upper()) or code(tax, r"00[1-3]")
    line = {
        "kind": kind or "Traslado",
        "tax": tax,
        "rate": rate(raw.get("rate")),
        "base": amount(raw.get("base")),
        "amount": amount(raw.get("amount")),
    }
    return line if line["tax"] or line["amount"] is not None else None


def concept(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    item = {
        "description": text(raw.get("description"), 1000),
        "quantity": amount(raw.get("quantity")),
        "unit_key": code(raw.get("unit_key"), r"[A-Z0-9]{2,3}"),
        "unit": text(raw.get("unit"), 50),
        "identification": text(raw.get("identification"), 100),
        "unit_value": amount(raw.get("unit_value")),
        "tax_object": code(raw.get("tax_object"), r"0[1-8]"),
        "amount": amount(raw.get("amount")),
        "taxes": [line for line in map(tax_line, raw.get("taxes") or []) if line],
    }
    return item if item["description"] or item["amount"] is not None else None


def invoice(raw: dict[str, Any]) -> dict[str, Any]:
    """Datos con las claves y tipos de parse_cfdi. Como parse_cfdi, el IVA trasladado sin dato es la suma de los
    traslados de los conceptos o 0."""
    concepts = [item for item in map(concept, raw.get("concepts") or []) if item]
    data = {
        "version": code(raw.get("version"), r"[34]\.[0-9]"),
        "uuid": uuid(raw.get("uuid")),
        "series": text(raw.get("series"), 25),
        "folio": text(raw.get("folio"), 40),
        "issuer_rfc": rfc(raw.get("issuer_rfc")),
        "issuer_name": text(raw.get("issuer_name"), 300),
        "issuer_regime": code(raw.get("issuer_regime"), r"\d{3}"),
        "receiver_rfc": rfc(raw.get("receiver_rfc")),
        "receiver_name": text(raw.get("receiver_name"), 300),
        "receiver_postal_code": code(raw.get("receiver_postal_code"), r"\d{5}"),
        "receiver_regime": code(raw.get("receiver_regime"), r"\d{3}"),
        "date": issued_at(raw.get("date")),
        "subtotal": amount(raw.get("subtotal")),
        "tax": amount(raw.get("tax")),
        "total": amount(raw.get("total")),
        "currency": code(raw.get("currency"), r"[A-Z]{3}"),
        "payment_form": code(raw.get("payment_form"), r"\d{2}"),
        "payment_method": code(raw.get("payment_method"), r"PUE|PPD"),
        "cfdi_use": code(raw.get("cfdi_use"), r"[A-Z]{1,2}\d{2}"),
        "voucher_type": code(raw.get("voucher_type"), r"[IEPTN]"),
        "concepts": concepts,
    }
    return data


def finish(data: dict[str, Any]) -> dict[str, Any]:
    if data["tax"] is None:
        data["tax"] = sum(
            (t["amount"] or Decimal() for c in data["concepts"] for t in c["taxes"] if t["kind"] == "Traslado"),
            Decimal(),
        )
    return data


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def _amount_variants(value: Decimal) -> set[str]:
    plain = f"{value:.2f}"
    return {plain, f"{value:,.2f}", str(value)}


def ground(data: dict[str, Any], content: str) -> list[str]:
    """Deja en None los identificadores e importes que no aparecen en el texto; devuelve sus nombres."""
    haystack = _compact(content or "")
    removed = []
    for key in GROUNDED_TEXT:
        value = data.get(key)
        if value and _compact(value) not in haystack:
            data[key] = None
            removed.append(key)
    for key in GROUNDED_AMOUNTS:
        value = data.get(key)
        if value is not None and value != 0 and not any(_compact(v) in haystack for v in _amount_variants(value)):
            data[key] = None
            removed.append(key)
    return removed
