from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Amrutam Telemedicine API"
    app_env: str = "development"
    database_url: str = "sqlite:///./telemedicine.db"
    jwt_secret: str = "change-me-in-production-please"
    access_token_minutes: int = 30
    rate_limit_per_minute: int = 120
    redis_url: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()

