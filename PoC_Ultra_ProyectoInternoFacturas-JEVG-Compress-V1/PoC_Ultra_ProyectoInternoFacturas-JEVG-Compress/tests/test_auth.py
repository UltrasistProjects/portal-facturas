"""Inicio y cierre de sesion con Keycloak (OIDC, add-keycloak-authentication; spec autenticacion-sesiones) contra el
Keycloak simulado de tests/idp.py: Authlib real, PKCE, state, nonce y validacion del ID token."""

import base64
import json
import time
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.constants import Role
from app.core.database import SessionLocal
from app.models import AuditLog, User, UserSession
from app.services import oidc, session_service
from tests.conftest import csrf, identity_account, login
from tests.idp import query

COOKIE = "invoice_portal_session"


def last_audit(action: str) -> AuditLog:
    with SessionLocal() as db:
        return db.scalar(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id.desc()).limit(1))


def assert_no_session(client) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"


@pytest.fixture()
def fresh_oidc(keycloak):
    """Cliente OIDC sin el discovery en cache: la proxima peticion vuelve a pedirlo a Keycloak."""
    oidc.use_transport(keycloak.transport)
    yield
    keycloak.oidc_unavailable = False
    oidc.use_transport(keycloak.transport)


# --- Inicio de sesion ---------------------------------------------------------------------------------------------


def test_redireccion_a_keycloak_con_pkce(client, keycloak):
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(keycloak.authorization_endpoint + "?")
    params = query(location)
    assert params["response_type"] == "code" and params["client_id"] == settings.keycloak_client_id
    assert params["redirect_uri"] == "http://testserver/auth/callback" and "openid" in params["scope"].split()
    assert params["state"] and params["nonce"] and params["code_challenge_method"] == "S256"
    assert len(params["code_challenge"]) == 43  # SHA-256 en base64url
    assert "password" not in location


def test_ruta_protegida_sin_sesion_redirige_a_login(client):
    response = client.get("/invoices", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"


def test_callback_valido(client, keycloak):
    response = login(client)
    assert response.status_code == 303 and response.headers["location"] == "/"
    assert client.get("/").status_code == 200
    # PKCE: el portal envio el code_verifier que corresponde al code_challenge (el simulador lo verifica).
    assert keycloak.token_requests[-1]["code_verifier"]
    entry = last_audit("LOGIN_SUCCESS")
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@poc.local"))
    assert entry.user_id == admin.id and admin.last_login_at is not None


def test_con_sesion_vigente_login_vuelve_al_tablero(client):
    login(client)
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/"


def test_formulario_local_retirado(client):
    assert client.post("/login", data={"email": "admin@poc.local", "password": "x"}).status_code == 405
    assert_no_session(client)


# --- Callbacks rechazados (HTTP 400, sin sesion) -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("claims", "reason"),
    [
        ({"nonce": "nonce-ajeno"}, "nonce"),
        ({"exp": int(time.time()) - 120}, "token"),  # vencido hace 2 minutos (tolerancia: 60 s)
        ({"aud": "otro-cliente", "azp": "otro-cliente"}, "token"),
        ({"iss": "http://otro-keycloak/realms/ultrasist-portal"}, "token"),
        ({"foreign_key": True}, "token"),  # firmado con una clave ajena al JWKS del realm
        ({"sub": None}, "token"),
    ],
    ids=["nonce", "expirado", "audiencia", "emisor", "firma", "sin-sub"],
)
def test_id_token_invalido(client, claims, reason):
    response = login(client, **claims)
    assert response.status_code == 400 and "No se pudo completar el inicio de sesión" in response.text
    assert last_audit("LOGIN_FAILED").new_value == {"reason": reason}
    assert_no_session(client)


def test_state_invalido(client, keycloak):
    params = query(client.get("/login", follow_redirects=False).headers["location"])
    code = keycloak.authorize("admin@poc.local", params)
    response = client.get("/auth/callback", params={"code": code, "state": "state-ajeno"}, follow_redirects=False)
    assert response.status_code == 400
    assert last_audit("LOGIN_FAILED").new_value == {"reason": "state"}
    assert_no_session(client)


