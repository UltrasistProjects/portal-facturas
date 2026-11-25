"""RFC del proveedor nacional: las reglas de la carga masiva (HU-01), compartidas con la edicion del proveedor."""

import re
from datetime import date

from app.core.constants import SupplierType

RFC_PATTERN = re.compile(r"^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$")
GENERIC_RFCS = {"XAXX010101000", "XEXX010101000"}
RFC_LENGTH = {SupplierType.PERSONA_MORAL: (12, "moral"), SupplierType.PERSONA_FISICA: (13, "física")}
MSG_GENERIC = "no se permite un RFC genérico; un proveedor extranjero se registra con Origen Internacional"
MSG_FORMAT = "tiene un formato inválido"
MSG_LENGTH = "una persona {label} debe tener un RFC de {length} caracteres"


def valid_rfc_date(digits: str) -> bool:
    """Los seis digitos del RFC (aammdd) forman una fecha valida en el siglo XX o XXI."""
    year, month, day = int(digits[:2]), int(digits[2:4]), int(digits[4:])
    for century in (1900, 2000):
        try:
            date(century + year, month, day)
            return True
        except ValueError:
            continue
    return False


def rfc_error(rfc: str, supplier_type: SupplierType | None) -> str | None:
    """Motivo por el que el RFC (ya en mayusculas) no es valido para ese tipo de persona; None si lo es."""
    if rfc in GENERIC_RFCS:
        return MSG_GENERIC
    if not (RFC_PATTERN.fullmatch(rfc) and valid_rfc_date(rfc[-9:-3])):
        return MSG_FORMAT
    if supplier_type in RFC_LENGTH and len(rfc) != RFC_LENGTH[supplier_type][0]:
        length, label = RFC_LENGTH[supplier_type]
        return MSG_LENGTH.format(label=label, length=length)
    return None
