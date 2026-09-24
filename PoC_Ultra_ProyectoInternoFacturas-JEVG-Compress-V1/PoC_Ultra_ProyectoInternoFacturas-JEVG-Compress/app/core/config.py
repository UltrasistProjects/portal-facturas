from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz del proyecto: todas las rutas relativas de la configuracion se resuelven contra ella, no contra el CWD.
BASE_DIR = Path(__file__).resolve().parents[2]

MIN_SECRET_KEY_LENGTH = 32
SECRET_KEY_HINT = 'Genere una con: python -c "import secrets; print(secrets.token_urlsafe(64))"'


class Settings(BaseSettings):
    app_name: str = "Invoice Portal PoC"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    secret_key: str = Field(default="", validate_default=True)
    database_url: str = "sqlite:///./data/invoice_portal.db"
    storage_path: Path = Path("storage")
    log_dir: Path = Path("logs")
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

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

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

    @field_validator("storage_path", "log_dir")
    @classmethod
    def anchored_path(cls, value: Path) -> Path:
        return (value if value.is_absolute() else BASE_DIR / value).resolve()

    @field_validator("database_url")
    @classmethod
    def anchored_sqlite_url(cls, value: str) -> str:
        prefix = "sqlite:///"
        if not value.startswith(prefix):
            return value
        path = value.removeprefix(prefix)
        if not path or path == ":memory:" or Path(path).is_absolute():
            return value
        return f"{prefix}{(BASE_DIR / path).resolve().as_posix()}"

    @model_validator(mode="after")
    def derived_defaults(self):
        if self.session_https_only is None:
            self.session_https_only = self.app_env != "development"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
