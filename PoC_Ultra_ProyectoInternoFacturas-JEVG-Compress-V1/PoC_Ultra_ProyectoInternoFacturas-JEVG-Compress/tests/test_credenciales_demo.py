import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.core.database import SessionLocal
from app.core.demo import DEMO_ACCOUNTS
from app.core.startup import startup_problems
from scripts.seed_db import seed_passwords


def test_login_en_desarrollo_muestra_acceso_rapido(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    page = client.get("/login").text
    assert 'data-demo="admin@poc.local|Admin#Demo2026"' in page
    assert "proveedor2@poc.local" not in page


@pytest.mark.parametrize("app_env", ["test", "production"])
def test_login_fuera_de_desarrollo_no_expone_credenciales(client, monkeypatch, app_env):
    monkeypatch.setattr(settings, "app_env", app_env)
    page = client.get("/login").text
    assert "data-demo" not in page
    for account in DEMO_ACCOUNTS:
        assert account.password not in page
    assert "Admin123!" not in page


def test_seed_fuera_de_desarrollo_genera_contrasenas_aleatorias(monkeypatch, capsys):
    monkeypatch.setattr(settings, "app_env", "test")
    first = seed_passwords()
    output = capsys.readouterr().out
    second = seed_passwords()
    demo = {account.password for account in DEMO_ACCOUNTS}
    assert set(first) == {account.email for account in DEMO_ACCOUNTS}
    assert not demo & set(first.values())
    assert first != second
    for password in first.values():
        assert output.count(password) == 1


def test_seed_en_desarrollo_usa_contrasenas_documentadas(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    assert seed_passwords() == {account.email: account.password for account in DEMO_ACCOUNTS}


def test_arranque_en_produccion_detecta_configuracion_insegura():
    production = Settings(_env_file=None, secret_key="k" * 32, app_env="production", session_https_only=False)
    with SessionLocal() as db:
        problems = startup_problems(production, db)
    assert any("SESSION_HTTPS_ONLY" in p for p in problems)
    assert any("admin@poc.local" in p for p in problems)


def test_arranque_en_produccion_con_cookie_segura_solo_reporta_cuentas_demo():
    production = Settings(_env_file=None, secret_key="k" * 32, app_env="production", session_https_only=True)
    with SessionLocal() as db:
        problems = startup_problems(production, db)
    assert len(problems) == 1 and "Cuentas demo activas" in problems[0]


def test_arranque_en_produccion_aborta(monkeypatch):
    from app.main import app

    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(RuntimeError, match="Arranque abortado"):
        with TestClient(app):
            pass


def test_desarrollo_no_aplica_verificaciones_de_produccion(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    with SessionLocal() as db:
        assert startup_problems(settings, db) == []
