import json
import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.core.config import BASE_DIR, Settings
from scripts.create_env import create_env
from tests.conftest import ROOT

VALID_KEY = "k" * 32


def build(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_secret_key_ausente_impide_arrancar(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError, match="SECRET_KEY es obligatoria"):
        build()


def test_secret_key_placeholder_rechazada():
    with pytest.raises(ValidationError, match="change-me"):
        build(secret_key="change-me-use-a-long-random-value")


def test_secret_key_corta_rechazada():
    with pytest.raises(ValidationError, match="al menos 32"):
        build(secret_key="k" * 31)


def test_app_env_desconocido_rechazado():
    with pytest.raises(ValidationError, match="development"):
        build(secret_key=VALID_KEY, app_env="prod")


def test_valores_por_defecto_seguros(monkeypatch):
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("SESSION_HTTPS_ONLY", raising=False)
    assert build(secret_key=VALID_KEY).debug is False
    assert build(secret_key=VALID_KEY, app_env="development").session_https_only is False
    assert build(secret_key=VALID_KEY, app_env="production").session_https_only is True
    assert build(secret_key=VALID_KEY, app_env="production", session_https_only="false").session_https_only is False


def test_rutas_relativas_se_anclan_a_la_raiz(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = build(
        secret_key=VALID_KEY,
        storage_path="./storage",
        log_dir="logs",
        database_url="sqlite:///./data/invoice_portal.db",
    )
    assert BASE_DIR == ROOT
    assert settings.storage_path == ROOT / "storage"
    assert settings.log_dir == ROOT / "logs"
    assert settings.database_url == f"sqlite:///{(ROOT / 'data' / 'invoice_portal.db').as_posix()}"


def test_arranque_desde_otro_directorio_con_debug_activo(tmp_path):
    env = {**os.environ, "DEBUG": "true", "STORAGE_PATH": "./storage", "LOG_DIR": str(tmp_path / "logs")}
    code = (
        "import json; from app.main import app; from app.core.config import settings;"
        "static = next(r for r in app.routes if getattr(r, 'path', '') == '/static');"
        "print(json.dumps({'debug': app.debug, 'storage': str(settings.storage_path),"
        " 'static': str(static.app.directory)}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**env, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data["debug"] is False
    assert data["storage"] == str(ROOT / "storage")
    assert data["static"] == str(ROOT / "app" / "static")
    assert not (tmp_path / "data").exists()


def test_create_env_genera_clave_y_no_sobrescribe(tmp_path):
    (tmp_path / ".env.example").write_text("APP_ENV=development\nSECRET_KEY=\nDEBUG=false\n", encoding="utf-8")
    assert create_env(tmp_path) is True
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    key = next(line.split("=", 1)[1] for line in content.splitlines() if line.startswith("SECRET_KEY="))
    assert len(key) >= 64
    assert build(secret_key=key).secret_key == key
    assert create_env(tmp_path) is False
    assert (tmp_path / ".env").read_text(encoding="utf-8") == content


def test_create_env_respeta_env_existente(tmp_path):
    (tmp_path / ".env.example").write_text("SECRET_KEY=\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET_KEY=propia\n", encoding="utf-8")
    assert create_env(tmp_path) is False
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "SECRET_KEY=propia\n"
