from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
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
    tavily_connect_timeout_seconds: float = 10.0
    tavily_read_timeout_seconds: float = 30.0

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_connect_timeout_seconds: float = 10.0
    llm_read_timeout_seconds: float = 60.0

    zhipu_api_key: str = ""
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    zhipu_embedding_model: str = "embedding-3"
    zhipu_embedding_dimension: int = 2048
    embedding_connect_timeout_seconds: float = 10.0
    embedding_read_timeout_seconds: float = 60.0

    agent_latency_logging_enabled: bool = True
    agent_debug_timings_in_response: bool = False
    agent_streaming_enabled: bool = True
    agent_activity_events_enabled: bool = True
    agent_stream_ui_flush_interval_ms: int = Field(default=50, ge=30, le=80)
    agent_stream_heartbeat_seconds: float = Field(default=15.0, ge=10.0, le=20.0)

    pla_real_provider_tests: bool = False
    pla_real_provider_benchmark_runs: int = Field(default=10, ge=1, le=100)
    pla_real_provider_warmup_runs: int = Field(default=1, ge=0, le=10)
    pla_sse_soak_runs: int = Field(default=20, ge=1, le=1000)
    pla_sse_target_url: str = "http://127.0.0.1:8081"
    pla_sse_proxy_target_url: str = ""
    pla_long_answer_max_tokens: int = Field(default=2000, ge=128, le=4096)
    pla_fault_injection_enabled: bool = False

    database_url: str = ""
    library_storage_dir: str = str(BACKEND_DIR / "storage" / "library")

    memory_checkpointer_backend: str = "postgres"
    memory_recent_turn_limit: int = 16
    memory_summary_trigger_turns: int = 24
    memory_retrieval_limit: int = 5
    memory_auto_write_enabled: bool = True
    memory_auto_write_min_importance: float = 0.75
    memory_auto_write_min_confidence: float = 0.80
    memory_auto_write_min_durability: float = 0.75
    memory_default_namespace: str = "default_user"
    memory_project_namespace: str = "project:personal-learning-agent"
    memory_postgres_pool_min_size: int = 1
    memory_postgres_pool_max_size: int = 10

    model_config = SettingsConfigDict(
        env_file=BACKEND_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def prohibit_production_fault_injection(self) -> "Settings":
        if (
            self.app_env.strip().lower() == "production"
            and self.pla_fault_injection_enabled
        ):
            raise ValueError(
                "PLA_FAULT_INJECTION_ENABLED cannot be enabled in production"
            )
        return self


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
