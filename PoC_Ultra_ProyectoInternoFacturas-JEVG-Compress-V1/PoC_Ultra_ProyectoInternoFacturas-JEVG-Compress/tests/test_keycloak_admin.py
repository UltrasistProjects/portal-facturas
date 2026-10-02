"""Cliente HTTP de la API de administracion de Keycloak y reglas de enlace (add-keycloak-authentication, D11, D13,
D14), contra el Keycloak simulado servido por httpx.MockTransport: sin Keycloak ni red."""

import logging

import httpx
import pytest

from app.core.constants import Role
from app.core.database import SessionLocal
from app.services import identity_service as identity
from app.services import keycloak_admin
from app.services.keycloak_admin import UPDATE_PASSWORD, IdentityProviderError, KeycloakAdmin
from tests.idp import FakeKeycloak


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def fake():
    return FakeKeycloak()


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def admin(fake, clock):
    return KeycloakAdmin(transport=fake.transport, clock=clock)


def token_requests(fake) -> int:
    return sum(request.get("grant_type") == "client_credentials" for request in fake.token_requests)


# --- Operaciones ----------------------------------------------------------------------------------------------------


def test_crea_cuenta_con_rol_y_contrasena_temporal(admin, fake):
    user_id = admin.create_user("Nuevo@Proveedor.mx".lower())
    admin.assign_realm_role(user_id, "Proveedor")
    admin.assign_realm_role(user_id, "Proveedor")  # ya lo tiene: no falla ni lo duplica
    admin.set_password(user_id, "Temporal#2026x", temporary=True)
    account = admin.get_user(user_id)
    assert (account.email, account.enabled, account.password_pending) == ("nuevo@proveedor.mx", True, True)
    assert admin.find_by_email("NUEVO@proveedor.mx") == account
    assert "Proveedor" in admin.realm_roles(user_id) and "offline_access" in admin.realm_roles(user_id)
    assert fake.accounts[user_id].password == "Temporal#2026x"


def test_contrasena_definitiva_sin_accion_requerida(admin, fake):
    user_id = admin.create_user("demo@poc.local")
    admin.set_password(user_id, "Demo#Prueba2026x", temporary=False)
    assert fake.accounts[user_id].required_actions == [] and not admin.get_user(user_id).password_pending


def test_deshabilitar_y_cerrar_sesiones(admin, fake):
    user_id = admin.create_user("sesiones@ultrasist.mx")
    admin.set_enabled(user_id, False)
    admin.logout(user_id)
    assert fake.accounts[user_id].enabled is False and fake.logouts == [user_id]
    admin.set_enabled(user_id, True)
    assert admin.get_user(user_id).enabled


def test_cuenta_inexistente(admin):
    assert admin.get_user("no-existe") is None and admin.find_by_email("nadie@ultrasist.mx") is None
    with pytest.raises(IdentityProviderError) as error:
        admin.set_enabled("no-existe", False)
    assert (error.value.operation, error.value.code, error.value.status_code) == ("get_user", "http_404", 503)


def test_rol_inexistente(admin):
    user_id = admin.create_user("rol@ultrasist.mx")
    with pytest.raises(IdentityProviderError, match="no está disponible") as error:
        admin.assign_realm_role(user_id, "Auditor")
    assert error.value.code == "role_not_found"


def test_correo_duplicado(admin):
    admin.create_user("doble@ultrasist.mx")
    with pytest.raises(IdentityProviderError) as error:
        admin.create_user("doble@ultrasist.mx")
    assert error.value.code == "http_409"


# --- Token de la cuenta de servicio ---------------------------------------------------------------------------------


def test_token_en_cache_y_renovado_al_expirar(admin, fake, clock):
    admin.find_by_email("a@ultrasist.mx")
    admin.find_by_email("b@ultrasist.mx")
    assert token_requests(fake) == 1
    clock.now += 300 - keycloak_admin.TOKEN_MARGIN_SECONDS + 1
    admin.find_by_email("c@ultrasist.mx")
    assert token_requests(fake) == 2


def test_token_revocado_se_renueva_una_vez(admin, fake):
    admin.find_by_email("a@ultrasist.mx")
    fake.admin_tokens.clear()  # Keycloak ya no acepta el token en cache: responde 401
    assert admin.find_by_email("a@ultrasist.mx") is None
    assert token_requests(fake) == 2


def test_credenciales_de_la_cuenta_de_servicio_rechazadas(clock):
    rejected = httpx.MockTransport(lambda request: httpx.Response(401, json={"error": "invalid_client"}))
    with pytest.raises(IdentityProviderError) as error:
        KeycloakAdmin(transport=rejected, clock=clock).find_by_email("a@ultrasist.mx")
    assert (error.value.operation, error.value.code) == ("service_token", "http_401")


# --- Fallos de Keycloak ---------------------------------------------------------------------------------------------


