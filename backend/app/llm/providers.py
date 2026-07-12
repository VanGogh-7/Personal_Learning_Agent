import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

import httpx

from app.core.config import Settings, get_settings
from app.llm.deepseek_client import DeepSeekClient
from app.observability.latency import current_latency_trace
from app.providers.http_clients import provider_http_clients


@dataclass(frozen=True)
class LLMGenerationMetrics:
    text: str
    ttft_ms: float | None
    generation_ms: float | None
    total_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    streaming: bool = False


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True)
class LLMStreamChunk:
    delta: str = ""
    finish_reason: str | None = None
    usage: TokenUsage | None = None


@dataclass(frozen=True)
class LLMStructuredResult:
    text: str
    usage: TokenUsage | None = None
    temperature: float | None = 0.0


class LLMProvider(Protocol):
    """Small synchronous text-generation boundary used by backend services."""

    def generate(self, prompt: str) -> str:
        """Generate text for a prompt."""

    def complete_chat(self, prompt: str) -> str:
        """Return one normalized complete chat response."""

    def stream_chat_completion(
        self, prompt: str, *, max_tokens: int | None = None
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream normalized final-answer chunks."""


class LLMConfigurationError(ValueError):
    """Raised when the requested LLM provider is not configured safely."""


class LLMProviderError(RuntimeError):
    """Raised when a configured LLM provider cannot generate a response."""


DETERMINISTIC_PROVIDER_NAME = "deterministic"
DEEPSEEK_PROVIDER_NAME = "deepseek"
DETERMINISTIC_ANSWER_MARKER = "Deterministic reference answer:"


class DeterministicLLMProvider:
    """Deterministic provider used by tests and local development by default."""

    def generate(self, prompt: str) -> str:
        trace = current_latency_trace()
        if trace is not None:
            trace.increment("llm_call_count")
        marker_index = prompt.find(DETERMINISTIC_ANSWER_MARKER)
        if marker_index == -1:
            return prompt.strip()

        answer_start = marker_index + len(DETERMINISTIC_ANSWER_MARKER)
        return prompt[answer_start:].strip()

    def complete_chat(self, prompt: str) -> str:
        return self.generate(prompt)

    def stream_chat(
        self, prompt: str, *, max_tokens: int | None = None
    ) -> AsyncIterator[LLMStreamChunk]:
        return self.stream_chat_completion(prompt, max_tokens=max_tokens)

    def generate_with_metrics(self, prompt: str) -> LLMGenerationMetrics:
        started_at = perf_counter()
        text = self.generate(prompt)
        total_ms = (perf_counter() - started_at) * 1000
        return LLMGenerationMetrics(
            text=text,
            ttft_ms=0.0,
            generation_ms=0.0,
            total_ms=total_ms,
            streaming=False,
        )

    def generate_structured(
        self, prompt: str, *, temperature: float | None = 0.0
    ) -> LLMStructuredResult:
        return LLMStructuredResult(text=self.generate(prompt), temperature=temperature)

    async def stream_chat_completion(
        self, prompt: str, *, max_tokens: int | None = None
    ) -> AsyncIterator[LLMStreamChunk]:
        text = self.generate(prompt)
        for delta in re.findall(r"\S+\s*|\s+", text):
            if delta:
                yield LLMStreamChunk(delta=delta)
        yield LLMStreamChunk(finish_reason="stop")


class OpenAICompatibleLLMProvider:
    """Minimal OpenAI-compatible chat completions provider.

    The provider is intentionally small and is only selected when
    configuration explicitly requests a real provider.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        client: httpx.Client | None = None,
        async_client: httpx.AsyncClient | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client
        self._async_client = async_client
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._extra_headers = dict(extra_headers or {})

    @property
    def model(self) -> str:
        return self._model

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self._extra_headers}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _generation_options(self) -> dict[str, int | float]:
        options: dict[str, int | float] = {}
        if self._temperature is not None:
            options["temperature"] = self._temperature
        if self._max_output_tokens is not None:
            options["max_tokens"] = self._max_output_tokens
        return options

    def generate(self, prompt: str) -> str:
        trace = current_latency_trace()
        if trace is not None:
            trace.increment("llm_call_count")
        request_payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Answer using only the provided retrieval context. "
                        "If the context is insufficient, say so clearly."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            **self._generation_options(),
        }
        headers = self._headers()

        try:
            if self._client is not None:
                response = self._client.post(
                    f"{self._base_url}/chat/completions",
                    json=request_payload,
                    headers=headers,
                )
            else:
                response = provider_http_clients.get("llm").post(
                    f"{self._base_url}/chat/completions",
                    json=request_payload,
                    headers=headers,
                )
            response.raise_for_status()
            data = response.json()
            return _extract_openai_compatible_content(data)
        except LLMProviderError:
            raise
        except httpx.HTTPError as exc:
            raise LLMProviderError("Real LLM provider request failed.") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMProviderError(
                "Real LLM provider returned an invalid response."
            ) from exc

    def complete_chat(self, prompt: str) -> str:
        return self.generate(prompt)

    def stream_chat(
        self, prompt: str, *, max_tokens: int | None = None
    ) -> AsyncIterator[LLMStreamChunk]:
        return self.stream_chat_completion(prompt, max_tokens=max_tokens)

    def generate_structured(
        self, prompt: str, *, temperature: float | None = 0.0
    ) -> LLMStructuredResult:
        trace = current_latency_trace()
        if trace is not None:
            trace.increment("llm_call_count")
        request_payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return one JSON object matching the supplied schema.",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        request_payload.update(self._generation_options())
        if temperature is not None:
            request_payload["temperature"] = temperature
        headers = self._headers()
        try:
            client = self._client or provider_http_clients.get("llm")
            response = client.post(
                f"{self._base_url}/chat/completions",
                json=request_payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            usage = data.get("usage") or {}
            return LLMStructuredResult(
                text=_extract_openai_compatible_content(data),
                temperature=temperature,
                usage=TokenUsage(
                    prompt_tokens=usage.get("prompt_tokens")
                    if isinstance(usage.get("prompt_tokens"), int)
                    else None,
                    completion_tokens=usage.get("completion_tokens")
                    if isinstance(usage.get("completion_tokens"), int)
                    else None,
                ),
            )
        except httpx.HTTPError as exc:
            raise LLMProviderError("Structured LLM request failed.") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMProviderError("Structured LLM response was invalid.") from exc

    def generate_with_metrics(self, prompt: str) -> LLMGenerationMetrics:
        trace = current_latency_trace()
        if trace is not None:
            trace.increment("llm_call_count")
            trace.set_counter("streaming_enabled", True)
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Answer using only the provided retrieval context. "
                        "If the context is insufficient, say so clearly."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "stream": True,
            "stream_options": {"include_usage": True},
            **self._generation_options(),
        }
        headers = self._headers()
        client = self._client or provider_http_clients.get("llm")
        started_at = perf_counter()
        first_token_at: float | None = None
        last_token_at: float | None = None
        chunks: list[str] = []
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        try:
            with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    event = json.loads(data)
                    usage = event.get("usage") or {}
                    if isinstance(usage.get("prompt_tokens"), int):
                        prompt_tokens = usage["prompt_tokens"]
                    if isinstance(usage.get("completion_tokens"), int):
                        completion_tokens = usage["completion_tokens"]
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    content = (choices[0].get("delta") or {}).get("content")
                    if not isinstance(content, str) or not content:
                        continue
                    now = perf_counter()
                    if first_token_at is None:
                        first_token_at = now
                    last_token_at = now
                    chunks.append(content)
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise LLMProviderError(
                "Real LLM provider streaming request failed."
            ) from exc
        text = "".join(chunks).strip()
        if not text or first_token_at is None or last_token_at is None:
            raise LLMProviderError("Real LLM provider returned an empty stream.")
        return LLMGenerationMetrics(
            text=text,
            ttft_ms=(first_token_at - started_at) * 1000,
            generation_ms=(last_token_at - first_token_at) * 1000,
            total_ms=(last_token_at - started_at) * 1000,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            streaming=True,
        )

    async def stream_chat_completion(
        self, prompt: str, *, max_tokens: int | None = None
    ) -> AsyncIterator[LLMStreamChunk]:
        trace = current_latency_trace()
        if trace is not None:
            trace.increment("llm_call_count")
            trace.set_counter("streaming_enabled", True)
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Answer using only the provided retrieval context. "
                        "If the context is insufficient, say so clearly."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "stream": True,
            "stream_options": {"include_usage": True},
            **self._generation_options(),
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        headers = self._headers()
        client = self._async_client or provider_http_clients.get_async("llm")
        try:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    event = json.loads(data)
                    usage_data = event.get("usage") or {}
                    usage = (
                        TokenUsage(
                            prompt_tokens=usage_data.get("prompt_tokens"),
                            completion_tokens=usage_data.get("completion_tokens"),
                        )
                        if usage_data
                        else None
                    )
                    choices = event.get("choices") or []
                    if not choices:
                        if usage is not None:
                            yield LLMStreamChunk(usage=usage)
                        continue
                    choice = choices[0]
                    delta = (choice.get("delta") or {}).get("content") or ""
                    finish_reason = choice.get("finish_reason")
                    if delta or finish_reason is not None or usage is not None:
                        yield LLMStreamChunk(
                            delta=delta if isinstance(delta, str) else "",
                            finish_reason=(
                                finish_reason
                                if isinstance(finish_reason, str)
                                else None
                            ),
                            usage=usage,
                        )
        except LLMProviderError:
            raise
        except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise LLMProviderError(
                "Real LLM provider streaming request failed."
            ) from exc


