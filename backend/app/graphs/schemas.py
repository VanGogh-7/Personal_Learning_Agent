from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

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
    citation_id: str | None = None
    title: str
    url: str
    excerpt: str
    provider: str = "deterministic"
    published_date: str | None = None
    published_at: str | None = None
    retrieved_at: str | None = None
    evidence_id: str | None = None
    source_type: Literal["web", "news", "academic", "page"] = "web"
    content: str | None = None
    authors: list[str] = Field(default_factory=list)
    doi: str | None = None
    arxiv_id: str | None = None

    @model_validator(mode="after")
    def default_citation_id(self) -> "WebSource":
        if self.citation_id is None:
            self.citation_id = self.source_id
        return self


class AgentDebugTimings(BaseModel):
    request_id: str
    timings_ms: dict[str, float]


class AgentChatRequest(BaseModel):
    message: str | None = None
    question: str | None = None
    selected_library_item_id: str | None = None
    selected_library_item_ids: list[str] = Field(default_factory=list)
    scope_type: AgentChatScope = "global"
    library_item_id: str | None = None
    library_item_ids: list[str] = Field(default_factory=list)
    top_k: int = 5
    session_id: str | None = None
    conversation_id: str | None = None
    include_long_term_memory: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize_product_request(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if normalized.get("question") is None and normalized.get("message") is not None:
            normalized["question"] = normalized["message"]
        if (
            normalized.get("library_item_id") is None
            and normalized.get("selected_library_item_id") is not None
        ):
            normalized["library_item_id"] = normalized["selected_library_item_id"]
        if not normalized.get("library_item_ids") and normalized.get(
            "selected_library_item_ids"
        ):
            normalized["library_item_ids"] = normalized["selected_library_item_ids"]

        if "scope_type" not in normalized:
            if normalized.get("library_item_ids"):
                normalized["scope_type"] = "multi_book"
            elif normalized.get("library_item_id"):
                normalized["scope_type"] = "single_book"
            else:
                normalized["scope_type"] = "global"
        return normalized

    @model_validator(mode="after")
    def validate_and_sync_product_fields(self) -> "AgentChatRequest":
        question = self.question or self.message
        if question is None or not question.strip():
            raise ValueError("message must not be empty")
        question = question.strip()
        self.question = question
        self.message = (
            self.message.strip() if self.message and self.message.strip() else question
        )

        if self.library_item_id is not None:
            self.library_item_id = self.library_item_id.strip() or None
        if self.selected_library_item_id is not None:
            self.selected_library_item_id = (
                self.selected_library_item_id.strip() or None
            )
        if self.library_item_id is None and self.selected_library_item_id is not None:
            self.library_item_id = self.selected_library_item_id
        if self.selected_library_item_id is None and self.library_item_id is not None:
            self.selected_library_item_id = self.library_item_id

        item_ids = self.library_item_ids or self.selected_library_item_ids
        normalized_ids = _normalize_item_ids(item_ids)
        self.library_item_ids = normalized_ids
        self.selected_library_item_ids = normalized_ids
        return self

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

    @field_validator("conversation_id")
    @classmethod
    def conversation_id_must_be_uuid_if_provided(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("conversation_id must not be empty")
        import uuid

        try:
            uuid.UUID(stripped)
        except ValueError as exc:
            raise ValueError("conversation_id must be a valid UUID") from exc
        return stripped

    @field_validator("library_item_id")
    @classmethod
    def library_item_id_must_not_be_blank_if_provided(
        cls, value: str | None
    ) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("selected_library_item_id")
    @classmethod
    def selected_library_item_id_must_not_be_blank_if_provided(
        cls, value: str | None
    ) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("library_item_ids")
    @classmethod
    def normalize_library_item_ids(cls, value: list[str]) -> list[str]:
        return _normalize_item_ids(value)

    @field_validator("selected_library_item_ids")
    @classmethod
    def normalize_selected_library_item_ids(cls, value: list[str]) -> list[str]:
        return _normalize_item_ids(value)


class AgentChatResponse(BaseModel):
    answer: str
    scope_type: AgentChatScope
    route: AgentRoute = "local_only"
    selected_library_items: list[SelectedLibraryItemRead] = Field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk]
    citations: list[RagCitation]
    local_citations: list[RagCitation] = Field(default_factory=list)
    web_sources: list[WebSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    local_summary: str | None = None
    web_summary: str | None = None
    total_retrieved: int
    session_id: str
    conversation_id: str
    memory_updates: list[dict[str, Any]] = Field(default_factory=list)
    memory: MemoryMetadata
    debug: AgentDebugTimings | None = None


def _normalize_item_ids(value: list[str]) -> list[str]:
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
