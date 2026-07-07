from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class LearningEventCreate(BaseModel):
    event_type: str
    title: str
    description: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    library_item_id: str | None = None
    note_id: str | None = None
    session_id: str | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("event_type", "title")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator(
        "description",
        "source_type",
        "source_id",
        "library_item_id",
        "note_id",
        "session_id",
    )
    @classmethod
    def strip_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class LearningEventRead(BaseModel):
    id: str
    event_type: str
    title: str
    description: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    library_item_id: str | None = None
    library_item_title: str | None = None
    note_id: str | None = None
    note_title: str | None = None
    session_id: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: datetime


class LearningEventListResponse(BaseModel):
    events: list[LearningEventRead]
    total: int


class LearningEventListParams(BaseModel):
    event_type: str | None = None
    source_type: str | None = None
    library_item_id: str | None = None
    note_id: str | None = None
    session_id: str | None = None
    date: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
