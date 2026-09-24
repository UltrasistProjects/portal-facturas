"""Aplica las migraciones hasta head y siembra la demo sólo si la base está vacía. No borra datos."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import User


def main() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(config, "head")
    with SessionLocal() as db:
        empty = db.scalar(select(User.id).limit(1)) is None
    if empty:
        from scripts.seed_db import main as seed

        seed()
    print(
        "Base de datos en la ultima revision"
        + (" y sembrada con la demo." if empty else "; datos existentes conservados.")
    )


if __name__ == "__main__":
    main()
