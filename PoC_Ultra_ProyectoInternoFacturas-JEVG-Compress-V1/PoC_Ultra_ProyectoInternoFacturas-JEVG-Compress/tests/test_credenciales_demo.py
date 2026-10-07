"""Credenciales demo (spec autenticacion-sesiones, add-keycloak-authentication): viven solo en el realm de Keycloak de
desarrollo; ni el codigo, ni el README, ni las plantillas contienen contrasenas demo."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings, settings
from app.core.database import SessionLocal
from app.core.demo import DEMO_ACCOUNTS
from app.core.startup import startup_problems
from scripts.seed_db import seed_passwords
from tests.conftest import ROOT, login

# Contrasenas demo que publicaba la version anterior: no deben quedar en el repositorio.
FORMER_DEMO_PASSWORDS = ("Admin#Demo2026", "Pmo#Demo2026", "Proveedor#Demo2026", "Admin123!")


@pytest.mark.parametrize("app_env", ["development", "production"])
def test_sin_acceso_rapido_en_las_paginas(client, monkeypatch, app_env):
    monkeypatch.setattr(settings, "app_env", app_env)
    assert "data-demo" not in client.get("/login", follow_redirects=False).text
    login(client)
    assert "data-demo" not in client.get("/").text


def test_repositorio_sin_contrasenas_demo():
    sources = [
        ROOT / "README.md",
        *(path for folder in ("app", "scripts", "infra") for path in (ROOT / folder).rglob("*")),
    ]
    for path in sources:
        if path.is_file() and path.suffix in {".py", ".html", ".js", ".json", ".md", ".txt", ".yaml"}:
            text = path.read_text(encoding="utf-8")
            assert not any(password in text for password in FORMER_DEMO_PASSWORDS), path
            assert "data-demo" not in text, path


def test_seed_fuera_de_desarrollo_genera_contrasenas_temporales(monkeypatch, capsys):
    monkeypatch.setattr(settings, "app_env", "test")
    first, temporary = seed_passwords()
    output = capsys.readouterr().out
    second, _ = seed_passwords()
    assert temporary is True  # Keycloak pedira cambiarlas en el primer acceso
    assert set(first) == {account.email for account in DEMO_ACCOUNTS}
    assert first != second and len(set(first.values())) == len(first)
    for password in first.values():
        assert output.count(password) == 1


def test_seed_en_desarrollo_usa_demo_password(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "demo_password", SecretStr("Demo#Prueba2026x"))
    passwords, temporary = seed_passwords()
    assert passwords == {account.email: "Demo#Prueba2026x" for account in DEMO_ACCOUNTS} and temporary is False


def test_seed_en_desarrollo_sin_demo_password(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "demo_password", SecretStr(""))
    with pytest.raises(SystemExit, match="DEMO_PASSWORD es obligatoria"):
        seed_passwords()


def test_cuentas_demo_en_keycloak(keycloak):
    """El seed de la sesion crea las cuentas demo en Keycloak, con su rol y sin accion requerida."""
    for account in DEMO_ACCOUNTS:
        created = keycloak.account(account.email)
        assert created.roles == {account.role.value} and created.required_actions == [] and created.enabled


def production_settings(**values) -> Settings:
    base = {
        "secret_key": "k" * 32,
        "app_env": "production",
        "keycloak_server_url": "https://sso.ultrasist.example",
        # Correo de produccion valido (HU-08): sin el, el transporte file de las pruebas seria otro problema.
        "mail_backend": "smtp",
        "smtp_host": "smtp.ultrasist.com.mx",
        "mail_from": "portal@ultrasist.com.mx",
    }
    return Settings(_env_file=None, **{**base, **values})


def test_arranque_en_produccion_detecta_configuracion_insegura():
    production = production_settings(session_https_only=False)
    with SessionLocal() as db:
        problems = startup_problems(production, db)
    assert any("SESSION_HTTPS_ONLY" in p for p in problems)
    assert any("admin@poc.local" in p for p in problems)


def test_arranque_en_produccion_con_cookie_segura_solo_reporta_cuentas_demo():
    production = production_settings(session_https_only=True)
    with SessionLocal() as db:
        problems = startup_problems(production, db)
    assert len(problems) == 1 and "Cuentas demo activas" in problems[0]


def test_arranque_en_produccion_con_transporte_de_archivo():
    production = production_settings(session_https_only=True, mail_backend="file")
    with SessionLocal() as db:
        problems = startup_problems(production, db)
    assert any("MAIL_BACKEND=file" in p and "SMTP" in p for p in problems)


def test_arranque_en_produccion_con_smtp_sin_cifrar():
    production = production_settings(session_https_only=True, smtp_security="none")
    with SessionLocal() as db:
        problems = startup_problems(production, db)
    assert any("SMTP_SECURITY=none" in p for p in problems)
    assert not any("MAIL_BACKEND" in p for p in problems)


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
