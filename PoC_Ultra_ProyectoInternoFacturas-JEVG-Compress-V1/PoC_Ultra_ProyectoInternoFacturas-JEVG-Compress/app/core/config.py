from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz del proyecto: todas las rutas relativas de la configuracion se resuelven contra ella, no contra el CWD.
BASE_DIR = Path(__file__).resolve().parents[2]

MIN_SECRET_KEY_LENGTH = 32
SECRET_KEY_HINT = 'Genere una con: python -c "import secrets; print(secrets.token_urlsafe(64))"'
DATABASE_URL_PREFIX = "postgresql+psycopg://"
DATABASE_URL_HINT = "Ejecute python scripts/create_env.py para completar el .env."
# Keycloak, proveedor de identidad (add-keycloak-authentication, D20): los secretos de los clientes siguen la regla
# de SECRET_KEY (obligatorios, sin valor por defecto y sin el prefijo de ejemplo).
MIN_KEYCLOAK_SECRET_LENGTH = 32
KEYCLOAK_HINT = DATABASE_URL_HINT
# Remitente del transporte de archivo: nunca sale del equipo, no necesita un dominio real.
DEFAULT_FILE_MAIL_FROM = "Portal de Proveedores ULTRASIST <no-reply@portal.local>"


class Settings(BaseSettings):
    app_name: str = "Invoice Portal PoC"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    secret_key: str = Field(default="", validate_default=True)
    database_url: str = Field(default="", validate_default=True)
    storage_path: Path = Path("storage")
    log_dir: Path = Path("logs")
    backup_dir: Path = Path("backups")
    max_upload_mb: int = 20
    # None significa "derivar de app_env": Secure fuera de development.
    session_https_only: bool | None = None
    business_timezone: str = "America/Mexico_City"
    backup_retention: int = Field(default=14, ge=1)
    ai_enabled: bool = False
    document_ai_provider: str = "mock"
    azure_document_intelligence_endpoint: str = ""
    azure_document_intelligence_key: str = ""
    azure_content_understanding_endpoint: str = ""
    azure_content_understanding_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = ""
    # Correo (HU-08). None significa "derivar de app_env": smtp en produccion y file (no envia) en los demas.
    mail_backend: Literal["smtp", "file"] | None = None
    mail_from: str = ""
    mail_outbox_dir: Path = Path("outbox")
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_timeout: int = Field(default=10, ge=1, le=120)
    # Keycloak (D20). Los secretos no tienen valor por defecto: sin ellos la aplicacion no arranca.
    keycloak_server_url: str = Field(default="", validate_default=True)
    keycloak_realm: str = Field(default="", validate_default=True)
    keycloak_client_id: str = Field(default="portal-facturas-web", validate_default=True)
    keycloak_client_secret: SecretStr = Field(default=SecretStr(""), validate_default=True)
    keycloak_admin_client_id: str = Field(default="portal-facturas-admin", validate_default=True)
    keycloak_admin_client_secret: SecretStr = Field(default=SecretStr(""), validate_default=True)
    keycloak_timeout: int = Field(default=10, ge=1, le=60)
    # Solo la usa el seed en development: contrasena de las cuentas demo en Keycloak.
    demo_password: SecretStr = SecretStr("")

    # hide_input_in_errors: un error de validacion no repite el valor recibido (secretos de Keycloak, la contrasena
    # dentro de DATABASE_URL); los mensajes propios ya nombran la variable y el motivo.
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    @field_validator("debug", "session_https_only", "ai_enabled", mode="before")
    @classmethod
    def portable_boolean(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "development"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "production", ""}:
                return False
        return value

    @field_validator("app_env", mode="before")
    @classmethod
    def normalized_env(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("secret_key")
    @classmethod
    def strong_secret_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"SECRET_KEY es obligatoria. {SECRET_KEY_HINT}")
        if value.lower().startswith("change-me"):
            raise ValueError(f"SECRET_KEY contiene el valor de ejemplo inseguro 'change-me...'. {SECRET_KEY_HINT}")
        if len(value) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(f"SECRET_KEY debe tener al menos {MIN_SECRET_KEY_LENGTH} caracteres. {SECRET_KEY_HINT}")
        return value

    @field_validator("business_timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"BUSINESS_TIMEZONE desconocida: {value!r} (ejemplo: America/Mexico_City)") from exc
        return value

    @field_validator("mail_backend", "smtp_security", mode="before")
    @classmethod
    def normalized_choice(cls, value):
        # Vacio en .env equivale a "sin definir" para MAIL_BACKEND.
        if isinstance(value, str):
            value = value.strip().lower()
            return value or None
        return value

    @field_validator("mail_from", "smtp_host", "smtp_username")
    @classmethod
    def stripped_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("storage_path", "log_dir", "backup_dir", "mail_outbox_dir")
    @classmethod
    def anchored_path(cls, value: Path) -> Path:
        return (value if value.is_absolute() else BASE_DIR / value).resolve()

    @field_validator("database_url")
    @classmethod
    def postgresql_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"DATABASE_URL es obligatoria. {DATABASE_URL_HINT}")
        if value.startswith("sqlite"):
            raise ValueError(
                "SQLite ya no es compatible: DATABASE_URL debe apuntar a PostgreSQL. "
                "python scripts/create_env.py actualiza el .env y reemplaza la URL de SQLite."
            )
        if not value.startswith(DATABASE_URL_PREFIX):
            raise ValueError(f"DATABASE_URL debe usar el esquema {DATABASE_URL_PREFIX}. {DATABASE_URL_HINT}")
        return value

    @field_validator("keycloak_server_url")
    @classmethod
    def keycloak_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value:
            raise ValueError(f"KEYCLOAK_SERVER_URL es obligatoria. {KEYCLOAK_HINT}")
        if not value.startswith(("http://", "https://")):
            raise ValueError("KEYCLOAK_SERVER_URL debe comenzar con http:// o https://.")
        return value

    @field_validator("keycloak_realm", "keycloak_client_id", "keycloak_admin_client_id")
    @classmethod
    def keycloak_name(cls, value: str, info: ValidationInfo) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"{info.field_name.upper()} es obligatoria. {KEYCLOAK_HINT}")
        return value

    @field_validator("keycloak_client_secret", "keycloak_admin_client_secret")
    @classmethod
    def keycloak_secret(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        name = info.field_name.upper()
        secret = value.get_secret_value().strip()
        if not secret:
            raise ValueError(f"{name} es obligatoria. {KEYCLOAK_HINT}")
        if secret.lower().startswith("change-me"):
            raise ValueError(f"{name} contiene el valor de ejemplo inseguro 'change-me...'. {KEYCLOAK_HINT}")
        if len(secret) < MIN_KEYCLOAK_SECRET_LENGTH:
            raise ValueError(f"{name} debe tener al menos {MIN_KEYCLOAK_SECRET_LENGTH} caracteres.")
        return SecretStr(secret)

    @property
    def keycloak_issuer(self) -> str:
        """Emisor de los tokens del realm; tambien es la base del discovery y del token endpoint."""
        return f"{self.keycloak_server_url}/realms/{quote(self.keycloak_realm, safe='')}"

    @property
    def keycloak_metadata_url(self) -> str:
        return f"{self.keycloak_issuer}/.well-known/openid-configuration"

    @property
    def keycloak_admin_url(self) -> str:
        return f"{self.keycloak_server_url}/admin/realms/{quote(self.keycloak_realm, safe='')}"

    @property
    def keycloak_origin(self) -> str:
        """Esquema, host y puerto de Keycloak: el destino que la CSP admite en form-action (logout)."""
        parts = urlsplit(self.keycloak_server_url)
        return f"{parts.scheme}://{parts.netloc}"

    @model_validator(mode="after")
    def derived_defaults(self):
        if self.app_env == "production" and not self.keycloak_server_url.startswith("https://"):
            raise ValueError("KEYCLOAK_SERVER_URL: en produccion Keycloak debe usarse por HTTPS (https://).")
        if self.session_https_only is None:
            self.session_https_only = self.app_env != "development"
        if self.mail_backend is None:
            self.mail_backend = "smtp" if self.app_env == "production" else "file"
        if self.mail_backend == "smtp":
            if not self.smtp_host:
                raise ValueError("SMTP_HOST es obligatoria con MAIL_BACKEND=smtp.")
            if not self.mail_from:
                raise ValueError("MAIL_FROM es obligatoria con MAIL_BACKEND=smtp.")
        elif not self.mail_from:
            self.mail_from = DEFAULT_FILE_MAIL_FROM
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
