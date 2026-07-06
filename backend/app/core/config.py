from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The real .env lives at the project root (one level above backend/), not inside backend/.
ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    app_name: str = "Personal Learning Agent"
    app_env: str = "development"
    app_version: str = "0.1.0"

    llm_provider: str = "deterministic"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    database_url: str = ""

    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_database_url() -> str:
    """Return DATABASE_URL, raising a clear error if it is not configured.

    Only database-specific code paths (SQLAlchemy engine creation,
    Alembic) should call this. General app startup and non-database
    endpoints (e.g. /health, /api/status) must not require DATABASE_URL.
    """
    database_url = get_settings().database_url
    if not database_url:
        raise ValueError("DATABASE_URL is required for database operations")
    return database_url
