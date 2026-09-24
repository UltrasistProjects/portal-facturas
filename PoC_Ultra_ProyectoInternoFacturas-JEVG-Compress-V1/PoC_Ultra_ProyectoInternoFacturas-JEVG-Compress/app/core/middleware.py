"""Middlewares ASGI puros: cubren tambien StaticFiles, FileResponse y las respuestas de error."""

import re
import uuid
from contextvars import ContextVar

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Viable sin excepciones: todos los assets son locales y no hay scripts ni estilos en linea. Bootstrap usa
# imagenes SVG en data: URIs, por eso img-src admite data:.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}
STRICT_TRANSPORT_SECURITY = "max-age=31536000"

REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9-]{8,64}")
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


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

        token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_var.reset(token)
