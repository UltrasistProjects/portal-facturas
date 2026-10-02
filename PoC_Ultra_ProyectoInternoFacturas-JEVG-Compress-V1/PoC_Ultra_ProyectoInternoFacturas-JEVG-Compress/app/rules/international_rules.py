"""Reglas del Invoice del proveedor internacional (HU-15 y HU-16).

Las reglas INT buscan en el texto del Invoice los datos del proveedor y de ULTRASIST. El Invoice no tiene formato fijo
y su texto puede extraerse mal, asi que una ausencia es una advertencia para el PMO y nunca bloquea el envio (D8).
FIN-007 si bloquea: es el control de duplicados del Invoice, que no tiene UUID.
"""

import re
import unicodedata

from app.rules.base import not_applicable, outcome
from app.rules.xml_rules import DISABLED
from app.schemas import ValidationOutcome
from app.services.validation_settings_service import RuleParameters

SOURCE = "Invoice.pdf"
INT_CODES = ("INT-001", "INT-002", "INT-003", "INT-004")
UNREADABLE = "No se pudo leer el texto del Invoice"
NO_ADDRESS = "Dirección no configurada en Reglas de Validación"
NO_VALUE = "Sin dato que buscar"
FOUND, NOT_FOUND = "Encontrado en el Invoice", "No encontrado"


def compact(value: str | None) -> str:
    """Texto comparable: sin acentos, en minusculas y solo con letras y digitos. Asi "ULTRASIST, S.A. de C.V."
    coincide con "ULTRASIST SA DE CV" y "98-7654321" con "987654321"."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", value or "") if not unicodedata.combining(c))
    return re.sub(r"[^0-9a-z]", "", plain.casefold())


def _search(code: str, value: str, haystack: str, message_pass: str, message_fail: str) -> ValidationOutcome:
    needle = compact(value)
    if not needle:
        return not_applicable(code, "INT", "WARNING", NO_VALUE, source_document=SOURCE)
    found = needle in haystack
    return outcome(
        code,
        "INT",
        found,
        "WARNING",
        message_pass,
        message_fail,
        value,
        FOUND if found else NOT_FOUND,
        SOURCE,
        warning=True,
    )


def international_rules(text: str, readable: bool, supplier, params: RuleParameters) -> list[ValidationOutcome]:
    """INT-001 a INT-004 sobre el texto del Invoice. Sin texto legible (o sin Invoice), NOT_EVALUATED."""
    if not readable:
        return [
            outcome(code, "INT", None, "WARNING", UNREADABLE, UNREADABLE, source_document=SOURCE) for code in INT_CODES
        ]
    haystack = compact(text)
    results = [
        _search(
            "INT-001",
            supplier.foreign_tax_id,
            haystack,
            "Identificador fiscal del proveedor presente en el Invoice",
            "No se encontró el identificador fiscal del proveedor en el Invoice",
        )
    ]
    if params.check_receiver_name:
        results.append(
            _search(
                "INT-002",
                params.receiver_name,
                haystack,
                "Razón social de ULTRASIST presente en el Invoice",
                "No se encontró la razón social de ULTRASIST en el Invoice",
            )
        )
    else:
        results.append(not_applicable("INT-002", "INT", "WARNING", DISABLED, params.receiver_name, SOURCE))
    if params.check_receiver_postal_code:
        # Numero aislado: 03930 no debe coincidir dentro de 1039300 (en compact() los digitos quedarian juntos).
        found = re.search(rf"(?<!\d){re.escape(params.receiver_postal_code)}(?!\d)", text) is not None
        results.append(
            outcome(
                "INT-003",
                "INT",
                found,
                "WARNING",
                "Código postal de ULTRASIST presente en el Invoice",
                "No se encontró el código postal de ULTRASIST en el Invoice",
                params.receiver_postal_code,
                FOUND if found else NOT_FOUND,
                SOURCE,
                warning=True,
            )
        )
    else:
        results.append(not_applicable("INT-003", "INT", "WARNING", DISABLED, params.receiver_postal_code, SOURCE))
    if compact(params.receiver_address):
        results.append(
            _search(
                "INT-004",
                params.receiver_address,
                haystack,
                "Dirección de ULTRASIST presente en el Invoice",
                "No se encontró la dirección de ULTRASIST en el Invoice",
            )
        )
    else:
        results.append(not_applicable("INT-004", "INT", "WARNING", NO_ADDRESS, source_document=SOURCE))
    return results


def invoice_duplicate_rule(filename: str | None, folios: list[str]) -> ValidationOutcome:
    """FIN-007: otra factura del proveedor tiene vigente un Invoice con el mismo nombre de archivo. Sin Invoice
    (`filename` None) no hay nada que comparar."""
    if filename is None:
        return outcome("FIN-007", "FIN", None, "CRITICAL", "", "Sin Invoice (PDF) que comparar")
    return outcome(
        "FIN-007",
        "FIN",
        not folios,
        "CRITICAL",
        "Invoice no duplicado",
        "Invoice duplicado por nombre de archivo",
        "Nombre de archivo único",
        filename,
        SOURCE,
        evidence={"invoices": folios},
    )
