import hashlib
import os
import re
import secrets
import shutil
import tempfile
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from scripts import pgtools

ROOT = Path(__file__).resolve().parents[1]

# La suite corre sobre una base PostgreSQL temporal (portal_test_<aleatorio>) y un almacenamiento temporal. Las
# variables deben definirse antes de importar `app`, porque la configuracion se lee al importar. La base se crea al
# iniciar la sesion (fixture test_database) y se elimina al terminar, tambien si la sesion falla.
try:
    SERVER_URL = pgtools.server_url()
    SERVER_ERROR = None
except RuntimeError as exc:  # pytest_sessionstart cancela la sesion con este mensaje
    SERVER_URL, SERVER_ERROR = pgtools.make_url("postgresql+psycopg://sin-servidor/postgres"), exc

# Base de trabajo (la del .env o del entorno, nunca TEST_DATABASE_URL): la suite no debe tocarla.
_work = os.environ.get("DATABASE_URL") or dotenv_values(ROOT / ".env").get("DATABASE_URL")
WORK_URL = make_url(_work) if _work else None
TEST_DATABASE = f"portal_test_{secrets.token_hex(6)}"
TEST_ROOT = Path(tempfile.mkdtemp(prefix="portal_tests_"))
os.environ.update(
    {
        "SECRET_KEY": secrets.token_urlsafe(64),
        "APP_ENV": "test",
        "DEBUG": "false",
        "DATABASE_URL": pgtools.url_string(pgtools.database_url(TEST_DATABASE, SERVER_URL)),
        "STORAGE_PATH": str(TEST_ROOT / "storage"),
        "LOG_DIR": str(TEST_ROOT / "logs"),
        # TestClient usa http://testserver; con cookie Secure no se enviaria la sesion.
        "SESSION_HTTPS_ONLY": "false",
        # Ninguna prueba envia correos reales: el transporte de archivo escribe en el directorio temporal.
        "MAIL_BACKEND": "file",
        "MAIL_OUTBOX_DIR": str(TEST_ROOT / "outbox"),
    }
)
OUTBOX = TEST_ROOT / "outbox"


def pytest_sessionstart(session):
    """Antes de recolectar las pruebas (que importan `app`): sin servidor alcanzable, la sesion no empieza."""
    try:
        if SERVER_ERROR is not None:
            raise SERVER_ERROR
        pgtools.check_server(SERVER_URL)
    except RuntimeError as exc:
        pytest.exit(f"Pruebas canceladas: {exc} O defina TEST_DATABASE_URL con un servidor alcanzable.", returncode=3)


TEST_PASSWORDS = {
    "admin@poc.local": "Test#Admin2026",
    "pmo@poc.local": "Test#Pmo2026",
    "proveedor1@poc.local": "Test#Proveedor2026",
    "proveedor2@poc.local": "Test#Proveedor2026",
}


def _work_row_counts() -> dict[str, int] | None:
    """Filas por tabla de la base de trabajo; None si no es alcanzable (p. ej. en un CI sin ella)."""
    if WORK_URL is None:
        return None
    engine = create_engine(WORK_URL, poolclass=NullPool, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            tables = connection.scalars(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
            ).all()
            return {table: connection.scalar(text(f'SELECT count(*) FROM "{table}"')) for table in tables}
    except OperationalError:
        return None


def _workspace_snapshot() -> dict:
    """Huella de los datos de trabajo del proyecto, que la suite no debe tocar."""
    files = [p for p in (ROOT / "storage").rglob("*") if p.is_file()]
    storage = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    return {"database": _work_row_counts(), "storage": storage}


def alembic_config(database_url: str | None = None):
    """Config de Alembic sin alembic.ini: su fileConfig reconfiguraria el logging a mitad de la suite."""
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(ROOT / "alembic"))
    if database_url:
        config.attributes["database_url"] = database_url
    return config


def head_revision() -> str:
    """Revision cabeza de la cadena de migraciones (evita fijar su identificador en las pruebas)."""
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(alembic_config()).get_current_head()


