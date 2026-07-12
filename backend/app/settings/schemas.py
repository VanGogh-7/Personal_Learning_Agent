from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

ProfileKind = Literal["chat", "embedding"]
ProviderId = Literal[
    "deepseek",
    "openai",
    "openai_compatible",
    "anthropic",
    "gemini",
    "zhipu",
    "ollama",
    "custom_openai_compatible",
]
IndexStatus = Literal["pending", "building", "ready", "active", "failed"]


class ProviderCapabilities(BaseModel):
    chat: bool = False
    streaming: bool = False
    tool_calling: bool = False
    structured_output: bool = False
    embeddings: bool = False
    multimodal_input: bool = False
    native_adapter: bool = False


class ProviderCatalogEntry(BaseModel):
    provider: ProviderId
    label: str
    capabilities: ProviderCapabilities
    default_chat_base_url: str | None = None
    default_embedding_base_url: str | None = None
    requires_api_key: bool = True
    runtime_status: Literal["available", "extension_ready"] = "available"


class ProviderProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ProfileKind
    name: str = Field(min_length=1, max_length=120)
    provider: ProviderId
    api_key: SecretStr | None = Field(default=None, repr=False)
    secret_ref: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str = Field(default="", max_length=500)
    model: str = Field(min_length=1, max_length=200)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=1, le=32768)
    embedding_dimension: int | None = Field(default=None, ge=1, le=65536)
    batch_size: int | None = Field(default=None, ge=1, le=256)
    extra_headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if normalized and not normalized.startswith(("http://", "https://")):
            raise ValueError("Base URL must use http or https")
        return normalized

    @field_validator("extra_headers")
    @classmethod
    def safe_extra_headers(cls, value: dict[str, str]) -> dict[str, str]:
        allowed = {
            "user-agent",
            "openai-organization",
            "openai-project",
            "http-referer",
            "x-title",
        }
        if any(key.strip().lower() not in allowed for key in value):
            raise ValueError(
                "Only audited non-secret extra headers may be stored in profile metadata"
            )
        return {key.strip(): item.strip() for key, item in value.items() if key.strip()}

    @model_validator(mode="after")
    def validate_kind_fields(self) -> "ProviderProfileInput":
        if self.kind == "chat":
            if self.embedding_dimension is not None or self.batch_size is not None:
                raise ValueError("Embedding fields are not valid for chat profiles")
        else:
            if self.temperature is not None or self.max_output_tokens is not None:
                raise ValueError("Chat fields are not valid for embedding profiles")
            if self.embedding_dimension is None:
                raise ValueError("Embedding dimension is required")
            if self.batch_size is None:
                self.batch_size = 16
        return self


class ProviderProfileRead(BaseModel):
    id: str
    kind: ProfileKind
    name: str
    provider: ProviderId
    base_url: str
    model: str
    secret_ref: str | None
    api_key_configured: bool
    api_key_mask: str | None = None
    temperature: float | None
    max_output_tokens: int | None
    embedding_dimension: int | None
    batch_size: int | None
    extra_headers: dict[str, str]
    config_version: int
    is_active: bool
    runtime_active: bool


class ProviderProfileList(BaseModel):
    profiles: list[ProviderProfileRead]
    active_chat_profile: str | None
    active_embedding_profile: str | None


class ProviderActivationRequest(BaseModel):
    api_key: SecretStr | None = Field(default=None, repr=False)


class ProviderSecretReferenceUpdate(BaseModel):
    secret_ref: str | None = Field(default=None, max_length=200)


class ProviderConnectionTestRequest(ProviderProfileInput):
    profile_id: str | None = None


class ProviderConnectionTestResponse(BaseModel):
    success: bool
    provider: str
    model: str
    latency_ms: float
    capabilities: ProviderCapabilities
    actual_embedding_dimension: int | None = None
    message: str


class EmbeddingIndexVersionRead(BaseModel):
    id: str
    embedding_profile_id: str
    dimension: int
    status: IndexStatus
    total_chunks: int
    embedded_chunks: int


class EmbeddingReindexResponse(BaseModel):
    index_version: EmbeddingIndexVersionRead
    requires_reindex: bool
    message: str
