"""Utilidades de PostgreSQL compartidas por los scripts y las pruebas.

- Servidor y bases temporales: server_url(), check_server(), create_database(), drop_database() y
  temporary_database().
- Herramientas cliente: dump(), restore(), list_dump() y server_version(). Con PG_CLIENT=docker (por defecto)
  pg_dump/pg_restore corren dentro del contenedor `db` de compose.yaml: misma version que el servidor (el pg_dump del
  host puede ser mas antiguo y negarse a respaldarlo), autenticacion local por socket y sin clientes en el host. Con
  PG_CLIENT=local se usan los binarios del host sobre la URL (p. ej. un CI con un servicio PostgreSQL).
"""

import os
import re
import secrets
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "compose.yaml"
# Base que existe en todo servidor: desde ella se crean y eliminan las demas sin conectarse a la de trabajo.
MAINTENANCE_DATABASE = "postgres"
SERVER_HINT = "Levante el contenedor con `docker compose up -d --wait db` (en la raiz del proyecto)."
_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]{0,62}")


def server_url() -> URL:
    """TEST_DATABASE_URL o, si no existe, el DATABASE_URL del entorno o de .env."""
    raw = (
        os.environ.get("TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or dotenv_values(ROOT / ".env").get("DATABASE_URL")
    )
    if not raw:
        raise RuntimeError("No hay DATABASE_URL ni TEST_DATABASE_URL. Ejecute python scripts/create_env.py.")
    return make_url(raw)


def url_string(url: URL) -> str:
    """URL con la contrasena visible (str(URL) la oculta), para pasarla por el entorno a otro proceso."""
    return url.render_as_string(hide_password=False)


def database_url(name: str, url: URL | None = None) -> URL:
    """URL de la base `name` en el mismo servidor."""
    return (url or server_url()).set(database=name)


def _identifier(name: str) -> str:
    if not _IDENTIFIER.fullmatch(name):
        raise ValueError(f"Nombre de base de datos no permitido: {name!r}")
    return name


def _admin_engine(url: URL | None = None) -> Engine:
    # CREATE/DROP DATABASE no pueden ejecutarse dentro de una transaccion.
    return create_engine(
        database_url(MAINTENANCE_DATABASE, url),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"connect_timeout": 5},
    )


def _check(engine: Engine, url: URL) -> None:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        reason = str(exc.orig).strip().splitlines()[0] if exc.orig else ""
        raise RuntimeError(
            f"PostgreSQL no responde en {url.host}:{url.port or 5432} ({reason}). {SERVER_HINT}"
        ) from exc
    finally:
        engine.dispose()


def check_server(url: URL | None = None) -> None:
    """Falla con un mensaje claro si el servidor no acepta conexiones (sin conectarse a la base de `url`)."""
    url = url or server_url()
    _check(_admin_engine(url), url)


def check_database(url: URL) -> None:
    """Falla con un mensaje claro si no es posible conectarse a la base de `url`."""
    _check(create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 5}), url)


def create_database(name: str, url: URL | None = None) -> URL:
    with _admin_engine(url).connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{_identifier(name)}"'))
    return database_url(name, url)


def drop_database(name: str, url: URL | None = None) -> None:
    """Elimina la base aunque tenga conexiones abiertas (WITH FORCE las termina)."""
    with _admin_engine(url).connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{_identifier(name)}" WITH (FORCE)'))


def databases(prefix: str, url: URL | None = None) -> list[str]:
    with _admin_engine(url).connect() as connection:
        rows = connection.execute(text("SELECT datname FROM pg_database WHERE starts_with(datname, :p)"), {"p": prefix})
        return sorted(name for (name,) in rows)


@contextmanager
def temporary_database(prefix: str = "portal_test_", url: URL | None = None) -> Iterator[URL]:
    """Crea una base vacia con nombre aleatorio y la elimina al salir, tambien si hubo un error."""
    name = f"{prefix}{secrets.token_hex(6)}"
    temporary = create_database(name, url)
    try:
        yield temporary
    finally:
        drop_database(name, url)


def server_version(url: URL | None = None) -> str:
    with _admin_engine(url).connect() as connection:
        return connection.execute(text("SHOW server_version")).scalar_one()


# --- Herramientas cliente (pg_dump / pg_restore) -------------------------------------------------------------


def _client_mode() -> str:
    mode = os.environ.get("PG_CLIENT", "docker").strip().lower()
    if mode not in {"docker", "local"}:
        raise RuntimeError(f"PG_CLIENT debe ser 'docker' o 'local', no {mode!r}.")
    return mode


def _run_client(tool: list[str], url: URL, *, stdin=None, stdout=None) -> bytes:
    """Ejecuta pg_dump/pg_restore contra la base de `url` y devuelve su salida estandar."""
    if _client_mode() == "docker":
        command = ["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "db", *tool, "-U", url.username]
        env = None
    else:
        command = list(tool)
        # La contrasena va por el entorno, no en la linea de comandos (visible en la lista de procesos).
        env = {
            **os.environ,
            "PGHOST": url.host or "localhost",
            "PGPORT": str(url.port or 5432),
            "PGUSER": url.username or "",
            "PGPASSWORD": url.password or "",
        }
    try:
        result = subprocess.run(
            command, stdin=stdin, stdout=stdout or subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=True
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"No se encontro {command[0]}. Con PG_CLIENT={_client_mode()} debe estar instalado."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"{tool[0]} fallo (codigo {exc.returncode}): {detail}") from exc
    return result.stdout or b""


def dump(database: URL, destination: Path) -> None:
    """Volcado en formato custom (-Fc): instantanea transaccional consistente aunque la aplicacion este en uso."""
    with destination.open("wb") as handle:
        _run_client(["pg_dump", "--format=custom", f"--dbname={database.database}"], database, stdout=handle)


def restore(database: URL, source: Path) -> None:
    """Reemplaza el contenido de la base con el volcado, en una sola transaccion: si algo falla no cambia nada."""
    with source.open("rb") as handle:
        _run_client(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--single-transaction",
                "--no-owner",
                f"--dbname={database.database}",
            ],
            database,
            stdin=handle,
        )


def list_dump(path: Path, url: URL | None = None) -> str:
    """Tabla de contenido del volcado (pg_restore --list); falla si el archivo no es un volcado legible."""
    with path.open("rb") as handle:
        return _run_client(["pg_restore", "--list"], url or server_url(), stdin=handle).decode(errors="replace")
