from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Auth System"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "change-me-in-production-use-32-chars-minimum"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5433/authdb"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Security
    bcrypt_rounds: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
