from functools import lru_cache
from pathlib import Path
from typing import Literal

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

    brave_api_key: str = ""

    mcp_enabled: bool = False
    mcp_real_tests: bool = False
    mcp_connect_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    mcp_tool_timeout_seconds: float = Field(default=30.0, gt=0, le=180)
    mcp_total_timeout_seconds: float = Field(default=45.0, gt=0, le=300)
    mcp_max_retries: int = Field(default=1, ge=0, le=2)
    mcp_retry_backoff_seconds: float = Field(default=0.2, ge=0, le=5)
    mcp_max_pending_calls_per_server: int = Field(default=20, ge=1, le=100)
    mcp_max_calls_per_request: int = Field(default=6, ge=1, le=12)
    mcp_max_evidence: int = Field(default=10, ge=1, le=30)
    mcp_max_fetch_urls: int = Field(default=3, ge=0, le=3)

    mcp_tavily_transport: str = "stdio"
    mcp_tavily_url: str = "https://mcp.tavily.com/mcp"
    mcp_tavily_command: str = "npx"
    mcp_tavily_args: list[str] = Field(
        default_factory=lambda: ["--no-install", "tavily-mcp"]
    )

    mcp_brave_transport: str = "stdio"
    mcp_brave_url: str = ""
    mcp_brave_command: str = "npx"
    mcp_brave_args: list[str] = Field(
        default_factory=lambda: [
            "--no-install",
            "@brave/brave-search-mcp-server",
            "--transport",
            "stdio",
        ]
    )

    mcp_fetch_transport: str = "stdio"
    mcp_fetch_url: str = ""
    mcp_fetch_command: str = "python"
    mcp_fetch_args: list[str] = Field(
        default_factory=lambda: ["-m", "app.mcp.servers.fetch"]
    )
    mcp_fetch_max_response_bytes: int = Field(
        default=1_000_000, ge=16_384, le=5_000_000
    )
    mcp_fetch_max_content_characters: int = Field(default=12_000, ge=1_000, le=50_000)
    mcp_fetch_max_redirects: int = Field(default=3, ge=0, le=5)
    mcp_fetch_read_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    mcp_fetch_total_timeout_seconds: float = Field(default=30.0, gt=0, le=180)

    mcp_academic_transport: str = "stdio"
    mcp_academic_url: str = ""
    mcp_academic_command: str = "python"
    mcp_academic_args: list[str] = Field(
        default_factory=lambda: ["-m", "app.mcp.servers.academic"]
    )
    academic_api_timeout_seconds: float = Field(default=20.0, gt=0, le=60)
    academic_api_min_interval_seconds: float = Field(default=0.2, ge=0, le=5)
    academic_api_user_agent: str = "PersonalLearningAgent/0.1"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_connect_timeout_seconds: float = 10.0
    llm_read_timeout_seconds: float = 60.0

    zhipu_api_key: str = ""
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    zhipu_embedding_model: str = "embedding-3"
    zhipu_embedding_dimension: int = 1024
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

    pdf_ocr_enabled: bool = True
    pdf_ocr_language: str = "eng"
    pdf_ocr_output_dir: str = str(BACKEND_DIR / "storage" / "ocr")
    pdf_layout_parser: Literal["pymupdf_rule"] = "pymupdf_rule"
    pdf_text_hybrid_retrieval_enabled: bool = True
    pdf_visual_retrieval_enabled: bool = False
    pdf_visual_model: str = "mock-colpali"
    pdf_visual_dimension: int = Field(default=128, ge=8, le=4096)
    pdf_hybrid_dense_weight: float = Field(default=1.0, ge=0, le=5)
    pdf_hybrid_keyword_weight: float = Field(default=1.0, ge=0, le=5)
    pdf_hybrid_visual_weight: float = Field(default=0.7, ge=0, le=5)
    local_exact_search_max_documents: int = Field(default=5, ge=1, le=100)
    hnsw_ef_search: int = Field(default=40, ge=1, le=1000)

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
