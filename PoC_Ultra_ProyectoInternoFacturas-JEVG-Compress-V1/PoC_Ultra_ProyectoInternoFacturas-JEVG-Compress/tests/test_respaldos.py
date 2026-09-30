import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import engine
from scripts import pgtools
from scripts.backup import MANIFEST, create_backup
from scripts.restore_backup import restore_backup
from tests.conftest import ROOT, head_revision
from tests.idp import FakeKeycloak, FakeKeycloakServer

SESSION_DB = engine.url


def scalar(database: URL, sql: str):
    target = create_engine(database, poolclass=NullPool)
    try:
        with target.connect() as connection:
            return connection.scalar(text(sql))
    finally:
        target.dispose()


def execute(database: URL, sql: str) -> None:
    target = create_engine(database, poolclass=NullPool)
    try:
        with target.begin() as connection:
            connection.execute(text(sql))
    finally:
        target.dispose()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def storage_digests(storage: Path) -> dict[str, str]:
    return {str(p.relative_to(storage)): digest(p) for p in sorted(storage.rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def session_dump(tmp_path_factory) -> Path:
    """Volcado de la base de la sesion, para crear copias aisladas sin tocar la compartida."""
    path = tmp_path_factory.mktemp("volcado") / "sesion.dump"
    pgtools.dump(SESSION_DB, path)
    return path


@pytest.fixture()
def restored_copy(session_dump):
    """Crea, a pedido, bases temporales con el contenido de la sesion; se eliminan al terminar la prueba."""
    created = []

    def copy() -> URL:
        created.append(f"portal_test_bak_{secrets.token_hex(6)}")
        database = pgtools.create_database(created[-1])
        pgtools.restore(database, session_dump)
        return database

    yield copy
    for name in created:
        pgtools.drop_database(name)


@pytest.fixture()
def installation(tmp_path, restored_copy):
    """Copia aislada de la BD y el storage de la suite, para respaldar y restaurar sin tocar los compartidos."""
    storage = tmp_path / "storage"
    shutil.copytree(settings.storage_path, storage)
    for scope in ("invoices", "suppliers", "temp"):  # como en el repositorio
        (storage / scope).mkdir(exist_ok=True)
        (storage / scope / ".gitkeep").write_text("\n", encoding="utf-8")
    return restored_copy(), storage, tmp_path / "backups", restored_copy


def test_respaldo_consistente_con_una_escritura_abierta(tmp_path, restored_copy):
    with engine.connect() as writer:
        writer.execute(
            text("INSERT INTO audit_logs (action, entity, timestamp) VALUES ('NO_CONFIRMADO', 'X', now())")
        )  # sin confirmar mientras corre el respaldo
        backup = create_backup(SESSION_DB, settings.storage_path, tmp_path / "backups", retention=14)
        writer.rollback()
    dump = backup / f"{SESSION_DB.database}.dump"
    assert "TABLE DATA public invoices" in pgtools.list_dump(dump)
    copy = restored_copy()
    pgtools.restore(copy, dump)
    assert scalar(copy, "SELECT count(*) FROM invoices") == scalar(SESSION_DB, "SELECT count(*) FROM invoices")
    assert scalar(copy, "SELECT count(*) FROM audit_logs WHERE action = 'NO_CONFIRMADO'") == 0
    manifest = json.loads((backup / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["database"]["sha256"] == digest(dump)
    assert manifest["storage"]["sha256"] == digest(backup / "storage.zip")
    assert manifest["alembic_revision"] == head_revision()
    assert manifest["server_version"] == pgtools.server_version()
    assert manifest["storage"]["files"] > 0


def test_retencion(installation):
    database, storage, backups, _copy = installation
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    for index in range(14):  # respaldos previos (solo cuenta el manifiesto)
        folder = backups / (start + timedelta(hours=index)).strftime("%Y%m%d-%H%M%S")
        folder.mkdir(parents=True)
        (folder / MANIFEST).write_text("{}", encoding="utf-8")
    create_backup(database, storage, backups, retention=14, now=start + timedelta(hours=14))
    remaining = sorted(path.name for path in backups.iterdir())
    assert len(remaining) == 14
    assert remaining[0] == "20260901-010000"
    assert remaining[-1] == "20260901-140000"


def test_respaldo_fallido_no_deja_directorios(installation, monkeypatch):
    database, storage, backups, _copy = installation

    def failing_dump(*_args):
        raise RuntimeError("pg_dump fallo")

    monkeypatch.setattr(pgtools, "dump", failing_dump)
    with pytest.raises(RuntimeError, match="pg_dump fallo"):
        create_backup(database, storage, backups, retention=14)
    assert list(backups.iterdir()) == []


def test_restauracion_con_manifiesto_alterado(installation):
    database, storage, backups, _copy = installation
    backup = create_backup(database, storage, backups, retention=14)
    with (backup / f"{database.database}.dump").open("ab") as handle:
        handle.write(b"alterado")
    execute(database, "DELETE FROM validation_results")
    before = storage_digests(storage)
    with pytest.raises(RuntimeError, match="no coincide"):
        restore_backup(backup, database, storage, backups, confirm=True)
    assert scalar(database, "SELECT count(*) FROM validation_results") == 0
    assert storage_digests(storage) == before
    assert len(list(backups.iterdir())) == 1  # sin respaldo de seguridad: no se llego a modificar nada


def test_restauracion_exige_confirmacion(installation):
    database, storage, backups, _copy = installation
    backup = create_backup(database, storage, backups, retention=14)
    with pytest.raises(RuntimeError, match="--yes"):
        restore_backup(backup, database, storage, backups, confirm=False)


def test_restauracion_completa(installation):
    database, storage, backups, copy = installation
    backup = create_backup(database, storage, backups, retention=14)
    results = scalar(database, "SELECT count(*) FROM validation_results")
    victim = next(path for path in storage.rglob("*") if path.is_file() and path.name != ".gitkeep")
    content = victim.read_bytes()
    execute(database, "DELETE FROM validation_results")
    victim.unlink()
    (storage / "invoices" / "intruso.txt").write_text("no deberia sobrevivir", encoding="utf-8")

    safety = restore_backup(backup, database, storage, backups, confirm=True)

    assert scalar(database, "SELECT count(*) FROM validation_results") == results
    assert victim.read_bytes() == content
    assert not (storage / "invoices" / "intruso.txt").exists()
    assert (storage / "invoices" / ".gitkeep").exists()
    # Cada documento registrado sigue siendo descargable: su archivo existe y coincide con el hash guardado.
    target = create_engine(database, poolclass=NullPool)
    with target.connect() as connection:
        documents = connection.execute(text("SELECT path, sha256 FROM documents")).all()
    target.dispose()
    assert documents
    assert all(digest(storage / path) == expected for path, expected in documents)
    # El respaldo de seguridad conserva el estado previo a la restauracion (sin validaciones).
    previous = copy()
    pgtools.restore(previous, safety / f"{database.database}.dump")
    assert scalar(previous, "SELECT count(*) FROM validation_results") == 0


def test_restauracion_rechaza_zip_slip(installation):
    database, storage, backups, _copy = installation
    backup = create_backup(database, storage, backups, retention=14)
    with zipfile.ZipFile(backup / "storage.zip", "w") as archive:
        archive.writestr("../fuera.txt", "x")
    manifest = json.loads((backup / MANIFEST).read_text(encoding="utf-8"))
    manifest["storage"]["sha256"] = digest(backup / "storage.zip")
    (backup / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    execute(database, "DELETE FROM validation_results")
    with pytest.raises(RuntimeError, match="fuera de storage"):
        restore_backup(backup, database, storage, backups, confirm=True)
    assert not (storage.parent / "fuera.txt").exists()
    assert scalar(database, "SELECT count(*) FROM validation_results") == 0  # la BD no se toco


# --- reset_demo en un workspace aislado (subproceso con su propia configuracion y base temporal) ---------------


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


@pytest.fixture(scope="module")
def keycloak_server():
    """El seed del subproceso crea las cuentas demo en un Keycloak simulado local (127.0.0.1), no en el de la sesion."""
    with FakeKeycloakServer(FakeKeycloak()) as server:
        yield server


@pytest.fixture()
def workspace(tmp_path, keycloak_server):
    ws = tmp_path / "ws"
    with pgtools.temporary_database("portal_test_reset_") as database:
        env = {
            **os.environ,
            "APP_ENV": "development",
            "DATABASE_URL": pgtools.url_string(database),
            "STORAGE_PATH": str(ws / "storage"),
            "BACKUP_DIR": str(tmp_path / "backups"),
            "LOG_DIR": str(tmp_path / "logs"),
            "KEYCLOAK_SERVER_URL": keycloak_server.url,
            "DEMO_PASSWORD": "Demo#Prueba2026x",
        }
        run(env, "init_db.py")
        execute(
            database,
            "INSERT INTO users (name, email, password_hash, role, is_active, created_at) "
            "VALUES ('Ana', 'ana@ultrasist.com.mx', 'x', 'PMO', true, now())",
        )
        yield ws, env, tmp_path / "backups", database


def ana_exists(database: URL) -> bool:
    return scalar(database, "SELECT count(*) FROM users WHERE email = 'ana@ultrasist.com.mx'") == 1


def test_reset_sin_terminal_ni_confirmacion_aborta(workspace):
    ws, env, backups, database = workspace
    result = run(env, "reset_demo.py", "--workspace", str(ws), check=False)
    assert result.returncode == 1
    assert "ana@ultrasist.com.mx" in result.stdout
    assert ana_exists(database)
    assert not backups.exists()


def test_reset_confirmado_respalda_y_reconstruye(workspace):
    ws, env, backups, database = workspace
    result = run(env, "reset_demo.py", "--yes", "--workspace", str(ws))
    assert "Respaldo previo" in result.stdout
    assert len(list(backups.iterdir())) == 1
    assert not ana_exists(database)
    assert scalar(database, "SELECT count(*) FROM invoices") == 12  # 11 nacionales y 1 internacional (HU-15)
    assert scalar(database, "SELECT version_num FROM alembic_version") == head_revision()


def test_reset_rechaza_rutas_fuera_del_workspace(workspace):
    ws, env, _backups, database = workspace
    result = run(env, "reset_demo.py", "--yes", check=False)  # workspace por defecto: la raiz del proyecto
    assert result.returncode != 0
    assert "fuera del workspace" in result.stderr
    assert ana_exists(database)


def test_reset_no_se_ejecuta_en_produccion(workspace):
    ws, env, _backups, database = workspace
    result = run({**env, "APP_ENV": "production"}, "reset_demo.py", "--yes", "--workspace", str(ws), check=False)
    assert result.returncode == 1
    assert ana_exists(database)


def test_reset_rechaza_un_servidor_no_local(tmp_path):
    env = {
        **os.environ,
        "APP_ENV": "development",
        "DATABASE_URL": "postgresql+psycopg://portal:secreto@db.ejemplo.com:5432/portal",
        "STORAGE_PATH": str(tmp_path / "storage"),
        "BACKUP_DIR": str(tmp_path / "backups"),
        "LOG_DIR": str(tmp_path / "logs"),
    }
    result = run(env, "reset_demo.py", "--yes", "--workspace", str(tmp_path), check=False)
    assert result.returncode == 1
    assert "db.ejemplo.com" in result.stdout
    assert not (tmp_path / "backups").exists()
