import json
import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.core.config import BASE_DIR, Settings
from scripts.create_env import SQLITE_WARNING, create_env, parse_env
from tests.conftest import ROOT

VALID_KEY = "k" * 32
POSTGRES_URL = "postgresql+psycopg://portal:secreto@127.0.0.1:55432/portal"


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


def test_url_de_sqlite_rechazada_con_indicaciones():
    with pytest.raises(ValidationError, match="SQLite ya no es compatible") as error:
        build(secret_key=VALID_KEY, database_url="sqlite:///./data/invoice_portal.db")
    assert "python scripts/create_env.py" in str(error.value)


def test_url_ausente_rechazada(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="DATABASE_URL es obligatoria"):
        build(secret_key=VALID_KEY)


def test_url_de_otro_driver_rechazada():
    with pytest.raises(ValidationError, match="postgresql\\+psycopg://"):
        build(secret_key=VALID_KEY, database_url="postgresql://portal:secreto@127.0.0.1:55432/portal")
    assert build(secret_key=VALID_KEY, database_url=POSTGRES_URL).database_url == POSTGRES_URL


def test_rutas_relativas_se_anclan_a_la_raiz(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = build(secret_key=VALID_KEY, storage_path="./storage", log_dir="logs", backup_dir="backups")
    assert BASE_DIR == ROOT
    assert settings.storage_path == ROOT / "storage"
    assert settings.log_dir == ROOT / "logs"
    assert settings.backup_dir == ROOT / "backups"


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


EXAMPLE = "APP_ENV=development\nSECRET_KEY=\nPOSTGRES_USER=portal\nPOSTGRES_DB=portal\nPOSTGRES_PORT=55432\n"
EXAMPLE += "POSTGRES_PASSWORD=\nDATABASE_URL=\nDEBUG=false\n"


def env_values(root) -> dict[str, str]:
    return parse_env((root / ".env").read_text(encoding="utf-8").splitlines())


def test_create_env_genera_claves_y_url_de_postgresql(tmp_path):
    (tmp_path / ".env.example").write_text(EXAMPLE, encoding="utf-8")
    assert create_env(tmp_path)
    values = env_values(tmp_path)
    assert len(values["SECRET_KEY"]) >= 64
    assert build(secret_key=values["SECRET_KEY"]).secret_key == values["SECRET_KEY"]
    assert len(values["POSTGRES_PASSWORD"]) >= 32
    assert values["DATABASE_URL"] == f"postgresql+psycopg://portal:{values['POSTGRES_PASSWORD']}@127.0.0.1:55432/portal"
    assert build(secret_key=VALID_KEY, database_url=values["DATABASE_URL"])
    assert values["APP_ENV"] == "development" and values["DEBUG"] == "false"


def test_create_env_usa_el_puerto_configurado(tmp_path):
    (tmp_path / ".env.example").write_text(
        EXAMPLE.replace("POSTGRES_PORT=55432", "POSTGRES_PORT=56000"), encoding="utf-8"
    )
    create_env(tmp_path)
    assert "@127.0.0.1:56000/portal" in env_values(tmp_path)["DATABASE_URL"]


def test_create_env_completa_un_env_existente_y_reemplaza_sqlite(tmp_path):
    (tmp_path / ".env.example").write_text(EXAMPLE, encoding="utf-8")
    original = "# propio\nSECRET_KEY=propia\nAPP_ENV=production\nDATABASE_URL=sqlite:///./data/invoice_portal.db\n"
    (tmp_path / ".env").write_text(original, encoding="utf-8")
    changes = create_env(tmp_path)
    assert SQLITE_WARNING in changes
    values = env_values(tmp_path)
    assert values["SECRET_KEY"] == "propia" and values["APP_ENV"] == "production"
    assert values["POSTGRES_USER"] == "portal" and values["POSTGRES_PORT"] == "55432"
    assert values["DATABASE_URL"] == f"postgresql+psycopg://portal:{values['POSTGRES_PASSWORD']}@127.0.0.1:55432/portal"
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert content.startswith("# propio\nSECRET_KEY=propia\nAPP_ENV=production\nDATABASE_URL=postgresql+psycopg://")
    assert "sqlite" not in content


def test_create_env_respeta_valores_presentes(tmp_path):
    (tmp_path / ".env.example").write_text(EXAMPLE, encoding="utf-8")
    (tmp_path / ".env").write_text(
        "SECRET_KEY=propia\nPOSTGRES_PASSWORD=clave\nPOSTGRES_PORT=56000\n", encoding="utf-8"
    )
    create_env(tmp_path)
    values = env_values(tmp_path)
    assert values["POSTGRES_PASSWORD"] == "clave"
    assert values["DATABASE_URL"] == "postgresql+psycopg://portal:clave@127.0.0.1:56000/portal"


def test_create_env_no_cambia_un_env_completo(tmp_path):
    (tmp_path / ".env.example").write_text(EXAMPLE, encoding="utf-8")
    create_env(tmp_path)
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert create_env(tmp_path) == []
    assert (tmp_path / ".env").read_text(encoding="utf-8") == content


def test_create_env_por_consola_avisa_del_reemplazo_de_sqlite(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "create_env.py").write_text(
        (ROOT / "scripts" / "create_env.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / ".env.example").write_text(EXAMPLE, encoding="utf-8")
    (tmp_path / ".env").write_text("DATABASE_URL=sqlite:///./data/invoice_portal.db\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(tmp_path / "scripts" / "create_env.py")], capture_output=True, text=True, check=True
    )
    assert SQLITE_WARNING in result.stdout
