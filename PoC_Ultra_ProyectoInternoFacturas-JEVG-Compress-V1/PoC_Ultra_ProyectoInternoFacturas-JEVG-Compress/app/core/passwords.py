import re
import secrets
import string
from functools import lru_cache
from pathlib import Path

# Politica de la ERS (RF-06). La auditoria sugeria 12 caracteres minimos; subirlo es cambiar esta constante.
MIN_LENGTH = 8
# Tope superior: evita que una contrasena enorme dispare el costo de Argon2.
MAX_LENGTH = 128
COMMON_PASSWORDS_FILE = Path(__file__).with_name("common_passwords.txt")


@lru_cache
def common_passwords() -> frozenset[str]:
    lines = COMMON_PASSWORDS_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip().lower() for line in lines if line.strip() and not line.startswith("#"))


def password_problems(password: str) -> list[str]:
    if len(password) < MIN_LENGTH:
        return [f"La contrasena debe tener al menos {MIN_LENGTH} caracteres."]
    if len(password) > MAX_LENGTH:
        return [f"La contrasena no puede exceder {MAX_LENGTH} caracteres."]
    problems = []
    if not re.search(r"[^\W\d_]", password):
        problems.append("La contrasena debe incluir al menos una letra.")
    if not re.search(r"\d", password):
        problems.append("La contrasena debe incluir al menos un numero.")
    if not re.search(r"[^\w]|_", password):
        problems.append("La contrasena debe incluir al menos un caracter especial.")
    # Una palabra comun decorada con digitos y simbolos (Password1!) sigue siendo comun.
    letters_only = re.sub(r"[\W\d_]", "", password).lower()
    common = common_passwords()
    if password.lower() in common or (len(letters_only) >= 4 and letters_only in common):
        problems.append("La contrasena es demasiado comun; elija otra.")
    return problems


def validate_password(password: str) -> str:
    problems = password_problems(password)
    if problems:
        raise ValueError(" ".join(problems))
    return password


def generate_password(length: int = 20) -> str:
    """Contrasena aleatoria con letras, digitos y un caracter especial garantizados."""
    alphabet = string.ascii_letters + string.digits
    body = [secrets.choice(alphabet) for _ in range(length - 3)]
    body += [secrets.choice(string.ascii_letters), secrets.choice(string.digits), secrets.choice("#$%&*+-=?@_")]
    secrets.SystemRandom().shuffle(body)
    return "".join(body)
