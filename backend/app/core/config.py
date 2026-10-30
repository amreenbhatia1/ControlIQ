from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRETS = {"dev-only-change-me", "change-me-to-a-long-random-value"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ControlIQ"
    organization_name: str = "Alpha Beta Bank"
    environment: str = Field(default="development", description="development | test | production")

    database_url: str = "postgresql+psycopg://controliq:controliq@localhost:5432/controliq"
    # Dedicated database for the pytest suite; it is wiped on every test run.
    test_database_url: str | None = None

    # Secret used to derive session token hashes. Must be overridden outside local development.
    secret_key: str = "dev-only-change-me"
    session_cookie_name: str = "controliq_session"
    session_ttl_hours: int = 12
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    cors_origins: str = "http://localhost:3000"

    evidence_storage_dir: str = "storage/evidence"
    evidence_max_bytes: int = 2 * 1024 * 1024

    demo_password: str = "ControlIQ-Demo-2026!"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: float = 20.0

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> "Settings":
        if self.environment == "production":
            if self.secret_key in PLACEHOLDER_SECRETS or len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be a random value of at least 32 characters in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production (serve over HTTPS)")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
