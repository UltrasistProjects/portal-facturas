"""Validacion 1 del proveedor (HU-24, RD-05): el emisor del CFDI es el proveedor del usuario.

PRV-001 compara el RFC, PRV-002 el nombre y PRV-003 exige un regimen fiscal activo del catalogo. Que el proveedor este
"Autorizado" lo cubre SUP-001. El Invoice internacional no es un CFDI: las tres resultan NOT_APPLICABLE.
"""

from collections.abc import Collection

from app.rules.base import NOT_FOR_INTERNATIONAL, not_applicable, outcome
from app.rules.text import same_name
from app.schemas import ValidationOutcome

SEVERITIES = {"PRV-001": "CRITICAL", "PRV-002": "ERROR", "PRV-003": "ERROR"}
NO_DATA = "Sin datos de la factura"


def supplier_identity_rules(
    data: dict | None,
    supplier,
    tax_regimes: Collection[str],
    international: bool = False,
    source_document: str | None = None,
) -> list[ValidationOutcome]:
    """`data` son los datos del comprobante (XML o PDF); `tax_regimes`, las claves activas del catalogo."""
    if international:
        return [not_applicable(code, "PRV", severity, NOT_FOR_INTERNATIONAL) for code, severity in SEVERITIES.items()]
    if data is None:
        return [outcome(code, "PRV", None, severity, NO_DATA, NO_DATA) for code, severity in SEVERITIES.items()]
    rfc = (data.get("issuer_rfc") or "").strip().upper()
    expected_rfc = (supplier.rfc or "").strip().upper()
    name = data.get("issuer_name")
    regime = (data.get("issuer_regime") or "").strip()
    if not regime:
        regime_message = "Falta el régimen fiscal del emisor"
    else:
        regime_message = f"Régimen fiscal {regime} no válido"
    return [
        outcome(
            "PRV-001",
            "PRV",
            bool(rfc) and rfc == expected_rfc,
            "CRITICAL",
            "RFC del emisor corresponde al proveedor",
            f"El RFC emisor {rfc or 'ausente'} no corresponde al proveedor {expected_rfc}",
            expected_rfc,
            rfc or None,
            source_document,
            "Emisor.Rfc",
        ),
        outcome(
            "PRV-002",
            "PRV",
            same_name(name, supplier.business_name),
            "ERROR",
            "Nombre del emisor coincide",
            "El nombre del emisor no coincide con el proveedor",
            supplier.business_name,
            name,
            source_document,
            "Emisor.Nombre",
        ),
        outcome(
            "PRV-003",
            "PRV",
            bool(regime) and regime in tax_regimes,
            "ERROR",
            "Régimen fiscal del emisor válido",
            regime_message,
            "Régimen activo del catálogo",
            regime or None,
            source_document,
            "Emisor.RegimenFiscal",
        ),
    ]
