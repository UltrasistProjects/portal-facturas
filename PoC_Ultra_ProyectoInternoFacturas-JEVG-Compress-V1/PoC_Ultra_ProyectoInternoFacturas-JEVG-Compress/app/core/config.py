from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Invoice Portal PoC"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me-use-a-long-random-value"
    database_url: str = "sqlite:///./data/invoice_portal.db"
    storage_path: Path = Path("./storage")
    max_upload_mb: int = 20
    session_https_only: bool = False
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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
