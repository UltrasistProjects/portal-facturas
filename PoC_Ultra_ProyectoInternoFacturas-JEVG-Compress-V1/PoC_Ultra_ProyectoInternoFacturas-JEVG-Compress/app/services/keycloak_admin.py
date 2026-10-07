"""Cliente de la API de administracion de Keycloak (add-keycloak-authentication, D11).

Usa la cuenta de servicio `portal-facturas-admin` (client credentials), que solo tiene manage-users, view-users y
query-users del cliente realm-management.

- Cada llamada tiene el timeout de KEYCLOAK_TIMEOUT.
- Errores de red, timeouts y respuestas inesperadas se traducen a IdentityProviderError (HTTP 503): nunca un
  traceback.
- El log registra la operacion, el codigo HTTP y la duracion; nunca cuerpos, tokens ni contrasenas.
- Tras un fallo de disponibilidad, las llamadas fallan de inmediato durante FAIL_FAST_SECONDS: una autorizacion masiva
  con Keycloak caido no espera el timeout por cada proveedor.

Las pruebas sustituyen el cliente con set_identity_admin(); ninguna necesita Keycloak ni red.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.core.errors import BusinessRuleError

logger = logging.getLogger(__name__)

MSG_UNAVAILABLE = "El servicio de identidad no está disponible. Intente más tarde."
UPDATE_PASSWORD = "UPDATE_PASSWORD"
# El token de la cuenta de servicio se renueva este margen antes de expirar.
TOKEN_MARGIN_SECONDS = 30
FAIL_FAST_SECONDS = 30


class IdentityProviderError(BusinessRuleError):
    """Keycloak no respondio o respondio algo inesperado. `code` va a la auditoria: unavailable, http_<estado>,
    invalid_response o role_not_found."""

    status_code = 503

    def __init__(self, operation: str, code: str):
        super().__init__(MSG_UNAVAILABLE)
        self.operation = operation
        self.code = code


@dataclass(frozen=True)
class IdentityAccount:
    """Cuenta de Keycloak, solo con lo que usa el portal."""

    id: str
    email: str
    enabled: bool
    required_actions: tuple[str, ...] = ()

    @property
    def password_pending(self) -> bool:
        """Conserva la contrasena temporal: Keycloak le exigira cambiarla en su siguiente acceso."""
        return UPDATE_PASSWORD in self.required_actions


class IdentityAdmin(Protocol):
    def find_by_email(self, email: str) -> IdentityAccount | None: ...

    def get_user(self, user_id: str) -> IdentityAccount | None: ...

    def create_user(self, email: str, *, enabled: bool = True) -> str: ...

    def realm_roles(self, user_id: str) -> set[str]: ...

    def assign_realm_role(self, user_id: str, role: str) -> None: ...

    def set_password(self, user_id: str, password: str, *, temporary: bool) -> None: ...

    def set_enabled(self, user_id: str, enabled: bool) -> None: ...

    def logout(self, user_id: str) -> None: ...


def _account(representation: dict) -> IdentityAccount:
    try:
        return IdentityAccount(
            id=representation["id"],
            email=(representation.get("email") or "").lower(),
            enabled=bool(representation.get("enabled")),
            required_actions=tuple(representation.get("requiredActions") or ()),
        )
    except (KeyError, TypeError, AttributeError):
        raise IdentityProviderError("read_user", "invalid_response") from None


class KeycloakAdmin:
    """Implementacion HTTP de IdentityAdmin contra la API de administracion del realm."""

    def __init__(self, transport: httpx.BaseTransport | None = None, clock: Callable[[], float] = time.monotonic):
        self._client = httpx.Client(timeout=settings.keycloak_timeout, transport=transport)
        self._clock = clock
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._unavailable_until = 0.0
        self._lock = threading.Lock()

    # --- Transporte ---------------------------------------------------------------------------------------------

    def _url(self, *parts: str) -> str:
        return "/".join([settings.keycloak_admin_url, *(quote(part, safe="") for part in parts)])

    def _log(self, operation: str, status: int | None, started: float) -> None:
        logger.info(
            "keycloak.admin",
            extra={
                "event": "keycloak.admin",
                "operation": operation,
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )

    def _request(self, operation: str, method: str, url: str, **kwargs) -> httpx.Response:
        if self._clock() < self._unavailable_until:
            raise IdentityProviderError(operation, "unavailable")
        started = time.perf_counter()
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.HTTPError:
            self._log(operation, None, started)
            self._unavailable_until = self._clock() + FAIL_FAST_SECONDS
            raise IdentityProviderError(operation, "unavailable") from None
        self._log(operation, response.status_code, started)
        if response.status_code >= 500:
            self._unavailable_until = self._clock() + FAIL_FAST_SECONDS
            raise IdentityProviderError(operation, "unavailable")
        return response

    def _access_token(self, refresh: bool = False) -> str:
        with self._lock:
            if not refresh and self._token and self._clock() < self._token_expires_at:
                return self._token
            response = self._request(
                "service_token",
                "POST",
                f"{settings.keycloak_issuer}/protocol/openid-connect/token",
                data={"grant_type": "client_credentials"},
                auth=(settings.keycloak_admin_client_id, settings.keycloak_admin_client_secret.get_secret_value()),
            )
            if response.status_code != 200:
                raise IdentityProviderError("service_token", f"http_{response.status_code}")
            try:
                payload = response.json()
                self._token = str(payload["access_token"])
                expires_in = int(payload.get("expires_in", 60))
            except (ValueError, KeyError, TypeError):
                raise IdentityProviderError("service_token", "invalid_response") from None
            self._token_expires_at = self._clock() + max(0, expires_in - TOKEN_MARGIN_SECONDS)
            return self._token

    def _call(
        self,
        operation: str,
        method: str,
        url: str,
        *,
        expected: tuple[int, ...] = (200,),
        allow_404: bool = False,
        **kw,
    ) -> httpx.Response | None:
        """Llamada autenticada con el token de la cuenta de servicio; un 401 renueva el token una vez."""
        for refresh in (False, True):
            headers = {"Authorization": f"Bearer {self._access_token(refresh=refresh)}"}
            response = self._request(operation, method, url, headers=headers, **kw)
            if response.status_code != 401:
                break
        if allow_404 and response.status_code == 404:
            return None
        if response.status_code not in expected:
            raise IdentityProviderError(operation, f"http_{response.status_code}")
        return response

    @staticmethod
    def _json(response: httpx.Response, operation: str):
        try:
            return response.json()
        except ValueError:
            raise IdentityProviderError(operation, "invalid_response") from None

    # --- Operaciones --------------------------------------------------------------------------------------------

    def find_by_email(self, email: str) -> IdentityAccount | None:
        response = self._call("find_user", "GET", self._url("users"), params={"email": email, "exact": "true"})
        wanted = email.lower()
        for representation in self._json(response, "find_user"):
            if (representation.get("email") or "").lower() == wanted:
                return _account(representation)
        return None

    def get_user(self, user_id: str) -> IdentityAccount | None:
        response = self._call("get_user", "GET", self._url("users", user_id), allow_404=True)
        return None if response is None else _account(self._json(response, "get_user"))

    def create_user(self, email: str, *, enabled: bool = True) -> str:
        """Crea la cuenta sin nombre: la razon social puede traer caracteres que Keycloak rechaza en nombres de persona,
        y el perfil de usuario del realm no exige nombre ni apellido. Devuelve su id (el `sub` de sus tokens)."""
        body = {"username": email, "email": email, "emailVerified": True, "enabled": enabled}
        response = self._call("create_user", "POST", self._url("users"), json=body, expected=(201,))
        user_id = response.headers.get("Location", "").rstrip("/").rsplit("/", 1)[-1]
        if not user_id or user_id == "users":
            raise IdentityProviderError("create_user", "invalid_response")
        return user_id

    def realm_roles(self, user_id: str) -> set[str]:
        """Realm roles efectivos de la cuenta (incluye los compuestos)."""
        url = self._url("users", user_id, "role-mappings", "realm", "composite")
        response = self._call("get_roles", "GET", url)
        return {role.get("name") for role in self._json(response, "get_roles")}

    def assign_realm_role(self, user_id: str, role: str) -> None:
        """Asigna el realm role. Se toma de los roles disponibles para la cuenta: la cuenta de servicio no tiene
        view-realm para leer el catalogo de roles."""
        url = self._url("users", user_id, "role-mappings", "realm")
        available = self._json(self._call("available_roles", "GET", f"{url}/available"), "available_roles")
        match = next((item for item in available if item.get("name") == role), None)
        if match is None:
            if role in self.realm_roles(user_id):
                return  # ya lo tiene
            raise IdentityProviderError("assign_role", "role_not_found")
        self._call("assign_role", "POST", url, json=[{"id": match["id"], "name": role}], expected=(204,))

    def set_password(self, user_id: str, password: str, *, temporary: bool) -> None:
        """Con temporary=True, Keycloak agrega la accion requerida UPDATE_PASSWORD (primer acceso, RF-06)."""
        body = {"type": "password", "value": password, "temporary": temporary}
        self._call("reset_password", "PUT", self._url("users", user_id, "reset-password"), json=body, expected=(204,))

    def set_enabled(self, user_id: str, enabled: bool) -> None:
        """Lee la representacion completa y la devuelve con `enabled` cambiado: una representacion parcial podria
        vaciar atributos del perfil."""
        url = self._url("users", user_id)
        representation = self._json(self._call("get_user", "GET", url), "get_user")
        representation["enabled"] = enabled
        self._call("update_user", "PUT", url, json=representation, expected=(204,))

    def logout(self, user_id: str) -> None:
        """Cierra todas las sesiones de la cuenta en Keycloak."""
        self._call("logout_user", "POST", self._url("users", user_id, "logout"), expected=(204,))


_admin: IdentityAdmin | None = None


def get_identity_admin() -> IdentityAdmin:
    global _admin
    if _admin is None:
        _admin = KeycloakAdmin()
    return _admin


def set_identity_admin(admin: IdentityAdmin | None) -> IdentityAdmin | None:
    """Sustituye el cliente (pruebas) y devuelve el anterior; con None vuelve a crearse el HTTP al pedirlo."""
    global _admin
    previous, _admin = _admin, admin
    return previous
