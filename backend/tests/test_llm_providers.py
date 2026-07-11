import httpx
import pytest

from app.core.config import Settings
from app.llm.providers import (
    DeepSeekLLMProvider,
    DeterministicLLMProvider,
    LLMConfigurationError,
    LLMProviderError,
    OpenAICompatibleLLMProvider,
    get_llm_provider,
)
from app.observability.latency import AgentLatencyTrace, latency_trace_context
from app.providers.http_clients import ProviderHttpClientManager


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
            json={
                "choices": [{"message": {"content": "Mocked real-provider answer."}}]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLLMProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
        client=client,
    )

    assert provider.generate("Question?") == "Mocked real-provider answer."


def test_openai_compatible_provider_failure_is_clean_and_does_not_leak_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLLMProvider(
        api_key="secret-test-key",
        base_url="https://api.example.com",
        model="test-model",
        client=client,
    )

    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate("Question?")

    message = str(exc_info.value)
    assert message == "Real LLM provider request failed."
    assert "secret-test-key" not in message


def test_streaming_provider_measures_ttft_and_generation() -> None:
    body = "\n".join(
        [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            'data: {"choices":[{"delta":{"content":" world"}}]}',
            'data: {"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":2}}',
            "data: [DONE]",
            "",
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert b'"stream":true' in request.content
        return httpx.Response(200, text=body)

    provider = OpenAICompatibleLLMProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    trace = AgentLatencyTrace()
    with latency_trace_context(trace):
        result = provider.generate_with_metrics("Question?")
    assert result.text == "Hello world"
    assert result.ttft_ms is not None and result.ttft_ms >= 0
    assert result.generation_ms is not None and result.generation_ms >= 0
    assert result.total_ms >= result.ttft_ms
    assert result.prompt_tokens == 7
    assert result.completion_tokens == 2
    assert trace.counters["llm_call_count"] == 1


def test_streaming_provider_timeout_is_clean() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    provider = OpenAICompatibleLLMProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LLMProviderError, match="streaming request failed"):
        provider.generate_with_metrics("Question?")


def test_provider_http_client_manager_reuses_and_closes_clients() -> None:
    manager = ProviderHttpClientManager()
    settings = Settings(_env_file=None)
    first = manager.get("llm", settings)
    second = manager.get("llm", settings)
    assert first is second
    manager.close()
    assert first.is_closed


@pytest.mark.anyio
async def test_provider_http_client_manager_reuses_and_closes_async_clients() -> None:
    manager = ProviderHttpClientManager()
    settings = Settings(_env_file=None)
    first = manager.get_async("llm", settings)
    second = manager.get_async("llm", settings)
    assert first is second
    await manager.aclose()
    assert first.is_closed


def test_provider_http_client_manager_reuses_web_client() -> None:
    manager = ProviderHttpClientManager()
    settings = Settings(_env_file=None)
    first = manager.get("web", settings)
    second = manager.get("web", settings)
    assert first is second
    manager.close()
    assert first.is_closed
