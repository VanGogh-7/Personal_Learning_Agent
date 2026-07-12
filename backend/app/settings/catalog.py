from app.settings.schemas import (
    ProviderCapabilities,
    ProviderCatalogEntry,
    ProviderId,
)

_OPENAI_CHAT = ProviderCapabilities(
    chat=True,
    streaming=True,
    tool_calling=True,
    structured_output=True,
)

PROVIDER_CATALOG: dict[ProviderId, ProviderCatalogEntry] = {
    "deepseek": ProviderCatalogEntry(
        provider="deepseek",
        label="DeepSeek",
        capabilities=_OPENAI_CHAT,
        default_chat_base_url="https://api.deepseek.com",
    ),
    "openai": ProviderCatalogEntry(
        provider="openai",
        label="OpenAI",
        capabilities=ProviderCapabilities.model_validate(
            {**_OPENAI_CHAT.model_dump(), "embeddings": True, "multimodal_input": True}
        ),
        default_chat_base_url="https://api.openai.com/v1",
        default_embedding_base_url="https://api.openai.com/v1",
    ),
    "openai_compatible": ProviderCatalogEntry(
        provider="openai_compatible",
        label="OpenAI-compatible",
        capabilities=ProviderCapabilities.model_validate(
            {**_OPENAI_CHAT.model_dump(), "embeddings": True}
        ),
        requires_api_key=False,
    ),
    "custom_openai_compatible": ProviderCatalogEntry(
        provider="custom_openai_compatible",
        label="Custom OpenAI-compatible",
        capabilities=ProviderCapabilities.model_validate(
            {**_OPENAI_CHAT.model_dump(), "embeddings": True}
        ),
        requires_api_key=False,
    ),
    "ollama": ProviderCatalogEntry(
        provider="ollama",
        label="Ollama",
        capabilities=ProviderCapabilities(
            chat=True, streaming=True, structured_output=True, embeddings=True
        ),
        default_chat_base_url="http://127.0.0.1:11434/v1",
        default_embedding_base_url="http://127.0.0.1:11434/v1",
        requires_api_key=False,
    ),
    "zhipu": ProviderCatalogEntry(
        provider="zhipu",
        label="Zhipu",
        capabilities=ProviderCapabilities(
            chat=True, streaming=True, structured_output=True, embeddings=True
        ),
        default_chat_base_url="https://open.bigmodel.cn/api/paas/v4",
        default_embedding_base_url="https://open.bigmodel.cn/api/paas/v4",
    ),
    "anthropic": ProviderCatalogEntry(
        provider="anthropic",
        label="Anthropic",
        capabilities=ProviderCapabilities(
            chat=True,
            streaming=True,
            tool_calling=True,
            structured_output=False,
            multimodal_input=True,
            native_adapter=True,
        ),
        default_chat_base_url="https://api.anthropic.com/v1",
        runtime_status="available",
    ),
    "gemini": ProviderCatalogEntry(
        provider="gemini",
        label="Gemini",
        capabilities=ProviderCapabilities(
            chat=True,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            embeddings=True,
            multimodal_input=True,
            native_adapter=True,
        ),
        default_chat_base_url="https://generativelanguage.googleapis.com/v1beta",
        default_embedding_base_url="https://generativelanguage.googleapis.com/v1beta",
        runtime_status="available",
    ),
}


def get_provider_entry(provider: ProviderId) -> ProviderCatalogEntry:
    return PROVIDER_CATALOG[provider]


def list_provider_catalog() -> list[ProviderCatalogEntry]:
    return list(PROVIDER_CATALOG.values())
