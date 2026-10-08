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
# En produccion Keycloak debe usarse por HTTPS; las pruebas corren contra http://keycloak.test.
KEYCLOAK_TLS = "https://sso.ultrasist.example"


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
    production = {"app_env": "production", "keycloak_server_url": KEYCLOAK_TLS}
    assert build(secret_key=VALID_KEY, **production).session_https_only is True
    assert build(secret_key=VALID_KEY, **production, session_https_only="false").session_https_only is False


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


# --- Transporte de correo (HU-08) ---------------------------------------------------------------------------------

MAIL_VARIABLES = ("MAIL_BACKEND", "MAIL_FROM", "MAIL_OUTBOX_DIR", "SMTP_HOST", "SMTP_SECURITY")


@pytest.fixture()
def no_mail_env(monkeypatch):
    for name in MAIL_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def test_correo_por_omision_fuera_de_produccion(no_mail_env, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = build(secret_key=VALID_KEY, app_env="development")
    assert settings.mail_backend == "file"
    assert settings.mail_outbox_dir == ROOT / "outbox"
    assert settings.mail_from == "Portal de Proveedores ULTRASIST <no-reply@portal.local>"
    assert (settings.smtp_port, settings.smtp_security, settings.smtp_timeout) == (587, "starttls", 10)


def test_correo_por_omision_en_produccion_exige_smtp(no_mail_env):
    with pytest.raises(ValidationError, match="SMTP_HOST es obligatoria con MAIL_BACKEND=smtp"):
        build(secret_key=VALID_KEY, app_env="production", keycloak_server_url=KEYCLOAK_TLS)
    configured = build(
        secret_key=VALID_KEY,
        app_env="production",
        keycloak_server_url=KEYCLOAK_TLS,
        smtp_host="smtp.ultrasist.com.mx",
        mail_from="a@b.mx",
    )
    assert configured.mail_backend == "smtp"


def test_smtp_sin_remitente(no_mail_env):
    with pytest.raises(ValidationError, match="MAIL_FROM es obligatoria con MAIL_BACKEND=smtp"):
        build(secret_key=VALID_KEY, mail_backend="smtp", smtp_host="smtp.ultrasist.com.mx")


@pytest.mark.parametrize(("field", "value"), [("smtp_security", "tls"), ("mail_backend", "sendmail")])
def test_valores_de_correo_fuera_de_dominio(no_mail_env, field, value):
    with pytest.raises(ValidationError, match="starttls|smtp"):
        build(secret_key=VALID_KEY, **{field: value})


def test_mail_backend_vacio_equivale_a_sin_definir(no_mail_env):
    assert build(secret_key=VALID_KEY, app_env="test", mail_backend=" ").mail_backend == "file"


@pytest.mark.parametrize("timeout", [0, 121])
def test_tiempo_de_espera_smtp_fuera_de_rango(no_mail_env, timeout):
    with pytest.raises(ValidationError):
        build(secret_key=VALID_KEY, smtp_timeout=timeout)


@pytest.mark.parametrize(("value", "expected"), [(None, "local"), (" ", "local"), (" Database ", "database")])
def test_almacenamiento_por_omision_y_normalizado(monkeypatch, value, expected):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    values = {} if value is None else {"storage_backend": value}
    assert build(secret_key=VALID_KEY, **values).storage_backend == expected


def test_almacenamiento_fuera_de_dominio():
    with pytest.raises(ValidationError, match="local"):
        build(secret_key=VALID_KEY, storage_backend="s3")


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


# --- Keycloak (add-keycloak-authentication, D20) --------------------------------------------------------------------


@pytest.mark.parametrize("name", ["KEYCLOAK_CLIENT_SECRET", "KEYCLOAK_ADMIN_CLIENT_SECRET", "KEYCLOAK_SERVER_URL"])
def test_variable_de_keycloak_ausente_impide_arrancar(monkeypatch, name):
    monkeypatch.delenv(name)
    with pytest.raises(ValidationError, match=f"{name} es obligatoria"):
        build(secret_key=VALID_KEY)


def test_realm_obligatorio(monkeypatch):
    monkeypatch.delenv("KEYCLOAK_REALM")
    with pytest.raises(ValidationError, match="KEYCLOAK_REALM es obligatoria"):
        build(secret_key=VALID_KEY)


@pytest.mark.parametrize(
    ("value", "reason"),
    [("change-me-keycloak-admin-secret-value", "change-me"), ("s" * 31, "al menos 32")],
)
def test_secreto_de_keycloak_inseguro(value, reason):
    with pytest.raises(ValidationError, match=reason) as error:
        build(secret_key=VALID_KEY, keycloak_admin_client_secret=value)
    assert value not in str(error.value)  # SecretStr: el valor no aparece en el mensaje


def test_keycloak_sin_tls_en_produccion():
    with pytest.raises(ValidationError, match="en produccion Keycloak debe usarse por HTTPS"):
        build(secret_key=VALID_KEY, app_env="production", keycloak_server_url="http://keycloak:8080")


def test_url_de_keycloak_invalida():
    with pytest.raises(ValidationError, match="http:// o https://"):
        build(secret_key=VALID_KEY, keycloak_server_url="keycloak.ultrasist.example")


def test_urls_derivadas_de_keycloak():
    configured = build(
        secret_key=VALID_KEY, keycloak_server_url="https://sso.ultrasist.example:8443/", keycloak_realm="portal"
    )
    assert configured.keycloak_issuer == "https://sso.ultrasist.example:8443/realms/portal"
    assert configured.keycloak_metadata_url.endswith("/realms/portal/.well-known/openid-configuration")
    assert configured.keycloak_admin_url == "https://sso.ultrasist.example:8443/admin/realms/portal"
    assert configured.keycloak_origin == "https://sso.ultrasist.example:8443"
    assert configured.keycloak_timeout == 10


def test_env_example_sin_secretos_de_keycloak():
    values = parse_env((ROOT / ".env.example").read_text(encoding="utf-8").splitlines())
    for name in (
        "KEYCLOAK_CLIENT_SECRET",
        "KEYCLOAK_ADMIN_CLIENT_SECRET",
        "KC_BOOTSTRAP_ADMIN_PASSWORD",
        "DEMO_PASSWORD",
    ):
        assert values[name] == "", name


def test_create_env_genera_la_configuracion_de_keycloak(tmp_path):
    (tmp_path / ".env.example").write_text(EXAMPLE, encoding="utf-8")
    create_env(tmp_path)
    values = env_values(tmp_path)
    assert values["KEYCLOAK_SERVER_URL"] == "http://127.0.0.1:58080" and values["KEYCLOAK_REALM"] == "ultrasist-portal"
    secrets = [
        values[name]
        for name in ("KEYCLOAK_CLIENT_SECRET", "KEYCLOAK_ADMIN_CLIENT_SECRET", "KC_BOOTSTRAP_ADMIN_PASSWORD")
    ]
    assert all(len(secret) >= 32 for secret in secrets) and len(set(secrets)) == 3
    configured = build(
        secret_key=VALID_KEY,
        keycloak_server_url=values["KEYCLOAK_SERVER_URL"],
        keycloak_client_secret=values["KEYCLOAK_CLIENT_SECRET"],
        keycloak_admin_client_secret=values["KEYCLOAK_ADMIN_CLIENT_SECRET"],
    )
    assert configured.keycloak_client_secret.get_secret_value() == values["KEYCLOAK_CLIENT_SECRET"]
    demo = values["DEMO_PASSWORD"]
    assert len(demo) == 20 and any(c.isalpha() for c in demo) and any(c.isdigit() for c in demo)
    assert any(not c.isalnum() for c in demo)


def test_create_env_completa_keycloak_sin_tocar_valores_presentes(tmp_path):
    (tmp_path / ".env.example").write_text(EXAMPLE, encoding="utf-8")
    (tmp_path / ".env").write_text(
        "KEYCLOAK_PORT=59000\nKEYCLOAK_CLIENT_SECRET=propio-" + "x" * 40 + "\n", encoding="utf-8"
    )
    create_env(tmp_path)
    values = env_values(tmp_path)
    assert values["KEYCLOAK_CLIENT_SECRET"] == "propio-" + "x" * 40
    assert values["KEYCLOAK_SERVER_URL"] == "http://127.0.0.1:59000"
    assert values["KEYCLOAK_ADMIN_CLIENT_SECRET"] and values["DEMO_PASSWORD"]
