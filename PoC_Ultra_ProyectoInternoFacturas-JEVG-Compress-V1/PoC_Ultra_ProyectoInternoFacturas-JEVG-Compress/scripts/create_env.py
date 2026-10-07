"""Crea .env a partir de .env.example, o completa uno existente, con SECRET_KEY, credenciales de PostgreSQL,
DATABASE_URL y la configuracion del Keycloak local (secretos de los clientes, administrador inicial y DEMO_PASSWORD).

Ante un .env existente solo agrega las claves ausentes (o vacias) sin tocar los valores presentes, salvo un
DATABASE_URL de SQLite, que se reemplaza por el de PostgreSQL avisandolo.
"""

import secrets
import string
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]

POSTGRES_DEFAULTS = {"POSTGRES_USER": "portal", "POSTGRES_DB": "portal", "POSTGRES_PORT": "55432"}
KEYCLOAK_DEFAULTS = {
    "KEYCLOAK_PORT": "58080",
    "KEYCLOAK_REALM": "ultrasist-portal",
    "KC_BOOTSTRAP_ADMIN_USERNAME": "admin",
}
# Secretos de Keycloak que se generan si faltan: los dos clientes del realm y el administrador inicial.
KEYCLOAK_SECRETS = ("KEYCLOAK_CLIENT_SECRET", "KEYCLOAK_ADMIN_CLIENT_SECRET", "KC_BOOTSTRAP_ADMIN_PASSWORD")
SQLITE_WARNING = "AVISO: DATABASE_URL de SQLite reemplazada por la de PostgreSQL (SQLite ya no es compatible)."


def parse_env(lines: list[str]) -> dict[str, str]:
    """Valores de las lineas CLAVE=valor (la primera aparicion; se ignoran comentarios)."""
    values: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition("=")
        key = key.strip()
        if separator and key and not key.startswith("#"):
            values.setdefault(key, value.strip().strip("'\""))
    return values


def _set(lines: list[str], key: str, value: str) -> None:
    """Reemplaza la linea CLAVE= existente o agrega una al final."""
    for index, line in enumerate(lines):
        if "=" in line and line.partition("=")[0].strip() == key:
            lines[index] = f"{key}={value}"
            return
    lines.append(f"{key}={value}")


def database_url(values: dict[str, str]) -> str:
    user, password, database = (
        quote(values[key], safe="") for key in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
    )
    return f"postgresql+psycopg://{user}:{password}@127.0.0.1:{values['POSTGRES_PORT']}/{database}"


def demo_password(length: int = 20) -> str:
    """Contrasena de las cuentas demo: la misma regla que app.core.passwords.generate_password (letras, digitos y un
    caracter especial garantizados). El script no importa app/: corre antes de que el .env exista."""
    alphabet = string.ascii_letters + string.digits
    body = [secrets.choice(alphabet) for _ in range(length - 3)]
    body += [secrets.choice(string.ascii_letters), secrets.choice(string.digits), secrets.choice("#$%&*+-=?@_")]
    secrets.SystemRandom().shuffle(body)
    return "".join(body)


def create_env(root: Path = ROOT) -> list[str]:
    """Crea o completa .env. Devuelve la descripcion de cada cambio; lista vacia si el archivo no cambio."""
    env_file = root / ".env"
    created = not env_file.exists()
    lines = (root / ".env.example" if created else env_file).read_text(encoding="utf-8").splitlines()
    values = parse_env(lines)
    changes = ["creado a partir de .env.example"] if created else []

    def fill(key: str, value: str, description: str) -> None:
        _set(lines, key, value)
        values[key] = value
        changes.append(description)

    if not values.get("SECRET_KEY"):
        fill("SECRET_KEY", secrets.token_urlsafe(64), "SECRET_KEY aleatoria generada")
    for key, default in POSTGRES_DEFAULTS.items():
        if not values.get(key):
            fill(key, default, f"{key}={default} agregada")
    if not values.get("POSTGRES_PASSWORD"):
        # token_urlsafe solo usa [A-Za-z0-9_-]: es segura dentro de la URL.
        fill("POSTGRES_PASSWORD", secrets.token_urlsafe(32), "POSTGRES_PASSWORD aleatoria generada")
    url = values.get("DATABASE_URL", "")
    if url.startswith("sqlite"):
        fill("DATABASE_URL", database_url(values), SQLITE_WARNING)
    elif not url:
        fill("DATABASE_URL", database_url(values), "DATABASE_URL de PostgreSQL agregada")

    for key, default in KEYCLOAK_DEFAULTS.items():
        if not values.get(key):
            fill(key, default, f"{key}={default} agregada")
    if not values.get("KEYCLOAK_SERVER_URL"):
        server_url = f"http://127.0.0.1:{values['KEYCLOAK_PORT']}"
        fill("KEYCLOAK_SERVER_URL", server_url, f"KEYCLOAK_SERVER_URL={server_url} agregada")
    for key in KEYCLOAK_SECRETS:
        if not values.get(key):
            fill(key, secrets.token_urlsafe(48), f"{key} aleatoria generada")
    if not values.get("DEMO_PASSWORD"):
        fill("DEMO_PASSWORD", demo_password(), "DEMO_PASSWORD aleatoria generada")

    if changes:
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changes


if __name__ == "__main__":
    changes = create_env()
    if not changes:
        print(".env ya esta completo; no se modifico.")
    for change in changes:
        print(change if change.startswith("AVISO") else f".env: {change}")