def test_error_devuelto_por_keycloak(client):
    params = query(client.get("/login", follow_redirects=False).headers["location"])
    response = client.get("/auth/callback", params={"error": "access_denied", "state": params["state"]})
    assert response.status_code == 400
    assert last_audit("LOGIN_FAILED").new_value == {"reason": "idp_error"}


def test_codigo_reutilizado(client, keycloak):
    params = query(client.get("/login", follow_redirects=False).headers["location"])
    code = keycloak.authorize("admin@poc.local", params)
    keycloak.codes.pop(code)  # Keycloak ya lo canjeo: el token endpoint responde invalid_grant
    response = client.get("/auth/callback", params={"code": code, "state": params["state"]}, follow_redirects=False)
    assert response.status_code == 400 and last_audit("LOGIN_FAILED").new_value == {"reason": "idp_error"}
    assert_no_session(client)


def test_keycloak_no_disponible_en_login(client, keycloak, fresh_oidc):
    keycloak.oidc_unavailable = True
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 503
    assert "El servicio de autenticación no está disponible." in response.text and "Traceback" not in response.text


def test_keycloak_no_disponible_en_el_callback(client, keycloak):
    params = query(client.get("/login", follow_redirects=False).headers["location"])
    code = keycloak.authorize("admin@poc.local", params)
    keycloak.oidc_unavailable = True
    response = client.get("/auth/callback", params={"code": code, "state": params["state"]}, follow_redirects=False)
    assert response.status_code == 503
    assert_no_session(client)


# --- Enlace por sub y roles (HTTP 403) ----------------------------------------------------------------------------


def test_cuenta_de_keycloak_sin_usuario_en_el_portal(client, keycloak):
    email = f"fantasma.{uuid4().hex[:8]}@ultrasist.mx"
    keycloak.add_account(email, "PMO")
    response = login(client, email)
    assert response.status_code == 403 and "Su cuenta no está habilitada en el portal." in response.text
    assert last_audit("LOGIN_DENIED").new_value == {"reason": "unknown_account", "email": email}
    assert_no_session(client)


def test_mismo_correo_con_otro_sub(client):
    # El callback nunca enlaza por correo: una cuenta con el correo del Administrador pero otro sub no entra.
    response = login(client, sub=str(uuid4()))
    assert response.status_code == 403
    assert last_audit("LOGIN_DENIED").new_value == {"reason": "unknown_account", "email": "admin@poc.local"}