@pytest.fixture(scope="session", autouse=True)
def test_database():
    before = _workspace_snapshot()
    from alembic import command

    from app.core.database import engine

    pgtools.create_database(TEST_DATABASE, SERVER_URL)
    try:
        command.upgrade(alembic_config(), "head")
        from scripts.seed_db import main as seed

        seed(passwords=TEST_PASSWORDS)
        yield
    finally:
        engine.dispose()
        pgtools.drop_database(TEST_DATABASE, SERVER_URL)
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
    assert _workspace_snapshot() == before, "La suite modifico la base de trabajo o storage/ del proyecto"


@pytest.fixture(autouse=True)
def reset_login_attempts():
    """Todas las peticiones de TestClient vienen de la IP "testclient": sin limpiar, los fallos de login de unas
    pruebas acercarian a otras al limite por IP."""
    yield
    from sqlalchemy import delete

    from app.core.database import SessionLocal
    from app.models import LoginAttempt

    with SessionLocal() as db:
        db.execute(delete(LoginAttempt))
        db.commit()


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


@pytest.fixture()
def restore_notification_templates():
    """Devuelve las plantillas de correo (HU-05) a su texto predeterminado, en la version 1 y sin Administrador: la
    base de la sesion es compartida y otras pruebas esperan la instalacion inicial."""
    yield
    from sqlalchemy import update

    from app.core.database import SessionLocal
    from app.models import NotificationTemplate
    from app.services.notification_templates import EVENTS

    with SessionLocal() as db:
        for event, spec in EVENTS.items():
            db.execute(
                update(NotificationTemplate)
                .where(NotificationTemplate.event == event)
                .values(subject=spec.default_subject, body=spec.default_body, version=1, updated_by=None)
            )
        db.commit()


RECEPTION_SEED = ["recepcionfacturas@ultrasist.com.mx"]


@pytest.fixture()
def restore_notification_recipients():
    """Devuelve los destinatarios (HU-08) a la instalacion inicial, vacia la bitacora de envios y el buzon de salida:
    la base de la sesion es compartida y otras pruebas esperan la configuracion sembrada."""
    yield
    from sqlalchemy import delete, update

    from app.core.database import SessionLocal
    from app.models import EmailDelivery, NotificationCopy, NotificationMailbox

    with SessionLocal() as db:
        db.execute(delete(EmailDelivery))
        db.execute(update(NotificationMailbox).values(addresses=RECEPTION_SEED, updated_by=None))
        db.execute(update(NotificationCopy).values(addresses=[], updated_by=None))
        db.commit()
    shutil.rmtree(OUTBOX, ignore_errors=True)


@pytest.fixture()
def registered_suppliers():
    """Fabrica de proveedores Registrado (HU-02). Al terminar borra sus usuarios, las sesiones y la auditoria de esos
    usuarios, y a ellos mismos: la base de la sesion es compartida."""
    from sqlalchemy import delete, select

    from app.core.constants import SupplierStatus, SupplierType
    from app.core.database import SessionLocal
    from app.models import AuditLog, LoginAttempt, Supplier, User, UserSession

    created: list[int] = []

    def make(count: int = 1, **overrides) -> list[Supplier]:
        rows = []
        with SessionLocal() as db:
            for _ in range(count):
                token = secrets.token_hex(3).upper()
                values = {
                    "business_name": f"Proveedor Acceso {token} SA de CV",
                    "rfc": f"HUA{token}A1",
                    "supplier_type": SupplierType.PERSONA_MORAL,
                    "email": f"acceso-{token.lower()}@proveedor.mx",
                    "status": SupplierStatus.REGISTERED,
                    **overrides,
                }
                supplier = Supplier(**values)
                db.add(supplier)
                db.flush()
                rows.append(supplier)
            db.commit()
        created.extend(s.id for s in rows)
        return rows

    yield make
    with SessionLocal() as db:
        users = list(db.scalars(select(User).where(User.supplier_id.in_(created))))
        user_ids = [u.id for u in users]
        db.execute(delete(UserSession).where(UserSession.user_id.in_(user_ids)))
        db.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
        db.execute(delete(LoginAttempt).where(LoginAttempt.email.in_([u.email for u in users])))
        db.execute(delete(User).where(User.id.in_(user_ids)))
        db.execute(delete(Supplier).where(Supplier.id.in_(created)))
        db.commit()
