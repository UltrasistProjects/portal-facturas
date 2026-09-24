import hashlib
import os
import re
import secrets
import shutil
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# La suite corre sobre una BD y un almacenamiento temporales. Las variables deben
# definirse antes de importar `app`, porque la configuracion se lee al importar.
TEST_ROOT = Path(tempfile.mkdtemp(prefix="portal_tests_"))
os.environ.update(
    {
        "SECRET_KEY": secrets.token_urlsafe(64),
        "APP_ENV": "test",
        "DEBUG": "false",
        "DATABASE_URL": f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}",
        "STORAGE_PATH": str(TEST_ROOT / "storage"),
        "LOG_DIR": str(TEST_ROOT / "logs"),
        # TestClient usa http://testserver; con cookie Secure no se enviaria la sesion.
        "SESSION_HTTPS_ONLY": "false",
    }
)

TEST_PASSWORDS = {
    "admin@poc.local": "Test#Admin2026",
    "pmo@poc.local": "Test#Pmo2026",
    "proveedor1@poc.local": "Test#Proveedor2026",
    "proveedor2@poc.local": "Test#Proveedor2026",
}


def _workspace_snapshot() -> dict[str, str]:
    """Huella de los datos de trabajo del proyecto, que la suite no debe tocar."""
    files = [p for p in (ROOT / "data").glob("*.db*") if p.is_file()]
    files += [p for p in (ROOT / "storage").rglob("*") if p.is_file()]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def alembic_config(database_url: str | None = None):
    """Config de Alembic sin alembic.ini: su fileConfig reconfiguraria el logging a mitad de la suite."""
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(ROOT / "alembic"))
    if database_url:
        config.attributes["database_url"] = database_url
    return config


@pytest.fixture(scope="session", autouse=True)
def test_database():
    before = _workspace_snapshot()
    from alembic import command

    command.upgrade(alembic_config(), "head")
    from scripts.seed_db import main as seed

    seed(passwords=TEST_PASSWORDS)
    yield
    from app.core.database import engine

    engine.dispose()
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
    assert _workspace_snapshot() == before, "La suite modifico data/ o storage/ del proyecto"


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def csrf(client, path: str = "/login") -> str:
    response = client.get(path)
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def login(client, email="admin@poc.local", password=None):
    password = TEST_PASSWORDS[email] if password is None else password
    return client.post(
        "/login", data={"email": email, "password": password, "csrf_token": csrf(client)}, follow_redirects=False
    )


def invoice_by_number(invoice_number: str):
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import Invoice

    with SessionLocal() as db:
        return db.scalar(select(Invoice).where(Invoice.invoice_number == invoice_number))


def supplier_by_email(email: str):
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import Supplier

    with SessionLocal() as db:
        return db.scalar(select(Supplier).where(Supplier.email == email))
