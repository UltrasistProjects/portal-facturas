"""Inicio de sesion OIDC contra Keycloak: Authorization Code con PKCE S256, state y nonce (add-keycloak-authentication,
D5, D6).

Usa la integracion de Starlette de Authlib. `state`, `nonce` y `code_verifier` viajan en la sesion (cookie firmada)
solo durante la ida y vuelta a Keycloak; el callback los consume. El ID token se valida con:
- la firma, contra el JWKS del realm (Authlib vuelve a leerlo si cambia el `kid`);
- `iss` igual al emisor del realm y `aud` con el client id del portal (Authlib no valida `aud` si no se le pide);
- `exp` vigente con LEEWAY_SECONDS de tolerancia;
- `nonce` igual al de la peticion.

Los access y refresh tokens se descartan: el portal no llama APIs en nombre del usuario.
"""

import httpx
from authlib.integrations.base_client.errors import MismatchingStateError
from authlib.integrations.starlette_client import OAuth, OAuthError
from joserfc.errors import ClaimError, JoseError
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.core.config import settings

LEEWAY_SECONDS = 60
CLIENT_NAME = "keycloak"
# Parametros extra del cliente HTTP de Authlib; las pruebas agregan el transporte del IdP simulado.
_client_overrides: dict = {}
_oauth: OAuth | None = None


class LoginRejected(Exception):
    """Callback invalido. `reason` va a la auditoria: state, nonce, token o idp_error."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class IdentityUnavailable(Exception):
    """Keycloak no respondio (discovery, JWKS o token endpoint)."""


def _client():
    global _oauth
    if _oauth is None:
        oauth = OAuth()
        oauth.register(
            CLIENT_NAME,
            client_id=settings.keycloak_client_id,
            client_secret=settings.keycloak_client_secret.get_secret_value(),
            server_metadata_url=settings.keycloak_metadata_url,
            client_kwargs={
                "scope": "openid",
                "code_challenge_method": "S256",
                "timeout": settings.keycloak_timeout,
                **_client_overrides,
            },
        )
        _oauth = oauth
    return _oauth.create_client(CLIENT_NAME)


def use_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Pruebas: el IdP simulado responde discovery, JWKS y token endpoint sin red. None vuelve a la red."""
    global _oauth
    if transport is None:
        _client_overrides.pop("transport", None)
    else:
        _client_overrides["transport"] = transport
    _oauth = None


def _claims_options() -> dict:
    # Diccionario nuevo en cada validacion: Authlib modifica las opciones que recibe.
    return {
        "iss": {"essential": True, "value": settings.keycloak_issuer},
        "aud": {"essential": True, "value": settings.keycloak_client_id},
        "sub": {"essential": True},
    }


async def authorize_redirect(request: Request, redirect_uri: str, **params) -> RedirectResponse:
    """Redireccion al endpoint de autorizacion. `params` agrega parametros como kc_action=UPDATE_PASSWORD."""
    try:
        return await _client().authorize_redirect(request, redirect_uri, **params)
    except httpx.HTTPError as exc:
        raise IdentityUnavailable() from exc


async def complete_login(request: Request) -> tuple[dict, str]:
    """Valida el callback y devuelve (claims del ID token, ID token). El ID token solo se guarda del lado del servidor
    como id_token_hint del cierre de sesion."""
    try:
        token = await _client().authorize_access_token(request, claims_options=_claims_options(), leeway=LEEWAY_SECONDS)
    except MismatchingStateError:
        raise LoginRejected("state") from None
    except OAuthError:
        # Keycloak redirigio con ?error= o el token endpoint rechazo el codigo (p. ej. code_verifier incorrecto).
        raise LoginRejected("idp_error") from None
    except httpx.HTTPError as exc:
        raise IdentityUnavailable() from exc
    except ClaimError as exc:
        raise LoginRejected("nonce" if exc.claim == "nonce" else "token") from None
    except (JoseError, ValueError):
        raise LoginRejected("token") from None
    claims, id_token = token.get("userinfo"), token.get("id_token")
    if not claims or not id_token:
        raise LoginRejected("token")
    return dict(claims), id_token


async def logout_url(id_token_hint: str | None, post_logout_redirect_uri: str) -> str | None:
    """URL del end_session_endpoint (RP-Initiated Logout). None si Keycloak no responde: el portal igual cierra su
    sesion."""
    try:
        result = await _client().create_logout_url(
            post_logout_redirect_uri=post_logout_redirect_uri,
            id_token_hint=id_token_hint,
            client_id=settings.keycloak_client_id,
        )
    except (httpx.HTTPError, RuntimeError):
        return None
    return result["url"]
