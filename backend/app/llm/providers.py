from typing import Any, Protocol

import httpx

from app.core.config import Settings, get_settings
from app.llm.deepseek_client import DeepSeekClient


class LLMProvider(Protocol):
    """Small synchronous text-generation boundary used by backend services."""

    def generate(self, prompt: str) -> str:
        """Generate text for a prompt."""


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
        marker_index = prompt.find(DETERMINISTIC_ANSWER_MARKER)
        if marker_index == -1:
            return prompt.strip()

        answer_start = marker_index + len(DETERMINISTIC_ANSWER_MARKER)
        return prompt[answer_start:].strip()


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
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client

    def generate(self, prompt: str) -> str:
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
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self._client is not None:
                response = self._client.post(
                    f"{self._base_url}/chat/completions",
                    json=request_payload,
                    headers=headers,
                    timeout=30.0,
                )
            else:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(
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
            raise LLMProviderError("Real LLM provider returned an invalid response.") from exc


class DeepSeekLLMProvider(OpenAICompatibleLLMProvider):
    """DeepSeek chat provider using its OpenAI-compatible API."""


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Return the configured LLM provider.

    Deterministic mode is the default and does not require secrets or
    network access. Real providers are selected only by explicit config.
    """

    resolved_settings = settings or get_settings()
    provider_name = resolved_settings.llm_provider.strip().lower()

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
        return DeepSeekLLMProvider(api_key=api_key, base_url=base_url, model=model)

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
