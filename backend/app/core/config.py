from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
BACKEND_ENV_FILE = BACKEND_DIR / ".env"

# Backward-compatible alias for older tests/imports. The local development
# environment file now lives in backend/.env.
ROOT_ENV_FILE = BACKEND_ENV_FILE


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    app_name: str = "Personal Learning Agent"
    app_env: str = "development"
    app_version: str = "0.1.0"

    llm_provider: str = "deterministic"
    embedding_provider: str = "mock"
    web_research_provider: str = "none"

    tavily_api_key: str = ""
    tavily_base_url: str = "https://api.tavily.com/search"
    tavily_search_depth: str = "basic"
    tavily_max_results: int = 5

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    zhipu_api_key: str = ""
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    zhipu_embedding_model: str = "embedding-3"
    zhipu_embedding_dimension: int = 2048

    database_url: str = ""
    library_storage_dir: str = str(BACKEND_DIR / "storage" / "library")

    model_config = SettingsConfigDict(
        env_file=BACKEND_ENV_FILE,
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
