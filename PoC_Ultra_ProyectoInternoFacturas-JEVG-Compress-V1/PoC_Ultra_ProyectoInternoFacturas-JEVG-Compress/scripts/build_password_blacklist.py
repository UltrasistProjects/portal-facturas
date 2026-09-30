"""Genera infra/keycloak/common_passwords.txt, la lista de la politica passwordBlacklist del realm (D17).

Keycloak compara la contrasena completa, sin distinguir mayusculas, contra cada linea. Como la politica ya exige un
digito y un caracter especial, ninguna entrada de la lista base (common_words.txt) podria coincidir con una contrasena
valida: la lista sola no bloquearia nada. Por eso, ademas de la lista base, se agrega cada palabra de solo letras (4 o
mas) con los sufijos que se usan para cumplir la regla ("password1!", "portal2026!"). Es una aproximacion de la regla
que aplicaba el portal (palabra comun decorada con digitos y simbolos), no una equivalencia exacta.

Uso: python scripts/build_password_blacklist.py [--check]
Con --check no escribe: termina con codigo 1 si el archivo versionado no corresponde a la lista base.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "infra" / "keycloak" / "common_words.txt"
OUTPUT = ROOT / "infra" / "keycloak" / "common_passwords.txt"
HEADER = "# Generado por scripts/build_password_blacklist.py a partir de common_words.txt: no editar a mano."
# Sufijos frecuentes para cumplir "un digito y un caracter especial"; cada uno tiene ambos.
SUFFIXES = (
    "1!", "12!", "123!", "1234!", "12345!", "1@", "123@", "1#", "123#", "1*", "123*", "1.", "123.",
    "!1", "@1", "#1", "!123", "@123", "2024!", "2025!", "2026!", "2027!", "2026@", "2026#", "2026*", "2026.",
)  # fmt: skip
WORD = re.compile(r"[^\W\d_]{4,}")


def base_entries(source: Path = SOURCE) -> list[str]:
    lines = source.read_text(encoding="utf-8").splitlines()
    return [line.strip().lower() for line in lines if line.strip() and not line.startswith("#")]


def build(source: Path = SOURCE) -> str:
    entries = base_entries(source)
    words = [entry for entry in entries if WORD.fullmatch(entry)]
    decorated = [word + suffix for word in words for suffix in SUFFIXES]
    unique = list(dict.fromkeys([*entries, *decorated]))
    return "\n".join([HEADER, *unique]) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="solo verifica que el archivo este al dia")
    args = parser.parse_args(argv)
    content = build()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != content:
            print(f"{OUTPUT.relative_to(ROOT)} no esta al dia: ejecute python scripts/build_password_blacklist.py")
            return 1
        return 0
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"{OUTPUT.relative_to(ROOT)}: {content.count(chr(10)) - 1} entradas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
