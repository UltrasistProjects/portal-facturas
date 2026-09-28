"""Cambio obligatorio de la contrasena asignada y cambio de contrasena (HU-10, spec autenticacion-sesiones)."""

import json
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, or_, select

from app.core.constants import LoginResult, Role
from app.core.database import SessionLocal
from app.core.security import hash_password, verify_password
from app.main import app
from app.models import AuditLog, Contract, Invoice, LoginAttempt, Supplier, User, UserSession
from app.routers.auth import MSG_MISMATCH, MSG_SAME, MSG_WRONG_CURRENT
from tests.conftest import csrf, login

TEMPORARY = "Temporal#2026x"
NEW = "Portal#2026x"
PASSWORD_URL = "/account/password"


@pytest.fixture()
def make_user():
    """Fabrica de usuarios PROVIDER del proveedor demo 1, con o sin la marca de contrasena asignada. Al terminar
    borra sus sesiones, intentos, auditoria y a ellos mismos: la base de la sesion es compartida."""
    emails: list[str] = []

    def make(*, must_change: bool = True, password: str = TEMPORARY) -> str:
        email = f"primer-{secrets.token_hex(4)}@proveedor.mx"
        with SessionLocal() as db:
            supplier_id = db.scalar(select(Supplier.id).where(Supplier.email == "proveedor1@poc.local"))
            db.add(
                User(
                    name="Usuario Primer Acceso",
                    email=email,
                    password_hash=hash_password(password),
                    role=Role.PROVIDER,
                    supplier_id=supplier_id,
                    must_change_password=must_change,
                )
            )
            db.commit()
        emails.append(email)
        return email

    make.track = emails.append  # usuarios creados por otra via (p. ej. /admin/users)
    yield make
    with SessionLocal() as db:
        ids = list(db.scalars(select(User.id).where(User.email.in_(emails))))
        db.execute(delete(UserSession).where(UserSession.user_id.in_(ids)))
        db.execute(
            delete(AuditLog).where(
                or_(AuditLog.user_id.in_(ids), (AuditLog.entity == "User") & AuditLog.entity_id.in_(map(str, ids)))
            )
        )
        db.execute(delete(LoginAttempt).where(LoginAttempt.email.in_(emails)))
        db.execute(delete(User).where(User.id.in_(ids)))
        db.commit()


def user(email: str) -> User:
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.email == email))


def change(client, current: str, new: str, confirm: str | None = None, token: str | None = None):
    data = {"current_password": current, "new_password": new, "confirm_password": new if confirm is None else confirm}
    data["csrf_token"] = csrf(client, PASSWORD_URL) if token is None else token
    return client.post(PASSWORD_URL, data=data, follow_redirects=False)


def password_changes(email: str) -> list[AuditLog]:
    with SessionLocal() as db:
        user_id = db.scalar(select(User.id).where(User.email == email))
        return list(
            db.scalars(select(AuditLog).where(AuditLog.action == "PASSWORD_CHANGED", AuditLog.user_id == user_id))
        )


# --- Cambio obligatorio -------------------------------------------------------------------------------------------


def test_primer_acceso_lleva_al_cambio(client, make_user):
    email = make_user()
    response = login(client, email, TEMPORARY)
    assert response.status_code == 303 and response.headers["location"] == PASSWORD_URL


@pytest.mark.parametrize("path", ["/", "/invoices", "/invoices/new", "/suppliers"])
def test_navegacion_bloqueada(client, make_user, path):
    login(client, make_user(), TEMPORARY)
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == PASSWORD_URL


def test_accion_bloqueada_sin_efectos(client, make_user):
    login(client, make_user(), TEMPORARY)
    with SessionLocal() as db:
        supplier_id = db.scalar(select(Supplier.id).where(Supplier.email == "proveedor1@poc.local"))
        contract_id = db.scalar(select(Contract.id).where(Contract.supplier_id == supplier_id))
    number = f"HU10-{secrets.token_hex(3)}"
    data = {
        "supplier_id": supplier_id,
        "contract_id": contract_id,
        "invoice_number": number,
        "service_period": "09/2026",
        "project_name": "Proyecto bloqueado",
        "csrf_token": csrf(client, PASSWORD_URL),
    }
    response = client.post("/invoices/new", data=data, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == PASSWORD_URL
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Invoice.id)).where(Invoice.invoice_number == number)) == 0


