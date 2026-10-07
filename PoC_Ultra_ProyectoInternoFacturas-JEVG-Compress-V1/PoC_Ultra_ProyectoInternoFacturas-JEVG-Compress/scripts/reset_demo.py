"""Reconstruye la BD y storage/ con los datos demo. Borra datos: respalda antes y pide confirmacion ante datos reales.

Solo actua sobre un PostgreSQL local (localhost, 127.0.0.1 o ::1) y nunca con APP_ENV=production. Detenga la
aplicacion antes: recrear el esquema necesita bloquear las tablas.
Uso: python scripts/reset_demo.py [--yes] [--workspace DIR]
"""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.demo import DEMO_EMAIL_DOMAIN
from scripts import pgtools
from scripts.backup import create_backup

CONFIRMATION_WORD = "REINICIAR"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def assert_inside(path: Path, workspace: Path) -> Path:
    resolved = path.resolve()
    if resolved != workspace and workspace not in resolved.parents:
        raise RuntimeError(f"Ruta fuera del workspace {workspace}: {resolved}")
    return resolved


def is_local(database: URL) -> bool:
    """Sin host, libpq usa el socket local."""
    return (database.host or "localhost") in LOCAL_HOSTS


def non_demo_data(database: URL) -> list[str]:
    """Motivos por los que la BD contiene datos que no provienen del seed demo."""
    engine = create_engine(database, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT to_regclass('public.users')")) is None:  # BD sin esquema
                return []
            users = connection.scalars(
                text("SELECT email FROM users WHERE email NOT LIKE :domain ORDER BY id"),
                {"domain": f"%{DEMO_EMAIL_DOMAIN}"},
            ).all()
            invoices = connection.scalar(
                text(
                    "SELECT count(*) FROM invoices WHERE CAST(id AS TEXT) NOT IN "
                    "(SELECT entity_id FROM audit_logs WHERE action = 'DEMO_SEEDED' AND entity = 'Invoice' "
                    "AND entity_id IS NOT NULL)"
                )
            )
    finally:
        engine.dispose()
    reasons = []
    if users:
        reasons.append(f"usuarios fuera de {DEMO_EMAIL_DOMAIN}: {', '.join(users[:5])}")
    if invoices:
        reasons.append(f"{invoices} facturas que no provienen del seed demo")
    return reasons


def confirmed(reasons: list[str], yes: bool) -> bool:
    if not reasons or yes:
        return True
    print("La base contiene datos que no son demo:\n- " + "\n- ".join(reasons))
    if not sys.stdin.isatty():
        print("Sin terminal interactiva: use --yes para confirmar el reinicio.")
        return False
    return (
        input(f"Se respaldaran y eliminaran. Escriba {CONFIRMATION_WORD} para continuar: ").strip() == CONFIRMATION_WORD
    )


def recreate_schema(database: URL) -> None:
    engine = create_engine(database, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            # Si la aplicacion sigue conectada, falla en lugar de esperar indefinidamente sus bloqueos.
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


def reset_demo(yes: bool = False, workspace: Path = ROOT) -> int:
    if settings.app_env == "production":
        print("reset_demo no se ejecuta con APP_ENV=production.")
        return 1
    database = make_url(settings.database_url)
    if not is_local(database):
        print(f"reset_demo solo actua sobre un PostgreSQL local; DATABASE_URL apunta a {database.host}.")
        return 1
    workspace = workspace.resolve()
    storage = assert_inside(settings.storage_path, workspace)
    pgtools.check_database(database)
    if not confirmed(non_demo_data(database), yes):
        print("Reinicio cancelado; no se borro nada.")
        return 1
    print(f"Respaldo previo en {create_backup(database, storage, settings.backup_dir, settings.backup_retention)}")
    recreate_schema(database)
    for scope in ("invoices", "suppliers", "temp"):
        folder = storage / scope
        if folder.exists():
            for child in folder.iterdir():
                if child.name != ".gitkeep":
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
    config = Config()
    config.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(config, "head")
    from scripts.seed_db import main as seed

    seed()
    print(f"Demo reconstruida en la base {database.database} de {database.host}:{database.port or 5432}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="confirma el reinicio aunque existan datos no-demo")
    parser.add_argument(
        "--workspace", type=Path, default=ROOT, help="directorio dentro del cual se permite borrar (por defecto: raiz)"
    )
    args = parser.parse_args()
    try:
        code = reset_demo(args.yes, args.workspace)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    raise SystemExit(code)


if __name__ == "__main__":
    main()
