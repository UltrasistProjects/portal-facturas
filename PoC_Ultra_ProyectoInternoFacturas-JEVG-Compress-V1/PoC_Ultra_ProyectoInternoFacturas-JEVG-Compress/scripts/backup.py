"""Respaldo consistente de la BD y de storage/, con manifiesto SHA-256 y retencion (AUDITORIA BD-08).

La BD se vuelca con pg_dump en formato custom, dentro del contenedor `db` (misma version que el servidor; ver
scripts/pgtools.py). El volcado es una instantanea transaccional: es consistente aunque la aplicacion este atendiendo
peticiones. Uso: python scripts/backup.py
"""

import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool

from app.core.config import settings
from scripts import pgtools

MANIFEST = "manifest.json"
STORAGE_ARCHIVE = "storage.zip"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def alembic_revision(database: URL) -> str | None:
    engine = create_engine(database, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None:
                return None
            return connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        engine.dispose()


def _new_backup_dir(backups: Path, now: datetime) -> Path:
    stamp = now.strftime("%Y%m%d-%H%M%S")
    target, suffix = backups / stamp, 1
    while target.exists():
        target, suffix = backups / f"{stamp}-{suffix}", suffix + 1
    target.mkdir(parents=True)
    return target


def _archive_storage(storage: Path, destination: Path) -> int:
    count = 0
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        if storage.exists():
            for file in sorted(storage.rglob("*")):
                if file.is_file() and file.name != ".gitkeep":
                    archive.write(file, file.relative_to(storage).as_posix())
                    count += 1
    return count


def prune(backups: Path, retention: int) -> list[Path]:
    """Conserva los `retention` respaldos mas recientes (orden por nombre = orden cronologico)."""
    existing = sorted(d for d in backups.iterdir() if d.is_dir() and (d / MANIFEST).is_file())
    removed = existing[: max(0, len(existing) - retention)]
    for directory in removed:
        shutil.rmtree(directory)
    return removed


def create_backup(
    database: URL, storage: Path, backups: Path, retention: int | None, now: datetime | None = None
) -> Path:
    """Crea backups/<AAAAMMDD-HHMMSS>/ con el volcado, storage.zip y manifest.json. retention=None no poda."""
    now = now or datetime.now(timezone.utc)
    target = _new_backup_dir(backups, now)
    try:
        dump = target / f"{database.database}.dump"
        pgtools.dump(database, dump)
        pgtools.list_dump(dump, database)  # el volcado debe poder leerse antes de darlo por bueno
        files = _archive_storage(storage, target / STORAGE_ARCHIVE)
        manifest = {
            "created_at": now.isoformat(),
            "alembic_revision": alembic_revision(database),
            "server_version": pgtools.server_version(database),
            "database": {"file": dump.name, "format": "pg_dump custom", "sha256": sha256(dump)},
            "storage": {"file": STORAGE_ARCHIVE, "sha256": sha256(target / STORAGE_ARCHIVE), "files": files},
        }
        (target / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)  # sin manifiesto no es un respaldo: no se deja a medias
        raise
    if retention is not None:
        prune(backups, retention)
    return target


def main() -> None:
    database = make_url(settings.database_url)
    try:
        pgtools.check_database(database)
        target = create_backup(database, settings.storage_path, settings.backup_dir, settings.backup_retention)
    except RuntimeError as exc:
        raise SystemExit(f"Respaldo fallido: {exc}") from exc
    print(f"Respaldo creado en {target}")


if __name__ == "__main__":
    main()
