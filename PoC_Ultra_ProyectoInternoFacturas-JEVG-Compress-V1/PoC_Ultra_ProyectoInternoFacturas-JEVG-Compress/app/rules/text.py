"""Normalizacion de textos para comparar datos de la factura con el proveedor y la orden de compra."""

import re
import unicodedata


def _plain(value: str | None) -> str:
    """Sin acentos ni diacriticos y en minusculas."""
    return "".join(c for c in unicodedata.normalize("NFKD", value or "") if not unicodedata.combining(c)).casefold()


def normalize_text(value: str | None) -> str:
    """Palabras comparables: sin acentos, en minusculas, con los signos como espacios y los espacios colapsados."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", _plain(value)).split())


def compact(value: str | None) -> str:
    """Texto comparable: sin acentos, en minusculas y solo con letras y digitos. Asi "FERROMEX, S.A. de C.V."
    coincide con "FERROMEX SA DE CV" y "L-31 T-900" con "L-31T-900"."""
    return re.sub(r"[^0-9a-z]", "", _plain(value))


def same_name(first: str | None, second: str | None) -> bool:
    """Dos nombres o razones sociales iguales sin distinguir mayusculas, acentos, espacios ni signos (RD-05)."""
    left = compact(first)
    return bool(left) and left == compact(second)
