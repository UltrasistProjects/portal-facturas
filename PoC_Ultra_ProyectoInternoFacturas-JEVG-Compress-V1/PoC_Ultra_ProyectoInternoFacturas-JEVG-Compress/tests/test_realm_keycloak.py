"""Realm versionado y servicio Keycloak de compose.yaml (add-keycloak-authentication; specs autenticacion-sesiones e
infraestructura-local): politica de contrasenas (RF-06), fuerza bruta (SEC-04), clientes, cuenta de servicio minima y
ningun secreto en el repositorio."""

import json
import re

import pytest
import yaml

from app.core.config import settings
from app.core.constants import Role
from scripts import build_password_blacklist
from tests.conftest import ROOT

KEYCLOAK_DIR = ROOT / "infra" / "keycloak"
REALM = json.loads((KEYCLOAK_DIR / "realm-ultrasist-portal.json").read_text(encoding="utf-8"))


def client(client_id: str) -> dict:
    return next(item for item in REALM["clients"] if item["clientId"] == client_id)


def test_politica_de_contrasenas():
    policies = REALM["passwordPolicy"].split(" and ")
    for expected in (
        "length(8)",
        "maxLength(128)",
        "digits(1)",
        "specialChars(1)",
        "notUsername(undefined)",
        "notEmail(undefined)",
        "passwordHistory(1)",
        "passwordBlacklist(common_passwords.txt)",
    ):
        assert expected in policies, expected
    [letter] = [policy for policy in policies if policy.startswith("regexPattern(")]
    # Keycloak usa expresiones de Java: \p{L} es "cualquier letra"; en Python, [^\W\d_].
    java = letter.removeprefix("regexPattern(").removesuffix(")")
    pattern = re.compile(java.replace("\\p{L}", "[^\\W\\d_]"))
    assert java == ".*\\p{L}.*"
    assert (
        pattern.fullmatch("Portal#2026x") and pattern.fullmatch("Contraseña#1") and not pattern.fullmatch("12345678#")
    )


def test_lista_de_contrasenas_comunes_al_dia():
    assert build_password_blacklist.main(["--check"]) == 0


def test_lista_de_contrasenas_comunes_con_variantes_decoradas():
    entries = (KEYCLOAK_DIR / "common_passwords.txt").read_text(encoding="utf-8").splitlines()
    assert {"password", "password1!", "portal2026!", "ultrasist123!", "proveedor2026#"} <= set(entries)
    # La politica exige letra, digito y caracter especial: sin variantes, la lista no bloquearia ninguna contrasena.
    valid = [e for e in entries if re.search(r"[^\W\d_]", e) and re.search(r"\d", e) and re.search(r"[^\w]|_", e)]
    assert len(valid) > 20000 and all(entry == entry.lower() for entry in entries[1:])


def test_deteccion_de_fuerza_bruta():
    expected = {
        "bruteForceProtected": True,
        "failureFactor": 5,
        "bruteForceStrategy": "MULTIPLE",
        "maxFailureWaitSeconds": 3600,
        "maxDeltaTimeSeconds": 86400,
        "permanentLockout": False,
    }
    assert {key: REALM[key] for key in expected} == expected


def test_sesion_sso_igual_a_la_local_y_eventos():
    assert (REALM["ssoSessionIdleTimeout"], REALM["ssoSessionMaxLifespan"], REALM["rememberMe"]) == (3600, 28800, False)
    assert REALM["eventsEnabled"] and {"UPDATE_PASSWORD", "LOGIN_ERROR"} <= set(REALM["enabledEventTypes"])
    assert not REALM["registrationAllowed"] and not REALM["resetPasswordAllowed"]


def test_roles_del_portal():
    assert {role["name"] for role in REALM["roles"]["realm"]} == {role.value for role in Role}