def test_red_caida_falla_rapido(clock):
    attempts = []

    def unreachable(request):
        attempts.append(request)
        raise httpx.ConnectError("sin red", request=request)

    admin = KeycloakAdmin(transport=httpx.MockTransport(unreachable), clock=clock)
    for _ in range(3):
        with pytest.raises(IdentityProviderError) as error:
            admin.find_by_email("a@ultrasist.mx")
        assert error.value.code == "unavailable"
    assert len(attempts) == 1  # las siguientes fallan de inmediato, sin esperar el timeout
    clock.now += keycloak_admin.FAIL_FAST_SECONDS + 1
    with pytest.raises(IdentityProviderError):
        admin.find_by_email("a@ultrasist.mx")
    assert len(attempts) == 2


def test_error_5xx_marca_indisponible(admin, fake):
    admin.find_by_email("a@ultrasist.mx")
    fake.unavailable = True  # la API responde 503
    with pytest.raises(IdentityProviderError) as error:
        admin.find_by_email("a@ultrasist.mx")
    assert (error.value.operation, error.value.code) == ("find_user", "unavailable")
    fake.unavailable = False
    with pytest.raises(IdentityProviderError):  # dentro de la ventana de falla rapida
        admin.find_by_email("a@ultrasist.mx")


@pytest.mark.parametrize(
    ("response", "operation", "code"),
    [
        (httpx.Response(200, text="no es json"), "find_user", "invalid_response"),
        (httpx.Response(201), "create_user", "invalid_response"),
        (httpx.Response(200, json={"sin": "access_token"}), "service_token", "invalid_response"),
    ],
    ids=["json-invalido", "sin-location", "token-sin-access-token"],
)
def test_respuestas_inesperadas(clock, response, operation, code):
    def handler(request):
        if request.url.path.endswith("/token") and operation != "service_token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 300})
        return response

    admin = KeycloakAdmin(transport=httpx.MockTransport(handler), clock=clock)
    call = admin.create_user if operation == "create_user" else admin.find_by_email
    with pytest.raises(IdentityProviderError) as error:
        call("a@ultrasist.mx")
    assert (error.value.operation, error.value.code) == (operation, code)


def test_representacion_incompleta(clock):
    def handler(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 300})
        return httpx.Response(200, json={"email": "sin-id@ultrasist.mx"})

    with pytest.raises(IdentityProviderError) as error:
        KeycloakAdmin(transport=httpx.MockTransport(handler), clock=clock).get_user("x")
    assert error.value.code == "invalid_response"


def test_log_sin_tokens_ni_contrasenas(admin, fake, caplog):
    with caplog.at_level(logging.INFO, logger="app.services.keycloak_admin"):
        user_id = admin.create_user("log@ultrasist.mx")
        admin.set_password(user_id, "Temporal#Secreta2026", temporary=True)
    events = [record for record in caplog.records if getattr(record, "event", None) == "keycloak.admin"]
    assert {e.operation for e in events} >= {"service_token", "create_user", "reset_password"}
    assert all(isinstance(e.duration_ms, int) and e.status in (200, 201, 204) for e in events)
    text = caplog.text + " ".join(str(vars(record)) for record in caplog.records)
    assert "Temporal#Secreta2026" not in text and not any(token in text for token in fake.admin_tokens)


def test_cliente_http_por_omision():
    previous = keycloak_admin.set_identity_admin(None)
    try:
        assert isinstance(keycloak_admin.get_identity_admin(), KeycloakAdmin)
    finally:
        keycloak_admin.set_identity_admin(previous)


# --- Reglas de enlace y estado de la contrasena (identity_service) -------------------------------------------------


def test_enlace_de_una_cuenta_de_otro_usuario_del_portal(keycloak):
    # admin@poc.local ya esta enlazado a su usuario del portal: otra alta con su correo es un conflicto.
    with SessionLocal() as db, pytest.raises(identity.AccountConflict):
        identity.provision(db, keycloak, email="admin@poc.local", role=Role.ADMINISTRADOR)


def test_enlace_habilita_la_cuenta_existente(keycloak):
    account = keycloak.add_account("deshabilitada@ultrasist.mx", enabled=False)
    with SessionLocal() as db:
        provisioned = identity.provision(db, keycloak, email=account.email, role=Role.PMO, enabled=True)
    assert (provisioned.sub, provisioned.origin) == (account.id, "linked")
    assert account.enabled and account.roles == {"PMO"} and account.required_actions == [UPDATE_PASSWORD]


def test_estado_de_la_contrasena(keycloak):
    account = keycloak.add_account("estado@ultrasist.mx", "PMO")
    assert identity.password_state(keycloak, None) == identity.UNLINKED
    assert identity.password_state(keycloak, "no-existe") == identity.UNLINKED
    keycloak.set_password(account.id, "Temporal#2026x", temporary=True)
    assert identity.password_state(keycloak, account.id) == identity.TEMPORARY
    keycloak.change_password(account.email, "Propia#2026x")
    assert identity.password_state(keycloak, account.id) == identity.CHANGED
    keycloak.unavailable = True
    assert identity.password_state(keycloak, account.id) == identity.UNAVAILABLE
