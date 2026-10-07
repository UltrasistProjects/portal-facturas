"""Restaura un respaldo creado por scripts/backup.py (AUDITORIA BD-08).

Detenga la aplicacion antes de restaurar: pg_restore --clean necesita bloquear las tablas.
Uso: python scripts/restore_backup.py backups/<AAAAMMDD-HHMMSS> --yes
"""

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy.engine import URL, make_url

from app.core.config import settings
from scripts import pgtools
from scripts.backup import MANIFEST, create_backup, sha256


def _check_archive(archive_path: Path, storage: Path) -> None:
    """Rechaza entradas que se extraerian fuera de storage/ (zip slip)."""
    root = storage.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.namelist():
            if root not in (root / member).resolve().parents:
                raise RuntimeError(f"Entrada fuera de storage en el respaldo: {member}")


def verify_backup(backup_dir: Path, storage: Path) -> dict:
    """Comprueba el respaldo completo antes de modificar nada: SHA-256, volcado legible y archivo de storage."""
    manifest = json.loads((backup_dir / MANIFEST).read_text(encoding="utf-8"))
    for artifact in (manifest["database"], manifest["storage"]):
        path = backup_dir / artifact["file"]
        if not path.is_file() or sha256(path) != artifact["sha256"]:
            raise RuntimeError(f"{artifact['file']} no coincide con el SHA-256 del manifiesto; restauracion abortada.")
    _check_archive(backup_dir / manifest["storage"]["file"], storage)
    return manifest


def _clear_storage(storage: Path) -> None:
    if not storage.exists():
        return
    for child in storage.iterdir():
        if child.is_dir():
            for file in [p for p in child.rglob("*") if p.is_file() and p.name != ".gitkeep"]:
                file.unlink()
            for folder in sorted((p for p in child.rglob("*") if p.is_dir()), reverse=True):
                if not any(folder.iterdir()):
                    folder.rmdir()
        elif child.name != ".gitkeep":
            child.unlink()


def _extract_storage(archive_path: Path, storage: Path) -> None:
    _check_archive(archive_path, storage)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(storage.resolve())


def restore_backup(backup_dir: Path, database: URL, storage: Path, backups: Path, confirm: bool) -> Path:
    """Verifica, respalda el estado actual y restaura. Devuelve el respaldo de seguridad."""
    if not confirm:
        raise RuntimeError("La restauracion reemplaza la BD y storage/: confirme con --yes.")
    manifest = verify_backup(backup_dir, storage)
    # Sin poda: la retencion podria eliminar justo el respaldo que se esta restaurando.
    safety = create_backup(database, storage, backups, retention=None)
    # Una sola transaccion: si pg_restore falla, la BD queda como estaba y storage/ no se toca.
    pgtools.restore(database, backup_dir / manifest["database"]["file"])
    _clear_storage(storage)
    storage.mkdir(parents=True, exist_ok=True)
    _extract_storage(backup_dir / manifest["storage"]["file"], storage)
    return safety


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup_dir", type=Path)
    parser.add_argument("--yes", action="store_true", help="confirma el reemplazo de la BD y de storage/")
    args = parser.parse_args()
    database = make_url(settings.database_url)
    try:
        pgtools.check_database(database)
        safety = restore_backup(args.backup_dir, database, settings.storage_path, settings.backup_dir, args.yes)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Estado previo respaldado en {safety}")
    print(f"Respaldo {args.backup_dir} restaurado.")


if __name__ == "__main__":
    main()
