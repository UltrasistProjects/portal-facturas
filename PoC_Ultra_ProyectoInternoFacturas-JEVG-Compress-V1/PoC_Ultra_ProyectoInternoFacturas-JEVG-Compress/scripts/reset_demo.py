import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config

from app.core.config import settings


def assert_inside_workspace(path: Path) -> Path:
    resolved = path.resolve()
    if resolved != ROOT and ROOT not in resolved.parents:
        raise RuntimeError(f"Ruta fuera del workspace: {resolved}")
    return resolved


def main() -> None:
    if not settings.database_url.startswith("sqlite:///"):
        raise RuntimeError("reset_demo solo admite SQLite local")
    db_path = assert_inside_workspace(ROOT / settings.database_url.removeprefix("sqlite:///"))
    if db_path.exists():
        db_path.unlink()
    for relative in ("storage/invoices", "storage/suppliers", "storage/temp"):
        folder = assert_inside_workspace(ROOT / relative)
        if folder.exists():
            for child in folder.iterdir():
                if child.name != ".gitkeep":
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(config, "head")
    from scripts.seed_db import main as seed

    seed()
    print(f"Demo reconstruida en {db_path}")


if __name__ == "__main__":
    main()
