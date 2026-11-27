"""Llamadas HTTP de los analizadores: plazo total por servicio, errores como AnalyzerUnavailable con su motivo y log
sin llaves ni contenido del documento (spec de observabilidad: evento, proveedor, duracion y resultado)."""

from __future__ import annotations

import logging
import ssl
import time
from collections.abc import Callable
from functools import cache

import certifi
import httpx

from app.services.ai.base import (
    AUTH,
    INVALID_RESPONSE,
    NETWORK,
    NOT_FOUND,
    QUOTA,
    SERVICE,
    TIMEOUT,
    AnalyzerUnavailable,
)

logger = logging.getLogger("app.services.ai")

Clock = Callable[[], float]


@cache
def ssl_context() -> ssl.SSLContext:
    """Un solo contexto TLS por proceso: cargar los certificados cuesta segundos en Windows y en cada arranque en frio
    de Vercel; reutilizarlo deja la creacion de cada cliente en milisegundos."""
    return ssl.create_default_context(cafile=certifi.where())


def client(transport: httpx.BaseTransport | None, headers: dict[str, str]) -> httpx.Client:
    """Cliente HTTP de un analizador; las pruebas pasan un transporte falso (sin red ni TLS)."""
    if transport is not None:
        return httpx.Client(transport=transport, headers=headers)
    return httpx.Client(verify=ssl_context(), headers=headers)  # pragma: no cover - solo con red real


def ms(seconds: float) -> int:
    return round(seconds * 1000)


def reason_for_status(status_code: int) -> str:
    if status_code in (401, 403):
        return AUTH
    if status_code == 404:
        return NOT_FOUND
    if status_code == 429:
        return QUOTA
    if status_code in (400, 413, 415, 422):
        return INVALID_RESPONSE  # el servicio rechazo la peticion: documento o parametros no admitidos
    return SERVICE


class Deadline:
    """Plazo total de un servicio: cada peticion espera, como mucho, lo que queda de el."""

    def __init__(self, seconds: float, clock: Clock = time.monotonic):
        self.clock = clock
        self.expires = clock() + seconds

    def remaining(self) -> float:
        return self.expires - self.clock()

    def check(self, service: str) -> float:
        remaining = self.remaining()
        if remaining <= 0:
            raise AnalyzerUnavailable(f"{service}: tiempo agotado", TIMEOUT)
        return remaining


def send(client: httpx.Client, method: str, url: str, deadline: Deadline, service: str, **kwargs) -> httpx.Response:
    """Peticion con el tiempo que queda del plazo; un error de red, de tiempo o HTTP >= 400 es AnalyzerUnavailable.
    El mensaje nunca incluye el cuerpo de la respuesta (puede repetir el documento) ni las cabeceras (la llave)."""
    remaining = deadline.check(service)
    try:
        response = client.request(method, url, timeout=httpx.Timeout(remaining), **kwargs)
    except httpx.TimeoutException as exc:
        raise AnalyzerUnavailable(f"{service}: tiempo agotado", TIMEOUT) from exc
    except httpx.HTTPError as exc:
        raise AnalyzerUnavailable(f"{service}: sin conexion ({type(exc).__name__})", NETWORK) from exc
    if response.status_code >= 400:
        reason = reason_for_status(response.status_code)
        raise AnalyzerUnavailable(f"{service}: HTTP {response.status_code}", reason)
    return response


def json_body(response: httpx.Response, service: str) -> dict:
    try:
        body = response.json()
    except ValueError as exc:
        raise AnalyzerUnavailable(f"{service}: respuesta que no es JSON", INVALID_RESPONSE) from exc
    if not isinstance(body, dict):
        raise AnalyzerUnavailable(f"{service}: respuesta inesperada", INVALID_RESPONSE)
    return body


def log_call(event: str, provider: str, started: float, outcome: str, clock: Clock = time.monotonic, **fields) -> int:
    """Registra la llamada (sin datos fiscales) y devuelve su duracion en milisegundos."""
    duration = ms(clock() - started)
    level = logging.INFO if outcome == "ok" else logging.WARNING
    logger.log(
        level,
        event,
        extra={"event": event, "provider": provider, "duration_ms": duration, "outcome": outcome, **fields},
    )
    return duration
