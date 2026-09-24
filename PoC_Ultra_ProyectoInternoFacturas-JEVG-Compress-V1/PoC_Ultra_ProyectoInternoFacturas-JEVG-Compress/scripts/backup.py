"""Respaldo consistente de la BD y de storage/, con manifiesto SHA-256 y retencion (AUDITORIA BD-08).

La BD se copia con la API de respaldo en linea de SQLite: es consistente aunque la aplicacion este atendiendo
peticiones y con WAL activo. Uso: python scripts/backup.py
"""

import hashlib
import json
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings

MANIFEST = "manifest.json"
STORAGE_ARCHIVE = "storage.zip"


def sqlite_files(db_path: Path) -> tuple[Path, Path, Path]:
    """La BD y sus archivos asociados en modo WAL: se borran o reemplazan siempre juntos."""
    return db_path, db_path.with_name(f"{db_path.name}-wal"), db_path.with_name(f"{db_path.name}-shm")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def alembic_revision(db_path: Path) -> str | None:
    with sqlite3.connect(db_path) as connection:
        try:
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.OperationalError:
            return None
    return row[0] if row else None


def _new_backup_dir(backups: Path, now: datetime) -> Path:
    stamp = now.strftime("%Y%m%d-%H%M%S")
    target, suffix = backups / stamp, 1
    while target.exists():
        target, suffix = backups / f"{stamp}-{suffix}", suffix + 1
    target.mkdir(parents=True)
    return target


def _copy_database(db_path: Path, destination: Path) -> None:
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(destination)
    try:
        with target:
            source.backup(target)
        # El respaldo debe ser un unico archivo autocontenido, sin -wal/-shm.
        target.execute("PRAGMA journal_mode=DELETE")
    finally:
        target.close()
        source.close()


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
    db_path: Path, storage: Path, backups: Path, retention: int | None, now: datetime | None = None
) -> Path:
    """Crea backups/<AAAAMMDD-HHMMSS>/ con la BD, storage.zip y manifest.json. retention=None no poda."""
    now = now or datetime.now(timezone.utc)
    target = _new_backup_dir(backups, now)
    database_copy = target / db_path.name
    _copy_database(db_path, database_copy)
    files = _archive_storage(storage, target / STORAGE_ARCHIVE)
    manifest = {
        "created_at": now.isoformat(),
        "alembic_revision": alembic_revision(database_copy),
        "database": {"file": database_copy.name, "sha256": sha256(database_copy)},
        "storage": {"file": STORAGE_ARCHIVE, "sha256": sha256(target / STORAGE_ARCHIVE), "files": files},
    }
    (target / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if retention is not None:
        prune(backups, retention)
    return target


def main() -> None:
    db_path = settings.sqlite_path
    if db_path is None:
        raise SystemExit("El respaldo solo admite SQLite en disco.")
    if not db_path.exists():
        raise SystemExit(f"No existe la base de datos {db_path}.")
    target = create_backup(db_path, settings.storage_path, settings.backup_dir, settings.backup_retention)
    print(f"Respaldo creado en {target}")


if __name__ == "__main__":
    main()