def test_cierre_de_sesion_disponible(client, make_user):
    login(client, make_user(), TEMPORARY)
    response = client.post("/logout", data={"csrf_token": csrf(client, PASSWORD_URL)}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"
    assert client.get(PASSWORD_URL, follow_redirects=False).headers["location"] == "/login"


def test_usuario_creado_por_el_administrador(client, make_user):
    login(client)
    email = f"interno-{secrets.token_hex(4)}@ultrasist.com.mx"
    make_user.track(email)
    data = {"name": "Interno Nuevo", "email": email, "password": TEMPORARY, "role": "INTERNAL"}
    response = client.post(
        "/admin/users", data={**data, "csrf_token": csrf(client, "/admin/users")}, follow_redirects=False
    )
    assert response.status_code == 303 and user(email).must_change_password
    assert "Contraseña temporal" in client.get("/admin/users").text
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    assert login(client, email, TEMPORARY).headers["location"] == PASSWORD_URL


def test_usuario_demo_sin_marca(client):
    response = login(client)
    assert response.status_code == 303 and response.headers["location"] == "/"
    assert client.get("/").status_code == 200
    assert not user("admin@poc.local").must_change_password


def test_pagina_de_cambio_sin_sesion(client):
    assert client.get(PASSWORD_URL, follow_redirects=False).headers["location"] == "/login"


# --- Cambio de contrasena -----------------------------------------------------------------------------------------


def test_pagina_obligatoria_sin_menu(client, make_user):
    email = make_user()
    login(client, email, TEMPORARY)
    page = client.get(PASSWORD_URL).text
    assert "Cambie su contraseña temporal" in page and email in page and "Cerrar sesión" in page
    assert 'class="sidebar"' not in page and "al menos una letra, un número y un carácter especial" in page


def test_cambio_exitoso_en_el_primer_acceso(client, make_user):
    email = make_user()
    login(client, email, TEMPORARY)
    response = change(client, TEMPORARY, NEW)
    assert response.status_code == 303 and response.headers["location"] == "/?notice=password_changed"
    assert "Contraseña actualizada" in client.get(response.headers["location"]).text
    changed = user(email)
    assert not changed.must_change_password and verify_password(NEW, changed.password_hash)
    with TestClient(app) as other:
        assert login(other, email, TEMPORARY).status_code == 400
        assert login(other, email, NEW).headers["location"] == "/"


@pytest.mark.parametrize(
    ("new", "message"),
    [
        ("Password123", "al menos un caracter especial"),
        ("Password1!", "demasiado comun"),
        ("x" * 129, "no puede exceder 128 caracteres"),
    ],
)
def test_nueva_contrasena_fuera_de_la_politica(client, make_user, new, message):
    email = make_user()
    login(client, email, TEMPORARY)
    response = change(client, TEMPORARY, new)
    assert response.status_code == 400 and message in response.text
    unchanged = user(email)
    assert unchanged.must_change_password and verify_password(TEMPORARY, unchanged.password_hash)


def test_varios_errores_juntos(client, make_user):
    login(client, make_user(), TEMPORARY)
    response = change(client, TEMPORARY, "abc", "abd")
    assert response.status_code == 400
    assert "al menos 8 caracteres" in response.text and MSG_MISMATCH in response.text


def test_nueva_contrasena_igual_a_la_actual(client, make_user):
    email = make_user()
    login(client, email, TEMPORARY)
    response = change(client, TEMPORARY, TEMPORARY)
    assert response.status_code == 400 and MSG_SAME in response.text
    assert user(email).must_change_password


def test_contrasena_actual_incorrecta(client, make_user):
    email = make_user()
    login(client, email, TEMPORARY)
    response = change(client, "Otra#Clave2026", NEW)
    assert response.status_code == 400 and MSG_WRONG_CURRENT in response.text
    assert verify_password(TEMPORARY, user(email).password_hash)
    with SessionLocal() as db:
        results = list(db.scalars(select(LoginAttempt.result).where(LoginAttempt.email == email)))
    assert results.count(LoginResult.FAILURE) == 1


def test_intentos_agotados(client, make_user):
    email = make_user()
    login(client, email, TEMPORARY)
    token = csrf(client, PASSWORD_URL)
    for _ in range(5):
        assert change(client, "Otra#Clave2026", NEW, token=token).status_code == 400
    response = change(client, TEMPORARY, NEW, token=token)
    assert response.status_code == 429 and "Retry-After" in response.headers
    assert user(email).must_change_password and verify_password(TEMPORARY, user(email).password_hash)


@pytest.mark.parametrize("token", ["", "token-invalido"])
def test_cambio_sin_token_csrf(client, make_user, token):
    email = make_user()
    login(client, email, TEMPORARY)
    response = change(client, TEMPORARY, NEW, token=token)
    assert response.status_code == 403 and verify_password(TEMPORARY, user(email).password_hash)


def test_cambio_voluntario(client, make_user):
    email = make_user(must_change=False)
    assert login(client, email, TEMPORARY).headers["location"] == "/"
    assert 'href="/account/password"' in client.get("/").text
    page = client.get(PASSWORD_URL).text
    assert 'class="sidebar"' in page and "Cambiar contraseña" in page
    response = change(client, TEMPORARY, NEW)
    assert response.headers["location"] == "/?notice=password_changed"
    assert verify_password(NEW, user(email).password_hash)
    assert [entry.new_value for entry in password_changes(email)] == [{"forced": False}]


def test_aviso_desconocido_se_ignora(client):
    login(client)
    assert "alert-success" not in client.get("/?notice=otro").text


# --- Sesiones y auditoria -----------------------------------------------------------------------------------------


def test_otras_sesiones_revocadas(client, make_user):
    email = make_user(must_change=False)
    with TestClient(app) as other:
        login(other, email, TEMPORARY)
        login(client, email, TEMPORARY)
        with SessionLocal() as db:
            user_id = db.scalar(select(User.id).where(User.email == email))
            before = set(db.scalars(select(UserSession.id).where(UserSession.user_id == user_id)))
        assert change(client, TEMPORARY, NEW).status_code == 303
        assert other.get("/", follow_redirects=False).headers["location"] == "/login"
        assert client.get("/").status_code == 200
    with SessionLocal() as db:
        active = set(
            db.scalars(select(UserSession.id).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None)))
        )
    # Sesion nueva para quien cambio la contrasena; las dos anteriores, revocadas.
    assert len(active) == 1 and not active & before


def test_auditoria_del_primer_cambio(client, make_user):
    email = make_user()
    login(client, email, TEMPORARY)
    change(client, TEMPORARY, NEW)
    [entry] = password_changes(email)
    assert entry.entity == "User" and entry.entity_id == str(user(email).id) and entry.new_value == {"forced": True}
    with SessionLocal() as db:
        dump = json.dumps([[a.old_value, a.new_value] for a in db.scalars(select(AuditLog))], default=str)
    assert TEMPORARY not in dump and NEW not in dump


def test_cambios_rechazados_sin_auditoria(client, make_user):
    email = make_user()
    login(client, email, TEMPORARY)
    token = csrf(client, PASSWORD_URL)
    change(client, TEMPORARY, "Password123", token=token)  # 400
    change(client, TEMPORARY, NEW, token="token-invalido")  # 403
    for _ in range(5):
        change(client, "Otra#Clave2026", NEW, token=token)
    assert change(client, TEMPORARY, NEW, token=token).status_code == 429
    assert password_changes(email) == []
