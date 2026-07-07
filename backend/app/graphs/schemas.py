from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.agents.router import AgentRoute
from app.rag.schemas import (
    MAX_TOP_K,
    MIN_TOP_K,
    MemoryMetadata,
    RagCitation,
    RetrievedChunk,
    SelectedLibraryItemRead,
)

AgentChatScope = Literal["global", "single_book", "multi_book"]


class WebSource(BaseModel):
    source_id: str
    title: str
    url: str
    excerpt: str
    provider: str = "deterministic"


class AgentChatRequest(BaseModel):
    question: str
    scope_type: AgentChatScope = "global"
    library_item_id: str | None = None
    library_item_ids: list[str] = Field(default_factory=list)
    top_k: int = 5
    session_id: str | None = None
    include_long_term_memory: bool = False

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be empty")
        return value

    @field_validator("top_k")
    @classmethod
    def top_k_must_be_in_range(cls, value: int) -> int:
        if not (MIN_TOP_K <= value <= MAX_TOP_K):
            raise ValueError(f"top_k must be between {MIN_TOP_K} and {MAX_TOP_K}")
        return value

    @field_validator("session_id")
    @classmethod
    def session_id_must_not_be_blank_if_provided(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("session_id must not be empty")
        return value.strip() if value is not None else value

    @field_validator("library_item_id")
    @classmethod
    def library_item_id_must_not_be_blank_if_provided(
        cls, value: str | None
    ) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("library_item_ids")
    @classmethod
    def normalize_library_item_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item_id in value:
            stripped = item_id.strip()
            if not stripped:
                raise ValueError("library_item_ids must not contain empty values")
            if stripped not in seen:
                normalized.append(stripped)
                seen.add(stripped)
        return normalized


class AgentChatResponse(BaseModel):
    answer: str
    scope_type: AgentChatScope
    route: AgentRoute = "local_only"
    selected_library_items: list[SelectedLibraryItemRead] = Field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk]
    citations: list[RagCitation]
    web_sources: list[WebSource] = Field(default_factory=list)
    local_summary: str | None = None
    web_summary: str | None = None
    total_retrieved: int
    session_id: str
    memory: MemoryMetadata
