import secrets
import string


def generate_password(length: int = 20) -> str:
    """Contrasena aleatoria con letras, digitos y un caracter especial garantizados."""
    alphabet = string.ascii_letters + string.digits
    body = [secrets.choice(alphabet) for _ in range(length - 3)]
    body += [secrets.choice(string.ascii_letters), secrets.choice(string.digits), secrets.choice("#$%&*+-=?@_")]
    secrets.SystemRandom().shuffle(body)
    return "".join(body)
