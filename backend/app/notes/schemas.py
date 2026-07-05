from datetime import datetime

from pydantic import BaseModel, Field, field_validator

DEFAULT_NOTE_STATUS = "active"


class NoteCreate(BaseModel):
    title: str
    content_latex: str
    description: str | None = None
    library_item_id: str | None = None
    source_session_id: str | None = None
    topic_tags: list[str] | None = None
    status: str = DEFAULT_NOTE_STATUS

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be empty")
        return value.strip()

    @field_validator("status")
    @classmethod
    def status_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("status must not be empty")
        return value.strip()

    @field_validator("description", "library_item_id", "source_session_id")
    @classmethod
    def strip_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("topic_tags")
    @classmethod
    def normalize_topic_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        tags = [tag.strip() for tag in value if tag.strip()]
        return tags or None


class NoteUpdate(BaseModel):
    title: str | None = None
    content_latex: str | None = None
    description: str | None = None
    library_item_id: str | None = None
    source_session_id: str | None = None
    topic_tags: list[str] | None = None
    status: str | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank_if_provided(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("title must not be empty")
        return value.strip() if value is not None else value

    @field_validator("status")
    @classmethod
    def status_must_not_be_blank_if_provided(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("status must not be empty")
        return value.strip() if value is not None else value

    @field_validator("description", "library_item_id", "source_session_id")
    @classmethod
    def strip_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("topic_tags")
    @classmethod
    def normalize_topic_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        tags = [tag.strip() for tag in value if tag.strip()]
        return tags or None


class NoteRead(BaseModel):
    id: str
    title: str
    content_latex: str
    description: str | None = None
    library_item_id: str | None = None
    source_session_id: str | None = None
    topic_tags: list[str] | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class NoteListResponse(BaseModel):
    notes: list[NoteRead]
    total: int


class ChatNoteChunkInput(BaseModel):
    id: str | None = None
    chunk_id: str | None = None
    document_id: str | None = None
    document_title: str | None = None
    chunk_index: int | None = None
    content: str
    score: float | None = None


class ChatNoteLibraryItemInput(BaseModel):
    id: str
    title: str
    author: str | None = None
    file_type: str | None = None
    status: str | None = None

    @field_validator("id", "title")
    @classmethod
    def required_strings_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("library item id and title must not be empty")
        return value.strip()

    @field_validator("author", "file_type", "status")
    @classmethod
    def strip_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ChatNoteDraftRequest(BaseModel):
    question: str
    answer: str
    retrieved_chunks: list[ChatNoteChunkInput] = Field(default_factory=list)
    library_item: ChatNoteLibraryItemInput | None = None
    session_id: str | None = None

    @field_validator("question", "answer")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question and answer must not be empty")
        return value.strip()

    @field_validator("session_id")
    @classmethod
    def session_id_must_not_be_blank_if_provided(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ChatNoteDraftResponse(BaseModel):
    title: str
    content_latex: str
    description: str | None = None
    library_item_id: str | None = None
    source_session_id: str | None = None
    topic_tags: list[str] | None = None
