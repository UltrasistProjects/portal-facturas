"""Restaura un respaldo creado por scripts/backup.py (AUDITORIA BD-08).

Detenga la aplicacion antes de restaurar. Uso: python scripts/restore_backup.py backups/<AAAAMMDD-HHMMSS> --yes
"""

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from scripts.backup import MANIFEST, create_backup, sha256, sqlite_files


def verify_backup(backup_dir: Path) -> dict:
    manifest = json.loads((backup_dir / MANIFEST).read_text(encoding="utf-8"))
    for artifact in (manifest["database"], manifest["storage"]):
        path = backup_dir / artifact["file"]
        if not path.is_file() or sha256(path) != artifact["sha256"]:
            raise RuntimeError(f"{artifact['file']} no coincide con el SHA-256 del manifiesto; restauracion abortada.")
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
    root = storage.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.namelist():
            target = (root / member).resolve()
            if root not in target.parents:  # evita zip slip
                raise RuntimeError(f"Entrada fuera de storage en el respaldo: {member}")
        archive.extractall(root)


def restore_backup(backup_dir: Path, db_path: Path, storage: Path, backups: Path, confirm: bool) -> Path | None:
    """Verifica, respalda el estado actual y restaura. Devuelve el respaldo de seguridad (None si no habia BD)."""
    if not confirm:
        raise RuntimeError("La restauracion reemplaza la BD y storage/: confirme con --yes.")
    manifest = verify_backup(backup_dir)
    # Sin poda: la retencion podria eliminar justo el respaldo que se esta restaurando.
    safety = create_backup(db_path, storage, backups, retention=None) if db_path.exists() else None
    for path in sqlite_files(db_path):
        path.unlink(missing_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(backup_dir / manifest["database"]["file"], db_path)
    _clear_storage(storage)
    storage.mkdir(parents=True, exist_ok=True)
    _extract_storage(backup_dir / manifest["storage"]["file"], storage)
    return safety


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup_dir", type=Path)
    parser.add_argument("--yes", action="store_true", help="confirma el reemplazo de la BD y de storage/")
    args = parser.parse_args()
    if settings.sqlite_path is None:
        raise SystemExit("La restauracion solo admite SQLite en disco.")
    try:
        safety = restore_backup(
            args.backup_dir, settings.sqlite_path, settings.storage_path, settings.backup_dir, args.yes
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    if safety:
        print(f"Estado previo respaldado en {safety}")
    print(f"Respaldo {args.backup_dir} restaurado.")


if __name__ == "__main__":
    main()
