from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.memory.long_term import MAX_IMPORTANCE, MIN_IMPORTANCE
from app.memory.models import MemoryStatus, MemorySubtype, MemoryType, SUBTYPES_BY_TYPE

DEFAULT_IMPORTANCE = 3


class LongTermMemoryCreateRequest(BaseModel):
    memory_type: str
    content: str
    importance: int = DEFAULT_IMPORTANCE
    source: str | None = "manual"
    tags: list[str] | None = None
    namespace: str | None = None
    subject_id: str | None = None
    memory_subtype: MemorySubtype | None = None
    structured_data: dict | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_typed_memory(self) -> "LongTermMemoryCreateRequest":
        if self.memory_subtype is not None:
            try:
                memory_type = MemoryType(self.memory_type)
            except ValueError as exc:
                raise ValueError(
                    "typed memories require semantic, episodic, or procedural"
                ) from exc
            if self.memory_subtype not in SUBTYPES_BY_TYPE[memory_type]:
                raise ValueError("memory_subtype is not valid for memory_type")
        return self

    @field_validator("memory_type")
    @classmethod
    def memory_type_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("memory_type must not be empty")
        return value.strip()

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be empty")
        return value

    @field_validator("importance")
    @classmethod
    def importance_must_be_in_range(cls, value: int) -> int:
        if not (MIN_IMPORTANCE <= value <= MAX_IMPORTANCE):
            raise ValueError(
                f"importance must be between {MIN_IMPORTANCE} and {MAX_IMPORTANCE}"
            )
        return value


class LongTermMemoryResponse(BaseModel):
    id: str
    memory_type: str
    content: str
    importance: int
    source: str | None = None
    tags: list[str] | None = None
    namespace: str = "default_user"
    subject_id: str | None = None
    memory_subtype: str | None = None
    structured_data: dict | None = None
    confidence: float = 1.0
    status: str = "active"
    source_type: str | None = None
    supersedes_id: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    last_accessed_at: datetime | None = None
    access_count: int = 0
    created_at: datetime
    updated_at: datetime


class LongTermMemoryListResponse(BaseModel):
    memories: list[LongTermMemoryResponse]
    total: int


class LongTermMemoryUpdateRequest(BaseModel):
    content: str | None = None
    importance: int | None = Field(default=None, ge=MIN_IMPORTANCE, le=MAX_IMPORTANCE)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    structured_data: dict | None = None
    status: MemoryStatus | None = None
    valid_until: datetime | None = None

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank_if_provided(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("content must not be empty")
        return value.strip() if value is not None else None
