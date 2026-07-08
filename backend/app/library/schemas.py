from datetime import datetime

from pydantic import BaseModel, Field, field_validator

DEFAULT_LIBRARY_STATUS = "registered"


class LibraryItemCreate(BaseModel):
    title: str
    author: str | None = None
    description: str | None = None
    file_path: str | None = None
    file_type: str | None = None
    topic_tags: list[str] | None = None
    status: str = DEFAULT_LIBRARY_STATUS

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

    @field_validator("author", "description", "file_path", "file_type")
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


class LibraryItemUpdate(BaseModel):
    title: str | None = None
    author: str | None = None
    description: str | None = None
    file_path: str | None = None
    file_type: str | None = None
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

    @field_validator("author", "description", "file_path", "file_type")
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


class LibraryItemRead(BaseModel):
    id: str
    title: str
    author: str | None = None
    description: str | None = None
    file_path: str | None = None
    file_type: str | None = None
    topic_tags: list[str] | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class LibraryItemListResponse(BaseModel):
    items: list[LibraryItemRead]
    total: int


class LibraryItemIndexResponse(BaseModel):
    item_id: str
    document_id: str | None
    status: str
    chunks_created: int
    embeddings_created: int
    message: str
    supported_file_types: list[str] = Field(default_factory=lambda: ["txt", "md", "pdf"])


class LibraryPdfImportRequest(BaseModel):
    source_paths: list[str]

    @field_validator("source_paths")
    @classmethod
    def source_paths_must_not_be_empty(cls, value: list[str]) -> list[str]:
        paths = [path.strip() for path in value if path.strip()]
        if not paths:
            raise ValueError("source_paths must contain at least one path")
        return paths


class LibraryPdfImportItemResponse(BaseModel):
    library_item: LibraryItemRead
    index_result: LibraryItemIndexResponse
    original_filename: str
    original_source_path: str
    managed_file_path: str
    file_size_bytes: int


class LibraryPdfImportResponse(BaseModel):
    items: list[LibraryPdfImportItemResponse]
    total: int


class LibraryMetadataDraftResponse(BaseModel):
    library_item_id: str
    title: str
    summary: str
    topic_tags: list[str]
    chunks_used: int
    mode: str
