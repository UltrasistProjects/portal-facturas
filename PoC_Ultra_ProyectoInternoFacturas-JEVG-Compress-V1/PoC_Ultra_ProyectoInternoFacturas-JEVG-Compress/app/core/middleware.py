"""Middlewares ASGI puros: cubren tambien StaticFiles, FileResponse y las respuestas de error."""

import re
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings


def content_security_policy(keycloak_origin: str, style_hashes: Sequence[str] = ()) -> str:
    """Viable sin excepciones: todos los assets son locales y no hay scripts ni estilos en linea. Bootstrap usa
    imagenes SVG en data: URIs, por eso img-src admite data:. form-action admite ademas el origen de Keycloak:
    Chrome aplica form-action a la redireccion que sigue a POST /logout (end_session_endpoint).

    `style_hashes` solo lo usa la vista previa del correo (HU-05): su iframe srcdoc hereda esta politica y necesita
    los atributos style del correo. 'unsafe-hashes' admite exactamente esos valores y ningun otro estilo en linea."""
    policy = (
        "default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; "
        f"form-action 'self' {keycloak_origin}; frame-ancestors 'none'"
    )
    if style_hashes:
        policy += f"; style-src 'self' 'unsafe-hashes' {' '.join(style_hashes)}"
    return policy


CONTENT_SECURITY_POLICY = content_security_policy(settings.keycloak_origin)


def content_security_policy_with_styles(style_hashes: Sequence[str]) -> str:
    """La CSP del portal con los atributos style de `style_hashes` admitidos (vista previa del correo)."""
    return content_security_policy(settings.keycloak_origin, style_hashes)


SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}
STRICT_TRANSPORT_SECURITY = "max-age=31536000"

REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9-]{8,64}")

# Contexto de la peticion para el log. Es un dict mutable: los endpoints y dependencias sincronos corren en un
# threadpool con una copia del contexto, y solo compartiendo la misma referencia el user_id llega de vuelta.
_request_context: ContextVar[dict | None] = ContextVar("request_context", default=None)


def request_context() -> dict:
    return _request_context.get() or {}


def bind_user(user_id: int) -> None:
    context = _request_context.get()
    if context is not None:
        context["user_id"] = user_id


@contextmanager
def request_scope(request_id: str | None, user_id: int | None = None) -> Iterator[dict]:
    context = {"request_id": request_id, "user_id": user_id}
    token = _request_context.set(context)
    try:
        yield context
    finally:
        _request_context.reset(token)


def security_headers(scheme: str) -> dict[str, str]:
    headers = dict(SECURITY_HEADERS)
    if scheme == "https":
        headers["Strict-Transport-Security"] = STRICT_TRANSPORT_SECURITY
    return headers


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        extra = security_headers(scope.get("scheme", "http"))

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in extra.items():
                    # La vista previa del correo trae su propia CSP, armada con content_security_policy().
                    if name == "Content-Security-Policy" and name in headers:
                        continue
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestContextMiddleware:
    """Asigna un request_id por peticion (reutiliza un X-Request-ID entrante valido) y lo devuelve en la respuesta."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = Headers(scope=scope).get("x-request-id", "")
        request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else uuid.uuid4().hex
        # En scope["state"] para que el handler de 500 (externo a este middleware) lo encuentre en request.state.
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        with request_scope(request_id):
            await self.app(scope, receive, send_with_request_id)
