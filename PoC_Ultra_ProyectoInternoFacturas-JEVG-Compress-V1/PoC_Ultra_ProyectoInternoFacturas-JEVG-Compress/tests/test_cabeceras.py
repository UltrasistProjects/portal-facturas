import re

import pytest
from fastapi.testclient import TestClient

from app.core.middleware import CONTENT_SECURITY_POLICY, content_security_policy
from tests.conftest import login

EXPECTED = {
    "content-security-policy": CONTENT_SECURITY_POLICY,
    "x-frame-options": "DENY",
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
}


def assert_security_headers(response):
    for name, value in EXPECTED.items():
        assert response.headers.get(name) == value, name


def test_csp_exacta():
    # form-action admite el origen de Keycloak: la redireccion de POST /logout va a su end_session_endpoint.
    assert CONTENT_SECURITY_POLICY == (
        "default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; "
        "form-action 'self' http://keycloak.test; frame-ancestors 'none'"
    )


def test_csp_admite_solo_el_origen_de_keycloak():
    policy = content_security_policy("http://127.0.0.1:58080")
    assert "form-action 'self' http://127.0.0.1:58080;" in policy
    assert policy.count("http") == 1


@pytest.mark.parametrize("path", ["/login", "/static/css/app.css", "/ruta-inexistente", "/health"])
def test_cabeceras_en_paginas_estaticos_y_errores(client, path):
    response = client.get(path, follow_redirects=False)
    assert_security_headers(response)
    assert "strict-transport-security" not in response.headers


def test_hsts_solo_sobre_https():
    from app.main import app

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/login", follow_redirects=False)
    assert response.headers["strict-transport-security"] == "max-age=31536000"


def test_request_id_generado_y_reutilizado(client):
    generated = client.get("/login").headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{32}", generated)
    assert client.get("/login", headers={"X-Request-ID": "abcd-1234-efgh"}).headers["x-request-id"] == "abcd-1234-efgh"
    replaced = client.get("/login", headers={"X-Request-ID": "<script>"}).headers["x-request-id"]
    assert replaced != "<script>" and re.fullmatch(r"[0-9a-f]{32}", replaced)


def test_error_500_con_cabeceras_y_referencia(monkeypatch):
    import app.routers.dashboard as dashboard
    from app.main import app

    def boom(*_args, **_kwargs):
        raise RuntimeError("fallo")

    monkeypatch.setattr(dashboard, "status_counts", boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        login(client)
        response = client.get("/", headers={"X-Request-ID": "soporte-500-abc"})
    assert response.status_code == 500
    assert_security_headers(response)
    assert response.headers["x-request-id"] == "soporte-500-abc"
    assert "soporte-500-abc" in response.text


def test_sin_cors():
    from app.main import app

    assert all(middleware.cls.__name__ != "CORSMiddleware" for middleware in app.user_middleware)


def test_plantillas_sin_scripts_ni_estilos_en_linea():
    from tests.conftest import ROOT

    for template in (ROOT / "app" / "templates").rglob("*.html"):
        source = template.read_text(encoding="utf-8")
        assert "<style" not in source, template.name
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", source), template.name
        assert not re.search(r"\sstyle=", source), template.name
        assert not re.search(r"\son[a-z]+=", source), template.name
