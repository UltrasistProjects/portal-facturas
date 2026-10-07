"""Keycloak simulado para las pruebas (add-keycloak-authentication, D23). Ninguna prueba necesita Keycloak ni red.

- La API de administracion es un IdentityAdmin en memoria (cuentas, roles, contrasenas y acciones requeridas).
- El OIDC del realm (discovery, JWKS, token endpoint y end_session) lo sirve un httpx.MockTransport: el portal usa
  Authlib de verdad, con PKCE, state y nonce. Los ID tokens se firman con un par RSA generado por sesion.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

from app.core.config import settings
from app.services.identity_service import PORTAL_ROLES
from app.services.keycloak_admin import UPDATE_PASSWORD, IdentityAccount, IdentityProviderError

DEFAULT_ROLES = {"offline_access", "uma_authorization", "default-roles-ultrasist-portal"}


@dataclass
class FakeAccount:
    id: str
    email: str
    enabled: bool = True
    roles: set[str] = field(default_factory=set)
    password: str | None = None
    required_actions: list[str] = field(default_factory=list)


@dataclass
class IssuedCode:
    claims: dict
    code_challenge: str
    redirect_uri: str
    key: RSAKey


class FakeKeycloak:
    def __init__(self):
        self.key = RSAKey.generate_key(2048, parameters={"kid": "portal-test", "use": "sig", "alg": "RS256"})
        self.foreign_key = RSAKey.generate_key(2048, parameters={"kid": "portal-test", "use": "sig", "alg": "RS256"})
        self.accounts: dict[str, FakeAccount] = {}
        self.codes: dict[str, IssuedCode] = {}
        self.transport = httpx.MockTransport(self._handle)
        self.reset()

    def reset(self) -> None:
        """Estado transitorio de cada prueba; las cuentas sembradas se conservan."""
        self.unavailable = False  # la API de administracion no responde
        self.oidc_unavailable = False  # discovery, JWKS y token endpoint no responden
        self.rejected_emails: set[str] = set()  # create_user responde 400 para estos correos
        self.calls: list[str] = []
        self.logouts: list[str] = []
        self.token_requests: list[dict] = []
        self.admin_tokens: set[str] = set()  # tokens vigentes de la cuenta de servicio; vaciarlo simula su expiracion

    # --- URLs del realm -------------------------------------------------------------------------------------------

    @property
    def issuer(self) -> str:
        return settings.keycloak_issuer

    @property
    def authorization_endpoint(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/auth"

    @property
    def end_session_endpoint(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/logout"

    # --- IdentityAdmin (en memoria) -------------------------------------------------------------------------------

    def _check(self, operation: str) -> None:
        self.calls.append(operation)
        if self.unavailable:
            raise IdentityProviderError(operation, "unavailable")

    def _find(self, email: str) -> FakeAccount | None:
        return next((account for account in self.accounts.values() if account.email == email.lower()), None)

    @staticmethod
    def _public(account: FakeAccount) -> IdentityAccount:
        return IdentityAccount(account.id, account.email, account.enabled, tuple(account.required_actions))

    def find_by_email(self, email: str) -> IdentityAccount | None:
        self._check("find_user")
        account = self._find(email)
        return None if account is None else self._public(account)

    def get_user(self, user_id: str) -> IdentityAccount | None:
        self._check("get_user")
        account = self.accounts.get(user_id)
        return None if account is None else self._public(account)

    def create_user(self, email: str, *, enabled: bool = True) -> str:
        self._check("create_user")
        if email.lower() in self.rejected_emails:
            raise IdentityProviderError("create_user", "http_400")
        if self._find(email) is not None:
            raise IdentityProviderError("create_user", "http_409")
        account = FakeAccount(str(uuid.uuid4()), email.lower(), enabled)
        self.accounts[account.id] = account
        return account.id

    def realm_roles(self, user_id: str) -> set[str]:
        self._check("get_roles")
        return set(self.accounts[user_id].roles) | DEFAULT_ROLES

    def assign_realm_role(self, user_id: str, role: str) -> None:
        self._check("assign_role")
        self.accounts[user_id].roles.add(role)

    def set_password(self, user_id: str, password: str, *, temporary: bool) -> None:
        self._check("reset_password")
        account = self.accounts[user_id]
        account.password = password
        account.required_actions = [UPDATE_PASSWORD] if temporary else []

    def set_enabled(self, user_id: str, enabled: bool) -> None:
        self._check("update_user")
        self.accounts[user_id].enabled = enabled

    def logout(self, user_id: str) -> None:
        self._check("logout_user")
        self.logouts.append(user_id)

    # --- Ayudas de las pruebas ------------------------------------------------------------------------------------

    def account(self, email: str) -> FakeAccount:
        account = self._find(email)
        assert account is not None, f"Sin cuenta de Keycloak para {email}"
        return account

    def add_account(self, email: str, *roles: str, enabled: bool = True) -> FakeAccount:
        """Cuenta que ya existia en Keycloak (creada fuera del portal)."""
        account = FakeAccount(str(uuid.uuid4()), email.lower(), enabled, set(roles))
        self.accounts[account.id] = account
        return account

    def change_password(self, email: str, password: str) -> None:
        """El usuario cambia la contrasena en Keycloak (primer acceso): desaparece UPDATE_PASSWORD."""
        account = self.account(email)
        account.password = password
        account.required_actions = []

    def authorize(self, email: str, params: dict[str, str], *, foreign_key: bool = False, **overrides) -> str:
        """Simula el inicio de sesion en la pagina de Keycloak y devuelve el `code` del callback. `overrides` cambia o
        quita (None) claims del ID token; `roles` reemplaza los realm roles."""
        account = self.account(email)
        now = int(time.time())
        roles = overrides.pop("roles", None)
        claims = {
            "iss": self.issuer,
            "sub": account.id,
            "aud": settings.keycloak_client_id,
            "azp": settings.keycloak_client_id,
            "exp": now + 300,
            "iat": now,
            "nonce": params.get("nonce"),
            "email": account.email,
            "realm_access": {"roles": sorted((account.roles if roles is None else set(roles)) | DEFAULT_ROLES)},
        }
        for name, value in overrides.items():
            if value is None:
                claims.pop(name, None)
            else:
                claims[name] = value
        code = secrets.token_urlsafe(24)
        key = self.foreign_key if foreign_key else self.key
        self.codes[code] = IssuedCode(claims, params["code_challenge"], params["redirect_uri"], key)
        return code

    # --- HTTP: OIDC y API de administracion (httpx.MockTransport o servidor local) -----------------------------------

    def _handle(self, request: httpx.Request) -> httpx.Response:
        """Enruta por ruta (no por host): el mismo simulador sirve al MockTransport y al servidor local de
        FakeKeycloakServer."""
        path = request.url.path
        realm = f"/realms/{settings.keycloak_realm}"
        admin = f"/admin/realms/{settings.keycloak_realm}"
        if path.startswith(admin + "/"):
            return self._admin(request, admin)
        if self.oidc_unavailable:
            raise httpx.ConnectError("Keycloak simulado sin servicio", request=request)
        if path == f"{realm}/.well-known/openid-configuration":
            return httpx.Response(200, json=self.metadata())
        if path == f"{realm}/protocol/openid-connect/certs":
            return httpx.Response(200, json=KeySet([self.key]).as_dict(private=False))
        if path == f"{realm}/protocol/openid-connect/token" and request.method == "POST":
            return self._token(request)
        return httpx.Response(404, json={"error": "not_found"})

    def metadata(self) -> dict:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": f"{self.issuer}/protocol/openid-connect/token",
            "jwks_uri": f"{self.issuer}/protocol/openid-connect/certs",
            "end_session_endpoint": self.end_session_endpoint,
            "id_token_signing_alg_values_supported": ["RS256"],
            "code_challenge_methods_supported": ["S256"],
        }

    @staticmethod
    def _basic_client(request: httpx.Request) -> tuple[str, str] | None:
        scheme, _, encoded = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "basic":
            return None
        client_id, _, secret = base64.b64decode(encoded).decode().partition(":")
        return unquote(client_id), unquote(secret)

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        self.token_requests.append(form)
        client = self._basic_client(request)
        if form.get("grant_type") == "client_credentials":
            # Cuenta de servicio del portal (API de administracion).
            if client != (settings.keycloak_admin_client_id, settings.keycloak_admin_client_secret.get_secret_value()):
                return httpx.Response(401, json={"error": "invalid_client"})
            token = secrets.token_urlsafe(16)
            self.admin_tokens.add(token)
            return httpx.Response(200, json={"access_token": token, "token_type": "Bearer", "expires_in": 300})
        if client != (settings.keycloak_client_id, settings.keycloak_client_secret.get_secret_value()):
            return httpx.Response(401, json={"error": "invalid_client"})
        issued = self.codes.pop(form.get("code", ""), None)
        if issued is None or form.get("redirect_uri") != issued.redirect_uri:
            return httpx.Response(400, json={"error": "invalid_grant"})
        verifier = form.get("code_verifier", "")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        if challenge != issued.code_challenge:
            return httpx.Response(400, json={"error": "invalid_grant", "error_description": "PKCE verification failed"})
        id_token = jwt.encode({"alg": "RS256", "kid": issued.key.kid}, issued.claims, issued.key)
        body = {
            "access_token": secrets.token_urlsafe(24),
            "token_type": "Bearer",
            "expires_in": 300,
            "id_token": id_token,
        }
        return httpx.Response(200, json=body)

    @staticmethod
    def _representation(account: FakeAccount) -> dict:
        return {
            "id": account.id,
            "username": account.email,
            "email": account.email,
            "emailVerified": True,
            "enabled": account.enabled,
            "requiredActions": list(account.required_actions),
        }

    def _admin(self, request: httpx.Request, base: str) -> httpx.Response:
        """API de administracion del realm, con las rutas que usa KeycloakAdmin."""
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme != "Bearer" or token not in self.admin_tokens:
            return httpx.Response(401, json={"error": "HTTP 401 Unauthorized"})
        if self.unavailable:
            return httpx.Response(503, json={"error": "unavailable"})
        parts = request.url.path[len(base) :].strip("/").split("/")
        body = json.loads(request.content) if request.content else None
        method = request.method
        try:
            if parts == ["users"] and method == "GET":
                found = self._find(request.url.params.get("email", ""))
                return httpx.Response(200, json=[self._representation(found)] if found else [])
            if parts == ["users"] and method == "POST":
                user_id = self.create_user(body["email"], enabled=body.get("enabled", True))
                location = f"{request.url.scheme}://{request.url.netloc.decode()}{base}/users/{user_id}"
                return httpx.Response(201, headers={"Location": location})
            user_id, action = parts[1], parts[2:]
            if user_id not in self.accounts:
                return httpx.Response(404, json={"error": "User not found"})
            if action == [] and method == "GET":
                return httpx.Response(200, json=self._representation(self.get_user_account(user_id)))
            if action == [] and method == "PUT":
                self.set_enabled(user_id, bool(body["enabled"]))
                return httpx.Response(204)
            if action == ["reset-password"] and method == "PUT":
                self.set_password(user_id, body["value"], temporary=bool(body["temporary"]))
                return httpx.Response(204)
            if action == ["logout"] and method == "POST":
                self.logout(user_id)
                return httpx.Response(204)
            if action == ["role-mappings", "realm", "composite"] and method == "GET":
                return httpx.Response(200, json=[{"name": role} for role in sorted(self.realm_roles(user_id))])
            if action == ["role-mappings", "realm", "available"] and method == "GET":
                assigned = self.accounts[user_id].roles
                available = [{"id": f"id-{role}", "name": role} for role in sorted(PORTAL_ROLES - assigned)]
                return httpx.Response(200, json=available)
            if action == ["role-mappings", "realm"] and method == "POST":
                for role in body:
                    self.assign_realm_role(user_id, role["name"])
                return httpx.Response(204)
        except IdentityProviderError as exc:
            status = 503 if exc.code == "unavailable" else int(exc.code.removeprefix("http_"))
            return httpx.Response(status, json={"error": exc.code})
        return httpx.Response(404, json={"error": "not_found"})

    def get_user_account(self, user_id: str) -> FakeAccount:
        self._check("get_user")
        return self.accounts[user_id]


class FakeKeycloakServer:
    """El simulador en un servidor HTTP local (127.0.0.1, puerto libre) para los scripts que corren en un subproceso
    (init_db, reset_demo): no pueden recibir el simulador en memoria. No sale a la red."""

    def __init__(self, keycloak: FakeKeycloak):
        self.keycloak = keycloak
        handle = keycloak._handle

        class Handler(BaseHTTPRequestHandler):
            def _serve(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                request = httpx.Request(
                    self.command,
                    f"http://{self.headers['Host']}{self.path}",
                    headers=dict(self.headers.items()),
                    content=self.rfile.read(length) if length else b"",
                )
                response = handle(request)
                self.send_response(response.status_code)
                for name, value in response.headers.items():
                    if name.lower() not in {"content-length", "transfer-encoding", "connection", "content-encoding"}:
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(response.content)))
                self.end_headers()
                self.wfile.write(response.content)

            do_GET = do_POST = do_PUT = _serve

            def log_message(self, *_args) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> "FakeKeycloakServer":
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._server.shutdown()
        self._server.server_close()


def query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
