import httpx
import pytest

from app.core.config import Settings
from app.llm.providers import (
    DeepSeekLLMProvider,
    DeterministicLLMProvider,
    LLMConfigurationError,
    OpenAICompatibleLLMProvider,
    get_llm_provider,
)


def test_default_provider_is_deterministic() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "deterministic"


def test_provider_factory_returns_deterministic_by_default() -> None:
    provider = get_llm_provider(Settings(_env_file=None))
    assert isinstance(provider, DeterministicLLMProvider)


def test_deterministic_provider_does_not_require_api_key() -> None:
    settings = Settings(_env_file=None, deepseek_api_key="")
    provider = get_llm_provider(settings)
    assert isinstance(provider, DeterministicLLMProvider)


def test_unsupported_provider_config_fails_clearly() -> None:
    settings = Settings(_env_file=None, llm_provider="unknown-provider")
    with pytest.raises(LLMConfigurationError, match="Unsupported LLM_PROVIDER"):
        get_llm_provider(settings)


def test_deepseek_provider_without_api_key_fails_clearly() -> None:
    settings = Settings(_env_file=None, llm_provider="deepseek", deepseek_api_key="")
    with pytest.raises(LLMConfigurationError, match="DEEPSEEK_API_KEY"):
        get_llm_provider(settings)


def test_deepseek_provider_requires_model_and_base_url() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="deepseek",
        deepseek_api_key="test-key",
        deepseek_base_url="",
        deepseek_model="",
    )

    with pytest.raises(LLMConfigurationError) as exc_info:
        get_llm_provider(settings)

    assert "DEEPSEEK_BASE_URL" in str(exc_info.value)
    assert "DEEPSEEK_MODEL" in str(exc_info.value)


def test_provider_factory_returns_deepseek_when_explicitly_configured() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="deepseek",
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
    )

    provider = get_llm_provider(settings)

    assert isinstance(provider, DeepSeekLLMProvider)


def test_openai_compatible_provider_can_use_mocked_client_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.example.com/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Mocked real-provider answer."}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLLMProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
        client=client,
    )

    assert provider.generate("Question?") == "Mocked real-provider answer."