class DeepSeekLLMProvider(OpenAICompatibleLLMProvider):
    """DeepSeek chat provider using its OpenAI-compatible API."""


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Return the configured LLM provider.

    Deterministic mode is the default and does not require secrets or
    network access. Real providers are selected only by explicit config.
    """

    if settings is None:
        from app.settings.runtime import current_chat_provider

        active = current_chat_provider()
        if active is not None:
            return active
    resolved_settings = settings or get_settings()
    provider_name = resolved_settings.llm_provider.strip().lower()
    trace = current_latency_trace()
    if trace is not None:
        trace.set_counter("llm_provider", provider_name or "deterministic")
        trace.set_counter(
            "llm_model",
            resolved_settings.deepseek_model
            if provider_name == DEEPSEEK_PROVIDER_NAME
            else "deterministic",
        )

    if provider_name in {"", DETERMINISTIC_PROVIDER_NAME, "mock"}:
        return DeterministicLLMProvider()

    if provider_name == DEEPSEEK_PROVIDER_NAME:
        client_config = DeepSeekClient(settings=resolved_settings)
        api_key = client_config.api_key.strip()
        base_url = client_config.base_url.strip()
        model = client_config.model.strip()
        missing = [
            name
            for name, value in [
                ("DEEPSEEK_API_KEY", api_key),
                ("DEEPSEEK_BASE_URL", base_url),
                ("DEEPSEEK_MODEL", model),
            ]
            if not value
        ]
        if missing:
            raise LLMConfigurationError(
                "LLM_PROVIDER=deepseek requires " + ", ".join(missing) + "."
            )
        return DeepSeekLLMProvider(
            api_key=api_key,
            base_url=base_url,
            model=model,
            client=(
                provider_http_clients.get("llm", resolved_settings)
                if settings is None
                else None
            ),
            async_client=(
                provider_http_clients.get_async("llm", resolved_settings)
                if settings is None
                else None
            ),
        )

    raise LLMConfigurationError(
        "Unsupported LLM_PROVIDER "
        f"'{resolved_settings.llm_provider}'. Supported values: deterministic, deepseek."
    )


def _extract_openai_compatible_content(data: dict[str, Any]) -> str:
    choices = data["choices"]
    if not choices:
        raise LLMProviderError("Real LLM provider returned no choices.")

    content = choices[0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise LLMProviderError("Real LLM provider returned an empty response.")
    return content.strip()
