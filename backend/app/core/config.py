from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ACP Enterprise"
    app_version: str = "0.1.0"
    environment: str = "development"
    business_timezone: str = "America/New_York"

    database_url: str = (
        "postgresql+asyncpg://acp_enterprise:"
        "acp_development_password@postgres:5432/acp_enterprise"
    )
    redis_url: str = "redis://redis:6379/0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
