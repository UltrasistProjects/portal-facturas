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
        # Keycloak simulado (tests/idp.py): el host no existe y ninguna prueba sale a la red.
        "KEYCLOAK_SERVER_URL": "http://keycloak.test",
        "KEYCLOAK_REALM": "ultrasist-portal",
        "KEYCLOAK_CLIENT_ID": "portal-facturas-web",
        "KEYCLOAK_CLIENT_SECRET": secrets.token_urlsafe(48),
        "KEYCLOAK_ADMIN_CLIENT_ID": "portal-facturas-admin",
        "KEYCLOAK_ADMIN_CLIENT_SECRET": secrets.token_urlsafe(48),
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
    "proveedor3@poc.local": "Test#Proveedor2026",
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


@pytest.fixture(scope="session")
def keycloak():
    """Keycloak simulado de toda la sesion: cliente de administracion del portal y transporte OIDC de Authlib."""
    from app.services import keycloak_admin, oidc
    from tests.idp import FakeKeycloak

    fake = FakeKeycloak()
    previous = keycloak_admin.set_identity_admin(fake)
    oidc.use_transport(fake.transport)
    yield fake
    oidc.use_transport(None)
    keycloak_admin.set_identity_admin(previous)


@pytest.fixture(scope="session", autouse=True)
def test_database(keycloak):
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
def reset_keycloak(keycloak):
    """Fallos simulados y registro de llamadas de una prueba no pasan a la siguiente."""
    keycloak.reset()
    yield
    keycloak.reset()


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


def identity_account(email: str, role) -> str:
    """Cuenta del Keycloak simulado para un usuario que crea la prueba (idempotente); devuelve su sub, que va en
    User.keycloak_sub para que la prueba pueda iniciar sesion con login()."""
    from app.services.keycloak_admin import get_identity_admin

    keycloak = get_identity_admin()
    existing = keycloak.accounts.get(next((k for k, a in keycloak.accounts.items() if a.email == email.lower()), ""))
    account = existing or keycloak.add_account(email)
    account.roles = {role.value}
    return account.id


def login(client, email="admin@poc.local", callback_params: dict | None = None, **claims):
    """Inicio de sesion completo contra el Keycloak simulado: /login redirige a Keycloak, la cuenta de `email` se
    autentica y /auth/callback recibe el codigo. `claims` altera el ID token (None quita un claim; `roles` reemplaza
    los realm roles). Parte de una sesion nueva, como quien entra con otra cuenta; devuelve la respuesta del
    callback."""
    from app.services.keycloak_admin import get_identity_admin
    from tests.idp import query

    keycloak = get_identity_admin()
    client.cookies.clear()
    response = client.get("/login", follow_redirects=False)
    location = response.headers.get("location", "")
    if not location.startswith(keycloak.authorization_endpoint):
        return response
    params = query(location)
    code = keycloak.authorize(email, params, **claims)
    return client.get(
        "/auth/callback",
        params={"code": code, "state": params["state"], **(callback_params or {})},
        follow_redirects=False,
    )


# Perfil del proveedor que exigen el alta individual y la edicion para una persona moral.
SUPPLIER_PROFILE_FORM = {
    "phone": "55 5555 0000",
    "classification": "EXTERNAL",
    "main_activity": "54",
    "incorporation_date": "2026-01-01",
    "website": "www.serviciosnuevos.example",
    "legal_rep_name": "Ana Martinez Ruiz",
    "legal_rep_phone": "55 1234 5678",
    "contact_name": "Luis Gomez Ortiz",
    "contact_phone": "(55) 8765-4321",
}


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


def add_expedient_documents(supplier_id: int, codes, document_date=None) -> None:
    """Documentos vigentes del expediente (sin factura) cargados directamente en la base, sin archivo en storage/:
    los requisitos de alta solo verifican que existan (HU-21)."""
    from sqlalchemy import select

    from app.core.constants import ProcessingStatus
    from app.core.database import SessionLocal
    from app.models import Document, User

    with SessionLocal() as db:
        admin_id = db.scalar(select(User.id).where(User.email == "admin@poc.local"))
        for code in codes:
            filename = f"{code.lower()}.pdf"
            db.add(
                Document(
                    supplier_id=supplier_id,
                    document_type=code,
                    original_filename=filename,
                    stored_filename=filename,
                    path=f"suppliers/{supplier_id}/{filename}",
                    mime_type="application/pdf",
                    file_size=1,
                    sha256="0" * 64,
                    uploaded_by=admin_id,
                    processing_status=ProcessingStatus.PROCESSED,
                    document_date=document_date,
                    metadata_json={"scope": "supplier"},
                    is_current=True,
                )
            )
        db.commit()


def load_requirements(*supplier_ids: int) -> None:
    """Completa los requisitos de alta exigibles de los proveedores con la configuracion vigente (HU-21), para las
    pruebas que autorizan proveedores."""
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import Supplier
    from app.services import supplier_requirements_service as requirements

    with SessionLocal() as db:
        suppliers = list(db.scalars(select(Supplier).where(Supplier.id.in_(supplier_ids))))
        pending = requirements.pending_requirements(db, suppliers)
    for supplier_id, types in pending.items():
        add_expedient_documents(supplier_id, [t.code for t in types])