@pytest.fixture()
def inactive_user():
    email = f"inactivo.{uuid4().hex[:8]}@ultrasist.mx"
    with SessionLocal() as db:
        user = User(
            name="Inactivo", email=email, role=Role.PMO, is_active=False, keycloak_sub=identity_account(email, Role.PMO)
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    yield user
    with SessionLocal() as db:
        db.execute(delete(AuditLog).where(AuditLog.entity == "User", AuditLog.entity_id == str(user.id)))
        db.execute(delete(User).where(User.id == user.id))
        db.commit()


def test_usuario_desactivado_localmente(client, inactive_user):
    response = login(client, inactive_user.email)
    assert response.status_code == 403 and "Su cuenta no está habilitada en el portal." in response.text
    assert last_audit("LOGIN_DENIED").new_value == {"reason": "inactive"}


@pytest.mark.parametrize(
    ("email", "roles", "reason"),
    [
        ("admin@poc.local", [], "role_missing"),
        ("admin@poc.local", ["PMO", "Administrador"], "role_mismatch"),
        ("proveedor1@poc.local", ["Administrador"], "role_mismatch"),
    ],
    ids=["sin-rol", "dos-roles", "rol-distinto"],
)
def test_roles_del_token(client, email, roles, reason):
    response = login(client, email, roles=roles)
    assert response.status_code == 403 and "Su cuenta no tiene un rol válido para el portal" in response.text
    entry = last_audit("LOGIN_DENIED")
    assert entry.new_value == {"reason": reason}
    assert_no_session(client)


def test_auditoria_de_acceso_sin_tokens(client):
    accepted = login(client)
    rejected = login(client, nonce="nonce-ajeno")
    code_values = [query(str(response.request.url))["code"] for response in (accepted, rejected)]
    with SessionLocal() as db:
        entries = db.scalars(
            select(AuditLog).where(AuditLog.action.in_(["LOGIN_SUCCESS", "LOGIN_FAILED", "LOGIN_DENIED"]))
        ).all()
        tokens = [token for token in db.scalars(select(UserSession.id_token_hint)) if token]
    content = json.dumps([[e.old_value, e.new_value] for e in entries], default=str)
    assert not any(value in content for value in [*code_values, *tokens, "nonce-ajeno"])


# --- Cierre de sesion ---------------------------------------------------------------------------------------------


def test_logout_termina_la_sesion_en_keycloak(client, keycloak):
    login(client)
    sid = json.loads(base64.b64decode(client.cookies.get(COOKIE).split(".")[0] + "=="))["sid"]
    with SessionLocal() as db:
        hint = db.scalar(select(UserSession.id_token_hint).where(UserSession.sid_hash == session_service.hash_sid(sid)))
    response = client.post("/logout", data={"csrf_token": csrf(client, "/")}, follow_redirects=False)
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith(keycloak.end_session_endpoint + "?")
    params = query(location)
    assert params["id_token_hint"] == hint and params["client_id"] == settings.keycloak_client_id
    assert params["post_logout_redirect_uri"] == "http://testserver/"
    assert last_audit("LOGOUT").user_id is not None
    assert_no_session(client)
    # Nueva visita: el portal vuelve a mandar a Keycloak (que pedira credenciales: su sesion SSO termino).
    assert client.get("/login", follow_redirects=False).headers["location"].startswith(keycloak.authorization_endpoint)


def test_logout_sin_token_csrf(client):
    login(client)
    assert client.post("/logout", data={}).status_code == 403
    assert client.get("/", follow_redirects=False).status_code == 200


def test_logout_con_keycloak_no_disponible(client, keycloak, fresh_oidc):
    login(client)
    oidc.use_transport(keycloak.transport)  # sin el discovery en cache
    keycloak.oidc_unavailable = True
    response = client.post("/logout", data={"csrf_token": csrf(client, "/")}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/"
    keycloak.oidc_unavailable = False
    assert_no_session(client)


# --- Cambio de contrasena en Keycloak ----------------------------------------------------------------------------


def test_cambiar_contrasena_redirige_a_keycloak(client, keycloak):
    login(client, "pmo@poc.local")
    assert 'href="/account/password"' in client.get("/").text
    response = client.get("/account/password", follow_redirects=False)
    assert response.status_code == 302 and response.headers["location"].startswith(keycloak.authorization_endpoint)
    assert query(response.headers["location"])["kc_action"] == "UPDATE_PASSWORD"


def test_regreso_del_cambio_de_contrasena(client, keycloak):
    login(client, "pmo@poc.local")
    params = query(client.get("/account/password", follow_redirects=False).headers["location"])
    code = keycloak.authorize("pmo@poc.local", params)
    response = client.get(
        "/auth/callback",
        params={"code": code, "state": params["state"], "kc_action_status": "success"},
        follow_redirects=False,
    )
    assert response.status_code == 303 and response.headers["location"] == "/?notice=password_changed"
    assert last_audit("PASSWORD_CHANGED").new_value == {"forced": False}
    assert "Contraseña actualizada" in client.get(response.headers["location"]).text


def test_cambio_de_contrasena_cancelado_no_se_audita(client, keycloak):
    before = last_audit("PASSWORD_CHANGED")
    response = login(client, "pmo@poc.local", callback_params={"kc_action_status": "cancelled"})
    assert response.headers["location"] == "/"
    after = last_audit("PASSWORD_CHANGED")
    assert (after.id if after else None) == (before.id if before else None)


def test_cambiar_contrasena_sin_sesion(client):
    response = client.get("/account/password", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"
    assert client.post("/account/password", data={}).status_code == 405