def test_cliente_web_confidencial_con_pkce():
    web = client(settings.keycloak_client_id)
    assert (web["publicClient"], web["standardFlowEnabled"]) == (False, True)
    assert (web["implicitFlowEnabled"], web["directAccessGrantsEnabled"], web["serviceAccountsEnabled"]) == (
        False,
        False,
        False,
    )
    assert web["attributes"]["pkce.code.challenge.method"] == "S256"
    assert all(uri.endswith("/auth/callback") for uri in web["redirectUris"])
    assert "*" not in json.dumps(web["redirectUris"]) and web["webOrigins"] == []
    [mapper] = web["protocolMappers"]
    assert mapper["protocolMapper"] == "oidc-usermodel-realm-role-mapper"
    assert mapper["config"]["claim.name"] == "realm_access.roles" and mapper["config"]["id.token.claim"] == "true"


def test_cuenta_de_servicio_minima():
    admin = client(settings.keycloak_admin_client_id)
    assert admin["serviceAccountsEnabled"] and not admin["standardFlowEnabled"]
    assert not admin["directAccessGrantsEnabled"] and not admin["publicClient"]
    [service_account] = REALM["users"]  # el unico usuario del realm versionado
    assert service_account["serviceAccountClientId"] == settings.keycloak_admin_client_id
    assert service_account["clientRoles"] == {"realm-management": ["manage-users", "view-users", "query-users"]}
    assert "credentials" not in service_account and "realmRoles" not in service_account


def test_realm_sin_secretos():
    assert client(settings.keycloak_client_id)["secret"] == "${KEYCLOAK_CLIENT_SECRET}"
    assert client(settings.keycloak_admin_client_id)["secret"] == "${KEYCLOAK_ADMIN_CLIENT_SECRET}"
    content = json.dumps(REALM)
    assert settings.keycloak_client_secret.get_secret_value() not in content
    assert settings.keycloak_admin_client_secret.get_secret_value() not in content
    assert '"credentials"' not in content and '"password"' not in content.lower().replace("passwordpolicy", "")


def test_perfil_de_usuario_sin_nombre_obligatorio():
    [provider] = REALM["components"]["org.keycloak.userprofile.UserProfileProvider"]
    profile = json.loads(provider["config"]["kc.user.profile.config"][0])
    attributes = {attribute["name"]: attribute for attribute in profile["attributes"]}
    assert "required" not in attributes["firstName"] and "required" not in attributes["lastName"]
    assert attributes["email"]["permissions"]["edit"] == ["admin"]  # el usuario no cambia el correo del enlace


@pytest.fixture(scope="module")
def keycloak_service() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))["services"]["keycloak"]


def test_servicio_keycloak_version_fija_y_solo_local(keycloak_service):
    assert re.fullmatch(r"quay\.io/keycloak/keycloak:26\.\d+\.\d+", keycloak_service["image"])
    assert keycloak_service["ports"] == ["127.0.0.1:${KEYCLOAK_PORT:-58080}:8080"]
    assert keycloak_service["healthcheck"]["test"][:2] == ["CMD", "bash"]


def test_servicio_keycloak_importa_el_realm_y_la_lista(keycloak_service):
    volumes = keycloak_service["volumes"]
    assert (
        "./infra/keycloak/realm-ultrasist-portal.json:/opt/keycloak/data/import/realm-ultrasist-portal.json:ro"
        in volumes
    )
    assert (
        "./infra/keycloak/common_passwords.txt:/opt/keycloak/data/password-blacklists/common_passwords.txt:ro"
        in volumes
    )
    assert "keycloak-data:/opt/keycloak/data" in volumes
    script = keycloak_service["entrypoint"][-1]
    assert "start-dev --import-realm" in script
    for name in ("KC_BOOTSTRAP_ADMIN_PASSWORD", "KEYCLOAK_CLIENT_SECRET", "KEYCLOAK_ADMIN_CLIENT_SECRET"):
        assert name in script  # sin la variable el contenedor se niega a arrancar
        assert keycloak_service["environment"][name] == f"${{{name}:-}}"
