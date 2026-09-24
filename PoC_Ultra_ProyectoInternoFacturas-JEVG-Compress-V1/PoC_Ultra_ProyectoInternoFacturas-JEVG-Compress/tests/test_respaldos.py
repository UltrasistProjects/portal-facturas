import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.database import engine
from scripts.backup import MANIFEST, create_backup, sqlite_files
from scripts.restore_backup import restore_backup
from tests.conftest import ROOT

SHARED_DB = Path(engine.url.database)


def count(db: Path, sql: str) -> int:
    with sqlite3.connect(db) as connection:
        return connection.execute(sql).fetchone()[0]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def installation(tmp_path):
    """Copia aislada de la BD y el storage de la suite, para respaldar y restaurar sin tocar los compartidos."""
    db_path = tmp_path / "data" / "portal.db"
    db_path.parent.mkdir()
    source, target = sqlite3.connect(SHARED_DB), sqlite3.connect(db_path)
    source.backup(target)
    source.close()
    target.close()
    storage = tmp_path / "storage"
    shutil.copytree(settings.storage_path, storage)
    for scope in ("invoices", "suppliers", "temp"):  # como en el repositorio
        (storage / scope).mkdir(exist_ok=True)
        (storage / scope / ".gitkeep").write_text("\n", encoding="utf-8")
    return db_path, storage, tmp_path / "backups"


