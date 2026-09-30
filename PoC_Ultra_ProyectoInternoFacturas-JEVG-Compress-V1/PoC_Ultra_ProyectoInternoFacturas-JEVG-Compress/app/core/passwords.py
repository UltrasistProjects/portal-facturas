"""Contrasenas temporales que el portal entrega a Keycloak (add-keycloak-authentication).

La politica de contrasenas (RF-06) la aplica Keycloak con la politica del realm (infra/keycloak/): el portal ya no
recibe ni valida las contrasenas que eligen los usuarios. Las temporales que genera aqui la cumplen.
"""

import secrets
import string


def generate_password(length: int = 20) -> str:
    """Contrasena aleatoria con letras, digitos y un caracter especial garantizados."""
    alphabet = string.ascii_letters + string.digits
    body = [secrets.choice(alphabet) for _ in range(length - 3)]
    body += [secrets.choice(string.ascii_letters), secrets.choice(string.digits), secrets.choice("#$%&*+-=?@_")]
    secrets.SystemRandom().shuffle(body)
    return "".join(body)
