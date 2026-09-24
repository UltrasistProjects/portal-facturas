"""Verificaciones de calidad del proyecto en un solo comando: ruff, formato, migraciones, pruebas con umbral de
cobertura (genera coverage.xml para SonarQube) y pip-audit. Termina con codigo distinto de cero si alguna falla.

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-audit", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="check_") as tmp:
        # alembic check necesita una BD en head y una SECRET_KEY: se usa una BD temporal, nunca la de trabajo.
        env = {
            **os.environ,
            "SECRET_KEY": os.environ.get("SECRET_KEY") or secrets.token_urlsafe(64),
            "DATABASE_URL": f"sqlite:///{(Path(tmp) / 'check.db').as_posix()}",
            "LOG_DIR": str(Path(tmp) / "logs"),
        }
        failures = []
        for name, command in steps(args.skip_audit):
            print(f"\n=== {name}", flush=True)
            if subprocess.run(command, cwd=ROOT, env=env).returncode != 0:
                failures.append(name)
    print("\n" + ("FALLARON: " + ", ".join(failures) if failures else "Todas las verificaciones pasaron."))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
