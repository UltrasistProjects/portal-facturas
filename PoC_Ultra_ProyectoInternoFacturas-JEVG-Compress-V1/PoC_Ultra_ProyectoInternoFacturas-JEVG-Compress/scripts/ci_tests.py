"""Pruebas en CI: levanta un PostgreSQL desechable (servicio `db` de compose.yaml), ejecuta pytest contra el y lo
elimina con su volumen al terminar, tambien si las pruebas fallan o el job se cancela.

El runner no tiene .env ni contenedor `db` propio. El servidor corre en un proyecto de compose con nombre aleatorio y
en un puerto libre, asi que no choca con el entorno de desarrollo del mismo equipo ni con otro job. Las variables se
pasan por el entorno, que tiene prioridad sobre .env; COMPOSE_PROJECT_NAME tambien llega a las pruebas de respaldo
(PG_CLIENT=docker), cuyo `docker compose exec db` usa este contenedor.

Uso: python scripts/ci_tests.py [argumentos de pytest]
"""

import os
import secrets
import signal
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "compose.yaml"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main(pytest_args: list[str]) -> int:
    project = f"portal-facturas-ci-{secrets.token_hex(4)}"
    user, database, password, port = "portal", "portal", secrets.token_hex(24), free_port()
    env = {
        **os.environ,
        "COMPOSE_PROJECT_NAME": project,
        "POSTGRES_USER": user,
        "POSTGRES_DB": database,
        "POSTGRES_PASSWORD": password,
        "POSTGRES_PORT": str(port),
        "TEST_DATABASE_URL": f"postgresql+psycopg://{user}:{password}@127.0.0.1:{port}/{database}",
    }
    compose = ["docker", "compose", "-f", str(COMPOSE_FILE), "-p", project]
    # Al cancelar el job llega SIGTERM: SystemExit deja correr el finally que elimina el contenedor.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        subprocess.run([*compose, "up", "-d", "--wait", "db"], env=env, check=True)
        return subprocess.run([sys.executable, "-m", "pytest", *pytest_args], cwd=ROOT, env=env).returncode
    except subprocess.CalledProcessError as exc:
        print(f"No se pudo levantar PostgreSQL con docker compose (codigo {exc.returncode}).", file=sys.stderr)
        return exc.returncode
    finally:
        subprocess.run([*compose, "down", "-v", "--remove-orphans"], env=env)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
