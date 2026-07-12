from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TavilySearchArguments(ToolArguments):
    query: str = Field(min_length=1, max_length=400)
    max_results: int = Field(default=5, ge=1, le=10)
    search_depth: Literal["basic", "advanced"] = "basic"


class TavilyExtractArguments(ToolArguments):
    urls: list[str] = Field(min_length=1, max_length=3)
    extract_depth: Literal["basic", "advanced"] = "basic"

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, values: list[str]) -> list[str]:
        return [_bounded_http_url(value) for value in values]


class BraveSearchArguments(ToolArguments):
    query: str = Field(min_length=1, max_length=400)
    count: int = Field(default=5, ge=1, le=10)
    safesearch: Literal["off", "moderate", "strict"] = "moderate"
    freshness: str | None = Field(default=None, max_length=32)


class FetchArguments(ToolArguments):
    url: str = Field(min_length=1, max_length=2_048)
    max_characters: int = Field(default=12_000, ge=1_000, le=50_000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _bounded_http_url(value)


class AcademicSearchArguments(ToolArguments):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)


class DoiLookupArguments(ToolArguments):
    doi: str = Field(min_length=7, max_length=256)

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, value: str) -> str:
        normalized = value.strip().lower()
        normalized = normalized.removeprefix("https://doi.org/").removeprefix("doi:")
        if not re.fullmatch(r"10\.\d{4,9}/\S+", normalized):
            raise ValueError("Invalid DOI")
        return normalized.rstrip(".,;)")


class PaperMetadataArguments(ToolArguments):
    identifier: str = Field(min_length=3, max_length=256)


TOOL_ARGUMENT_MODELS: dict[tuple[str, str], type[ToolArguments]] = {
    ("tavily", "tavily-search"): TavilySearchArguments,
    ("tavily", "tavily-extract"): TavilyExtractArguments,
    ("brave", "brave_web_search"): BraveSearchArguments,
    ("brave", "brave_news_search"): BraveSearchArguments,
    ("fetch", "fetch"): FetchArguments,
    ("academic", "search_arxiv"): AcademicSearchArguments,
    ("academic", "search_openalex"): AcademicSearchArguments,
    ("academic", "lookup_doi"): DoiLookupArguments,
    ("academic", "get_paper_metadata"): PaperMetadataArguments,
}


def validate_tool_arguments(
    server: str, tool: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    model = TOOL_ARGUMENT_MODELS.get((server, tool))
    if model is None:
        raise ValueError("MCP tool has no approved argument schema")
    return model.model_validate(arguments).model_dump(exclude_none=True)


def _bounded_http_url(value: str) -> str:
    normalized = value.strip()
    if not normalized.lower().startswith(("http://", "https://")):
        raise ValueError("Only HTTP and HTTPS URLs are allowed")
    return normalized
