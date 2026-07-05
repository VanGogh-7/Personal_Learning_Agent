from datetime import datetime

from pydantic import BaseModel, field_validator

from app.memory.long_term import MAX_IMPORTANCE, MIN_IMPORTANCE

DEFAULT_IMPORTANCE = 3


class LongTermMemoryCreateRequest(BaseModel):
    memory_type: str
    content: str
    importance: int = DEFAULT_IMPORTANCE
    source: str | None = "manual"
    tags: list[str] | None = None

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
            raise ValueError(f"importance must be between {MIN_IMPORTANCE} and {MAX_IMPORTANCE}")
        return value


class LongTermMemoryResponse(BaseModel):
    id: str
    memory_type: str
    content: str
    importance: int
    source: str | None = None
    tags: list[str] | None = None
    created_at: datetime
    updated_at: datetime


class LongTermMemoryListResponse(BaseModel):
    memories: list[LongTermMemoryResponse]
    total: int
