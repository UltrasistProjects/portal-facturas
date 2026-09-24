import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.constants import LoginResult
from app.core.database import SessionLocal
from app.models import AuditLog
from app.services import login_throttle
from tests.conftest import TEST_PASSWORDS, csrf, login

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def record_many(db, email, results, start=NOW, ip="10.0.0.1", step=timedelta(seconds=10)):
    for index, result in enumerate(results):
        login_throttle.record(db, email, ip, result, now=start + index * step)


def test_bloqueo_tras_cinco_fallos_aun_con_contrasena_correcta(client, monkeypatch):
    for _ in range(5):
        assert login(client, "pmo@poc.local", "incorrecta").status_code == 400
    import app.routers.auth as auth

    def never(*_args):
        raise AssertionError("verify_password no debe ejecutarse durante un bloqueo")

    monkeypatch.setattr(auth, "verify_password", never)
    response = login(client, "pmo@poc.local", TEST_PASSWORDS["pmo@poc.local"])
    assert response.status_code == 429
    assert "Demasiados intentos" in response.text
    assert int(response.headers["retry-after"]) > 0
    assert client.get("/", follow_redirects=False).status_code == 303  # sigue sin sesion


def test_correo_inexistente_recibe_la_misma_respuesta(client):
    for _ in range(5):
        login(client, "no-existe@ultrasist.com.mx", "incorrecta")
    missing = login(client, "no-existe@ultrasist.com.mx", "incorrecta")
    for _ in range(5):
        login(client, "proveedor2@poc.local", "incorrecta")
    existing = login(client, "proveedor2@poc.local", "incorrecta")
    assert missing.status_code == existing.status_code == 429
    strip = lambda text: text.replace(csrf(client), "")  # noqa: E731
    assert strip(missing.text) == strip(existing.text)


def test_backoff_exponencial():
    with SessionLocal() as db:
        record_many(db, "backoff@ultrasist.com.mx", [LoginResult.FAILURE] * 7)
        last = NOW + 6 * timedelta(seconds=10)
        assert login_throttle.lock_minutes(7) == 4
        assert not login_throttle.check(db, "backoff@ultrasist.com.mx", None, now=last + timedelta(minutes=3.9)).allowed
        assert login_throttle.check(db, "backoff@ultrasist.com.mx", None, now=last + timedelta(minutes=4.1)).allowed
        db.rollback()


def test_bloqueo_maximo_de_sesenta_minutos():
    assert login_throttle.lock_minutes(5) == 1
    assert login_throttle.lock_minutes(11) == 60
    assert login_throttle.lock_minutes(30) == 60


def test_limite_por_ip():
    with SessionLocal() as db:
        for index in range(20):
            login_throttle.record(db, f"u{index}@ultrasist.com.mx", "10.9.9.9", LoginResult.FAILURE, now=NOW)
        blocked = login_throttle.check(db, "otro@ultrasist.com.mx", "10.9.9.9", now=NOW + timedelta(minutes=1))
        assert not blocked.allowed
        assert login_throttle.check(db, "otro@ultrasist.com.mx", "10.9.9.9", now=NOW + timedelta(minutes=16)).allowed
        assert login_throttle.check(db, "otro@ultrasist.com.mx", "10.8.8.8", now=NOW + timedelta(minutes=1)).allowed
        db.rollback()


def test_exito_reinicia_contador():
    with SessionLocal() as db:
        email = "reinicio@ultrasist.com.mx"
        record_many(db, email, [LoginResult.FAILURE] * 3 + [LoginResult.SUCCESS])
        assert login_throttle.consecutive_failures(db, email, NOW + timedelta(minutes=1))[0] == 0
        db.rollback()


def test_intentos_bloqueados_no_extienden_el_bloqueo():
    with SessionLocal() as db:
        email = "throttled@ultrasist.com.mx"
        record_many(db, email, [LoginResult.FAILURE] * 5 + [LoginResult.THROTTLED] * 3)
        assert login_throttle.consecutive_failures(db, email, NOW + timedelta(minutes=2))[0] == 5
        db.rollback()


def test_bloqueo_auditado_y_registrado_sin_contrasena(client, caplog):
    with caplog.at_level(logging.WARNING, logger="app.services.login_throttle"):
        for _ in range(5):
            login(client, "proveedor1@poc.local", "Secreta#Incorrecta1")
    with SessionLocal() as db:
        locked = db.scalars(select(AuditLog).where(AuditLog.action == "LOGIN_LOCKED")).all()
    assert any(entry.new_value["email"] == "proveedor1@poc.local" for entry in locked)
    messages = [r for r in caplog.records if getattr(r, "event", None) == "login.locked"]
    assert messages
    assert all("Secreta#Incorrecta1" not in str(r.__dict__) for r in caplog.records)


@pytest.mark.parametrize("failures", [4])
def test_menos_de_cinco_fallos_no_bloquea(client, failures):
    for _ in range(failures):
        login(client, "admin@poc.local", "incorrecta")
    assert login(client, "admin@poc.local").status_code == 303
