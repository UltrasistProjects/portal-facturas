"""Reconstruye la BD y storage/ con los datos demo. Borra datos: respalda antes y pide confirmacion ante datos reales.

Uso: python scripts/reset_demo.py [--yes] [--workspace DIR]
"""

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config

from app.core.config import settings
from app.core.demo import DEMO_EMAIL_DOMAIN
from scripts.backup import create_backup, sqlite_files

CONFIRMATION_WORD = "REINICIAR"


def assert_inside(path: Path, workspace: Path) -> Path:
    resolved = path.resolve()
    if resolved != workspace and workspace not in resolved.parents:
        raise RuntimeError(f"Ruta fuera del workspace {workspace}: {resolved}")
    return resolved


def non_demo_data(db_path: Path) -> list[str]:
    """Motivos por los que la BD contiene datos que no provienen del seed demo."""
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as connection:
        try:
            users = [
                email
                for (email,) in connection.execute(
                    "SELECT email FROM users WHERE email NOT LIKE ?", (f"%{DEMO_EMAIL_DOMAIN}",)
                )
            ]
            (invoices,) = connection.execute(
                "SELECT count(*) FROM invoices WHERE CAST(id AS TEXT) NOT IN "
                "(SELECT entity_id FROM audit_logs WHERE action = 'DEMO_SEEDED' AND entity = 'Invoice')"
            ).fetchone()
        except sqlite3.OperationalError:  # BD sin esquema
            return []
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


def reset_demo(yes: bool = False, workspace: Path = ROOT) -> int:
    if settings.app_env == "production":
        print("reset_demo no se ejecuta con APP_ENV=production.")
        return 1
    db_path = settings.sqlite_path
    if db_path is None:
        print("reset_demo solo admite SQLite en disco.")
        return 1
    workspace = workspace.resolve()
    db_path = assert_inside(db_path, workspace)
    storage = assert_inside(settings.storage_path, workspace)
    if not confirmed(non_demo_data(db_path), yes):
        print("Reinicio cancelado; no se borro nada.")
        return 1
    if db_path.exists():
        print(f"Respaldo previo en {create_backup(db_path, storage, settings.backup_dir, settings.backup_retention)}")
    for path in sqlite_files(db_path):
        path.unlink(missing_ok=True)
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
    print(f"Demo reconstruida en {db_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="confirma el reinicio aunque existan datos no-demo")
    parser.add_argument(
        "--workspace", type=Path, default=ROOT, help="directorio dentro del cual se permite borrar (por defecto: raiz)"
    )
    args = parser.parse_args()
    raise SystemExit(reset_demo(args.yes, args.workspace))


if __name__ == "__main__":
    main()