def contract_document(db, contract_id: int, code: str, filename: str | None = None):
    """Documento vigente de un contrato (HU-22), con su archivo en storage/ para que siga siendo descargable y su hash
    coincida (los respaldos lo verifican). Es solo del contrato: sin supplier_id ni invoice_id."""
    from sqlalchemy import select

    from app.core.config import settings
    from app.core.constants import ProcessingStatus
    from app.models import Document, User

    filename = filename or f"{code.lower()}.pdf"
    content = f"%PDF-1.4\n%{code}\n".encode()
    path = f"contracts/{contract_id}/{secrets.token_hex(8)}.pdf"
    target = settings.storage_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    document = Document(
        contract_id=contract_id,
        document_type=code,
        original_filename=filename,
        stored_filename=target.name,
        path=path,
        mime_type="application/pdf",
        file_size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        uploaded_by=db.scalar(select(User.id).where(User.email == "admin@poc.local")),
        processing_status=ProcessingStatus.PROCESSED,
        metadata_json={"scope": "contract"},
        is_current=True,
    )
    db.add(document)
    db.flush()
    return document


def active_contract(db, supplier_id: int, **values):
    """Contrato Activo con su contrato firmado (HU-22), listo para facturar: el alta crea contratos Registrado y DOC-005
    exige el contrato firmado. Se agrega a la sesion `db` sin confirmarla."""
    from app.core.constants import SIGNED_CONTRACT_DOCUMENT, ContractStatus
    from app.models import Contract

    contract = Contract(supplier_id=supplier_id, status=ContractStatus.ACTIVE, **values)
    db.add(contract)
    db.flush()
    contract_document(db, contract.id, SIGNED_CONTRACT_DOCUMENT)
    return contract


@pytest.fixture()
def new_contracts():
    """Fabrica de contratos de prueba (HU-22), por omision Registrado y del proveedor demo persona moral (Autorizado),
    con los documentos de las claves indicadas. `track` agrega a la limpieza los contratos creados por HTTP. Al
    terminar borra sus documentos y a ellos mismos: la base de la sesion es compartida. Los contratos no deben tener
    facturas."""
    from datetime import date
    from decimal import Decimal

    from sqlalchemy import delete, update

    from app.core.constants import ContractStatus
    from app.core.database import SessionLocal
    from app.models import Contract, Document

    created: list[int] = []

    def make(codes=(), supplier_id: int | None = None, status=ContractStatus.REGISTERED, **overrides):
        token = secrets.token_hex(3).upper()
        values = {
            "supplier_id": supplier_id or supplier_by_email("proveedor1@poc.local").id,
            "project_name": f"Contrato HU22 {token}",
            "project_leader": "Lider de pruebas",
            "authorized_technology": "Power Platform",
            "authorized_amount": Decimal("1000.00"),
            "currency": "MXN",
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
            "status": status,
            **overrides,
        }
        with SessionLocal() as db:
            contract = Contract(**values)
            db.add(contract)
            db.flush()
            for code in codes:
                contract_document(db, contract.id, code)
            db.commit()
            created.append(contract.id)
            return contract

    make.track = created.append
    yield make
    with SessionLocal() as db:
        documents = Document.contract_id.in_(created)
        db.execute(update(Document).where(documents).values(replaced_document_id=None))
        db.execute(delete(Document).where(documents))
        db.execute(delete(Contract).where(Contract.id.in_(created)))
        db.commit()


@pytest.fixture()
def registered_suppliers():
    """Fabrica de proveedores Registrado (HU-02), por omision con sus requisitos de alta completos (HU-21) para poder
    autorizarlos; `requirements=False` los deja sin documentos. Al terminar borra sus documentos, sus usuarios, las
    sesiones y la auditoria de esos usuarios, y a ellos mismos: la base de la sesion es compartida."""
    from sqlalchemy import delete, select

    from app.core.constants import SupplierStatus, SupplierType
    from app.core.database import SessionLocal
    from app.models import AuditLog, Document, Supplier, User, UserSession

    created: list[int] = []

    def make(count: int = 1, requirements: bool = True, **overrides) -> list[Supplier]:
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
        if requirements:
            load_requirements(*(s.id for s in rows))
        return rows

    yield make
    with SessionLocal() as db:
        users = list(db.scalars(select(User).where(User.supplier_id.in_(created))))
        user_ids = [u.id for u in users]
        db.execute(delete(UserSession).where(UserSession.user_id.in_(user_ids)))
        db.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
        db.execute(delete(Document).where(Document.supplier_id.in_(created), Document.invoice_id.is_(None)))
        db.execute(delete(User).where(User.id.in_(user_ids)))
        db.execute(delete(Supplier).where(Supplier.id.in_(created)))
        db.commit()


def migration_module(revision: str):
    """Modulo de una migracion: sus constantes son la siembra de datos de referencia."""
    import importlib.util

    path = ROOT / "alembic" / "versions" / f"{revision}.py"
    spec = importlib.util.spec_from_file_location(f"migration_{revision}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def restore_validation_rules():
    """Devuelve las Reglas de Validacion (HU-06) y los catalogos (HU-07), incluidas las actividades economicas, a la
    instalacion inicial: la base de la sesion es compartida y el motor de otras pruebas espera la configuracion
    sembrada."""
    yield
    from sqlalchemy import delete, update

    from app.core.database import SessionLocal
    from app.models import CatalogEntry, ValidationSettings

    seed = migration_module("0007_validation_rules_catalogs")
    entries = {**seed.ENTRIES, **migration_module("0009_supplier_profile").ENTRIES}
    with SessionLocal() as db:
        db.execute(update(ValidationSettings).values(**{k: v for k, v in seed.SETTINGS.items() if k != "id"}))
        for catalog, rows in entries.items():
            codes = [code for code, _ in rows]
            db.execute(delete(CatalogEntry).where(CatalogEntry.catalog == catalog, CatalogEntry.code.not_in(codes)))
            for code, name in rows:
                db.execute(
                    update(CatalogEntry)
                    .where(CatalogEntry.catalog == catalog, CatalogEntry.code == code)
                    .values(name=name, is_active=True, updated_by=None)
                )
        db.commit()