def test_respaldo_consistente_con_una_escritura_abierta(tmp_path):
    writer = sqlite3.connect(SHARED_DB, isolation_level=None)
    try:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO audit_logs (action, entity, timestamp) VALUES ('NO_CONFIRMADO', 'X', '2026-01-01')")
        backup = create_backup(SHARED_DB, settings.storage_path, tmp_path / "backups", retention=14)
    finally:
        writer.execute("ROLLBACK")
        writer.close()
    copy = backup / SHARED_DB.name
    with sqlite3.connect(copy) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert count(copy, "SELECT count(*) FROM invoices") == count(SHARED_DB, "SELECT count(*) FROM invoices")
    assert count(copy, "SELECT count(*) FROM audit_logs WHERE action = 'NO_CONFIRMADO'") == 0
    manifest = json.loads((backup / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["database"]["sha256"] == digest(copy)
    assert manifest["storage"]["sha256"] == digest(backup / "storage.zip")
    assert manifest["alembic_revision"]
    assert manifest["storage"]["files"] > 0


def test_retencion(installation):
    db_path, storage, backups = installation
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    for index in range(16):
        create_backup(db_path, storage, backups, retention=14, now=start + timedelta(hours=index))
    remaining = sorted(path.name for path in backups.iterdir())
    assert len(remaining) == 14
    assert remaining[0] == "20260901-020000"


def test_restauracion_con_manifiesto_alterado(installation):
    db_path, storage, backups = installation
    backup = create_backup(db_path, storage, backups, retention=14)
    with (backup / db_path.name).open("ab") as handle:
        handle.write(b"alterado")
    before = digest(db_path)
    with pytest.raises(RuntimeError, match="no coincide"):
        restore_backup(backup, db_path, storage, backups, confirm=True)
    assert digest(db_path) == before


def test_restauracion_exige_confirmacion(installation):
    db_path, storage, backups = installation
    backup = create_backup(db_path, storage, backups, retention=14)
    with pytest.raises(RuntimeError, match="--yes"):
        restore_backup(backup, db_path, storage, backups, confirm=False)


def test_restauracion_completa(installation):
    db_path, storage, backups = installation
    backup = create_backup(db_path, storage, backups, retention=14)
    results = count(db_path, "SELECT count(*) FROM validation_results")
    victim = next(path for path in storage.rglob("*") if path.is_file() and path.name != ".gitkeep")
    content = victim.read_bytes()
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM validation_results")
    victim.unlink()
    (storage / "invoices" / "intruso.txt").write_text("no deberia sobrevivir", encoding="utf-8")

    safety = restore_backup(backup, db_path, storage, backups, confirm=True)

    assert count(db_path, "SELECT count(*) FROM validation_results") == results
    assert victim.read_bytes() == content
    assert not (storage / "invoices" / "intruso.txt").exists()
    assert (storage / "invoices" / ".gitkeep").exists()
    assert count(safety / db_path.name, "SELECT count(*) FROM validation_results") == 0


def test_restauracion_rechaza_zip_slip(installation):
    db_path, storage, backups = installation
    backup = create_backup(db_path, storage, backups, retention=14)
    with zipfile.ZipFile(backup / "storage.zip", "w") as archive:
        archive.writestr("../fuera.txt", "x")
    manifest = json.loads((backup / MANIFEST).read_text(encoding="utf-8"))
    manifest["storage"]["sha256"] = digest(backup / "storage.zip")
    (backup / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="fuera de storage"):
        restore_backup(backup, db_path, storage, backups, confirm=True)
    assert not (storage.parent / "fuera.txt").exists()


def test_archivos_de_la_bd_en_modo_wal():
    db = Path("/datos/portal.db")
    assert sqlite_files(db) == (db, Path("/datos/portal.db-wal"), Path("/datos/portal.db-shm"))


# --- reset_demo en un workspace aislado (subproceso con su propia configuracion) ---------------------------


@pytest.fixture()
def workspace(tmp_path):
    ws = tmp_path / "ws"
    env = {
        **os.environ,
        "APP_ENV": "development",
        "DATABASE_URL": f"sqlite:///{(ws / 'data' / 'portal.db').as_posix()}",
        "STORAGE_PATH": str(ws / "storage"),
        "BACKUP_DIR": str(tmp_path / "backups"),
        "LOG_DIR": str(tmp_path / "logs"),
    }
    run(env, "init_db.py")
    with sqlite3.connect(ws / "data" / "portal.db") as connection:
        connection.execute(
            "INSERT INTO users (name, email, password_hash, role, is_active, created_at) "
            "VALUES ('Ana', 'ana@ultrasist.com.mx', 'x', 'INTERNAL', 1, '2026-09-01 00:00:00')"
        )
    return ws, env, tmp_path / "backups"


def run(env, script, *args, check=True):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        env=env,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=check,
    )


def ana_exists(ws) -> bool:
    return count(ws / "data" / "portal.db", "SELECT count(*) FROM users WHERE email = 'ana@ultrasist.com.mx'") == 1


def test_reset_sin_terminal_ni_confirmacion_aborta(workspace):
    ws, env, backups = workspace
    result = run(env, "reset_demo.py", "--workspace", str(ws), check=False)
    assert result.returncode == 1
    assert "ana@ultrasist.com.mx" in result.stdout
    assert ana_exists(ws)
    assert not backups.exists()


def test_reset_confirmado_respalda_y_reconstruye(workspace):
    ws, env, backups = workspace
    result = run(env, "reset_demo.py", "--yes", "--workspace", str(ws))
    assert "Respaldo previo" in result.stdout
    assert len(list(backups.iterdir())) == 1
    assert not ana_exists(ws)
    assert count(ws / "data" / "portal.db", "SELECT count(*) FROM invoices") == 10


def test_reset_rechaza_rutas_fuera_del_workspace(workspace):
    ws, env, _backups = workspace
    result = run(env, "reset_demo.py", "--yes", check=False)  # workspace por defecto: la raiz del proyecto
    assert result.returncode != 0
    assert "fuera del workspace" in result.stderr
    assert ana_exists(ws)


def test_reset_no_se_ejecuta_en_produccion(workspace):
    ws, env, _backups = workspace
    result = run({**env, "APP_ENV": "production"}, "reset_demo.py", "--yes", "--workspace", str(ws), check=False)
    assert result.returncode == 1
    assert ana_exists(ws)
