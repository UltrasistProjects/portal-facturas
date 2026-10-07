"""Verificaciones de calidad del proyecto en un solo comando: ruff, formato, migraciones, pruebas con umbral de
cobertura (genera coverage.xml para SonarQube) y pip-audit. Termina con codigo distinto de cero si alguna falla.

alembic check y pytest necesitan un PostgreSQL alcanzable (docker compose up -d --wait db, o TEST_DATABASE_URL).

Uso: python scripts/check.py [--skip-audit]   (--skip-audit para trabajar sin conexion)
"""

import argparse
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import pgtools

ALEMBIC_CHECK = (
    "from alembic import command; from alembic.config import Config;"
    "c = Config(); c.set_main_option('script_location', 'alembic');"
    "command.upgrade(c, 'head'); command.check(c)"
)


def steps(skip_audit: bool) -> list[tuple[str, list[str]]]:
    python = sys.executable
    result = [
        ("ruff check", [python, "-m", "ruff", "check", "."]),
        ("ruff format --check", [python, "-m", "ruff", "format", "--check", "."]),
        ("alembic check", [python, "-c", ALEMBIC_CHECK]),
        ("pytest + cobertura", [python, "-m", "pytest", "-p", "no:cacheprovider"]),
    ]
    if not skip_audit:
        result.append(
            ("pip-audit", [python, "-m", "pip_audit", "-r", "requirements.lock", "--progress-spinner", "off"])
        )
    return result


def run_step(name: str, command: list[str], env: dict[str, str]) -> bool:
    if name != "alembic check":
        return subprocess.run(command, cwd=ROOT, env=env).returncode == 0
    # alembic check necesita una BD en head: se usa una base temporal del servidor de pruebas, nunca la de trabajo,
    # y se elimina al terminar aunque el paso falle.
    try:
        with pgtools.temporary_database("portal_test_check_") as url:
            return (
                subprocess.run(command, cwd=ROOT, env={**env, "DATABASE_URL": pgtools.url_string(url)}).returncode == 0
            )
    except RuntimeError as exc:  # servidor no disponible
        print(exc)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-audit", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="check_") as tmp:
        env = {
            **os.environ,
            "SECRET_KEY": os.environ.get("SECRET_KEY") or secrets.token_urlsafe(64),
            "LOG_DIR": str(Path(tmp) / "logs"),
            # alembic check importa la configuracion completa pero no llama a Keycloak: valores de relleno si faltan.
            "KEYCLOAK_SERVER_URL": os.environ.get("KEYCLOAK_SERVER_URL") or "http://127.0.0.1:58080",
            "KEYCLOAK_REALM": os.environ.get("KEYCLOAK_REALM") or "ultrasist-portal",
            "KEYCLOAK_CLIENT_SECRET": os.environ.get("KEYCLOAK_CLIENT_SECRET") or secrets.token_urlsafe(48),
            "KEYCLOAK_ADMIN_CLIENT_SECRET": os.environ.get("KEYCLOAK_ADMIN_CLIENT_SECRET") or secrets.token_urlsafe(48),
        }
        failures = []
        for name, command in steps(args.skip_audit):
            print(f"\n=== {name}", flush=True)
            if not run_step(name, command, env):
                failures.append(name)
    print("\n" + ("FALLARON: " + ", ".join(failures) if failures else "Todas las verificaciones pasaron."))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
