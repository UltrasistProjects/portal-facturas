import base64
import json
import os
import subprocess
import sys
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import User, UserSession
from app.services import session_service
from tests.conftest import ROOT, csrf, login

COOKIE = "invoice_portal_session"


def session_data(client) -> dict:
    """Contenido de la cookie firmada de Starlette (base64 de JSON + firma)."""
    payload = client.cookies.get(COOKIE).split(".")[0]
    return json.loads(base64.b64decode(payload + "=" * (-len(payload) % 4)))


def reuse(client, cookie: str):
    client.cookies.clear()
    client.cookies.set(COOKIE, cookie)
    return client.get("/", follow_redirects=False)


def test_cookie_solo_lleva_identificador_opaco_y_csrf(client):
    login(client)
    client.get("/")
    data = session_data(client)
    assert set(data) == {"sid", "csrf_token"}
    with SessionLocal() as db:
        stored = db.scalar(select(UserSession).where(UserSession.sid_hash == session_service.hash_sid(data["sid"])))
        assert stored is not None
        columns = {attr.key: getattr(stored, attr.key) for attr in UserSession.__mapper__.column_attrs}
    assert data["sid"] not in json.dumps(columns, default=str)


def test_cookie_reutilizada_tras_logout(client):
    login(client)
    captured = client.cookies.get(COOKIE)
    assert client.get("/", follow_redirects=False).status_code == 200
    client.post("/logout", data={"csrf_token": csrf(client, "/")})
    response = reuse(client, captured)
    assert response.status_code == 303 and response.headers["location"] == "/login"


def test_expiracion_por_inactividad(client, monkeypatch):
    login(client)
    start = session_service.utcnow()
    monkeypatch.setattr(session_service, "utcnow", lambda: start + timedelta(minutes=59))
    assert client.get("/", follow_redirects=False).status_code == 200  # la actividad renueva la sesion
    monkeypatch.setattr(session_service, "utcnow", lambda: start + timedelta(minutes=59 + 61))
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.get("/login").status_code == 200  # sin ciclo de redirecciones


def test_expiracion_absoluta(client, monkeypatch):
    login(client)
    start = session_service.utcnow()
    for minutes in range(50, 8 * 60, 50):  # actividad continua cada 50 minutos
        monkeypatch.setattr(session_service, "utcnow", lambda m=minutes: start + timedelta(minutes=m))
        assert client.get("/", follow_redirects=False).status_code == 200
    monkeypatch.setattr(session_service, "utcnow", lambda: start + timedelta(hours=8, minutes=1))
    assert client.get("/", follow_redirects=False).status_code == 303


def test_deshabilitar_usuario_revoca_sus_sesiones():
    from app.main import app

    with TestClient(app) as provider, TestClient(app) as admin:
        login(provider, "proveedor2@poc.local")
        assert provider.get("/", follow_redirects=False).status_code == 200
        login(admin)
        with SessionLocal() as db:
            target = db.scalar(select(User.id).where(User.email == "proveedor2@poc.local"))
        toggle = f"/admin/users/{target}/toggle"
        admin.post(toggle, data={"csrf_token": csrf(admin, "/admin/users")})
        try:
            assert provider.get("/", follow_redirects=False).status_code == 303
            with SessionLocal() as db:
                active = db.scalars(
                    select(UserSession).where(UserSession.user_id == target, UserSession.revoked_at.is_(None))
                ).all()
            assert active == []
        finally:
            admin.post(toggle, data={"csrf_token": csrf(admin, "/admin/users")})  # rehabilita para otras pruebas


def test_fijacion_de_sesion(client):
    login(client)
    first_cookie, first_sid = client.cookies.get(COOKIE), session_data(client)["sid"]
    login(client, "pmo@poc.local")
    assert session_data(client)["sid"] != first_sid
    assert reuse(client, first_cookie).status_code == 303


def test_cookie_secure_segun_configuracion(tmp_path):
    code = (
        "from starlette.middleware.sessions import SessionMiddleware; from app.main import app;"
        "print(next(m.kwargs['https_only'] for m in app.user_middleware if m.cls is SessionMiddleware))"
    )
    env = {k: v for k, v in os.environ.items() if k != "SESSION_HTTPS_ONLY"}
    env.update({"APP_ENV": "production", "LOG_DIR": str(tmp_path), "PYTHONPATH": str(ROOT)})
    result = subprocess.run([sys.executable, "-c", code], env=env, cwd=ROOT, capture_output=True, text=True, check=True)
    assert result.stdout.strip().splitlines()[-1] == "True"


def test_cookie_secure_emitida_sobre_https():
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.sessions import SessionMiddleware
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    from app.main import app as portal

    kwargs = next(m.kwargs for m in portal.user_middleware if m.cls is SessionMiddleware)

    def set_session(request):
        request.session["sid"] = "x"
        return PlainTextResponse("ok")

    probe = Starlette(
        routes=[Route("/", set_session)], middleware=[Middleware(SessionMiddleware, **{**kwargs, "https_only": True})]
    )
    with TestClient(probe, base_url="https://testserver") as client:
        assert "secure" in client.get("/").headers["set-cookie"].lower()
