import json
from collections.abc import AsyncIterator

import httpx

from app.llm.providers import (
    LLMProviderError,
    LLMStreamChunk,
    LLMStructuredResult,
    TokenUsage,
)


class AnthropicLLMProvider:
    """Native Anthropic Messages adapter with normalized PLA output."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        client: httpx.Client,
        async_client: httpx.AsyncClient,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client
        self._async_client = async_client
        self._temperature = temperature
        self._max_tokens = max_output_tokens or 2000

    def _payload(self, prompt: str, *, stream: bool = False) -> dict:
        payload = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }
        if self._temperature is not None:
            payload["temperature"] = self._temperature
        return payload

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def generate(self, prompt: str) -> str:
        try:
            response = self._client.post(
                f"{self._base_url}/messages",
                json=self._payload(prompt),
                headers=self._headers(),
            )
            response.raise_for_status()
            text = "".join(
                item.get("text", "")
                for item in response.json().get("content", [])
                if item.get("type") == "text"
            ).strip()
            if not text:
                raise ValueError("empty content")
            return text
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise LLMProviderError("Anthropic provider request failed.") from exc

    def complete_chat(self, prompt: str) -> str:
        return self.generate(prompt)

    def stream_chat(
        self, prompt: str, *, max_tokens: int | None = None
    ) -> AsyncIterator[LLMStreamChunk]:
        return self.stream_chat_completion(prompt, max_tokens=max_tokens)

    async def stream_chat_completion(
        self, prompt: str, *, max_tokens: int | None = None
    ) -> AsyncIterator[LLMStreamChunk]:
        payload = self._payload(prompt, stream=True)
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        try:
            async with self._async_client.stream(
                "POST",
                f"{self._base_url}/messages",
                json=payload,
                headers=self._headers(),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line[5:].strip())
                    if event.get("type") == "content_block_delta":
                        text = (event.get("delta") or {}).get("text") or ""
                        if text:
                            yield LLMStreamChunk(delta=text)
                    elif event.get("type") == "message_stop":
                        yield LLMStreamChunk(finish_reason="stop")
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise LLMProviderError("Anthropic provider stream failed.") from exc


class GeminiLLMProvider:
    """Native Gemini generateContent adapter with normalized PLA output."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        client: httpx.Client,
        async_client: httpx.AsyncClient,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client
        self._async_client = async_client
        self._temperature = temperature
        self._max_tokens = max_output_tokens

    def _payload(
        self,
        prompt: str,
        *,
        json_output: bool = False,
        temperature: float | None = None,
    ) -> dict:
        generation: dict[str, object] = {}
        resolved_temperature = self._temperature if temperature is None else temperature
        if resolved_temperature is not None:
            generation["temperature"] = resolved_temperature
        if self._max_tokens is not None:
            generation["maxOutputTokens"] = self._max_tokens
        if json_output:
            generation["responseMimeType"] = "application/json"
        return {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation,
        }

    def _url(self, operation: str) -> str:
        return f"{self._base_url}/models/{self._model}:{operation}"

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self._api_key, "content-type": "application/json"}

    @staticmethod
    def _text(payload: dict) -> str:
        parts = payload["candidates"][0]["content"]["parts"]
        text = "".join(part.get("text", "") for part in parts).strip()
        if not text:
            raise ValueError("empty content")
        return text

    def generate(self, prompt: str) -> str:
        try:
            response = self._client.post(
                self._url("generateContent"),
                json=self._payload(prompt),
                headers=self._headers(),
            )
            response.raise_for_status()
            return self._text(response.json())
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise LLMProviderError("Gemini provider request failed.") from exc

    def complete_chat(self, prompt: str) -> str:
        return self.generate(prompt)

    def stream_chat(
        self, prompt: str, *, max_tokens: int | None = None
    ) -> AsyncIterator[LLMStreamChunk]:
        return self.stream_chat_completion(prompt, max_tokens=max_tokens)

    def generate_structured(
        self, prompt: str, *, temperature: float | None = 0.0
    ) -> LLMStructuredResult:
        try:
            response = self._client.post(
                self._url("generateContent"),
                json=self._payload(prompt, json_output=True, temperature=temperature),
                headers=self._headers(),
            )
            response.raise_for_status()
            usage = response.json().get("usageMetadata") or {}
            return LLMStructuredResult(
                text=self._text(response.json()),
                temperature=temperature,
                usage=TokenUsage(
                    prompt_tokens=usage.get("promptTokenCount"),
                    completion_tokens=usage.get("candidatesTokenCount"),
                ),
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise LLMProviderError("Gemini structured request failed.") from exc

    async def stream_chat_completion(
        self, prompt: str, *, max_tokens: int | None = None
    ) -> AsyncIterator[LLMStreamChunk]:
        payload = self._payload(prompt)
        if max_tokens is not None:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens
        try:
            async with self._async_client.stream(
                "POST",
                self._url("streamGenerateContent") + "?alt=sse",
                json=payload,
                headers=self._headers(),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line[5:].strip())
                    text = self._text(event)
                    if text:
                        yield LLMStreamChunk(delta=text)
                yield LLMStreamChunk(finish_reason="stop")
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError) as exc:
            raise LLMProviderError("Gemini provider stream failed.") from exc
