from typing import Any

import httpx

from app.embeddings.base import EmbeddingProvider
from app.embeddings.providers import EmbeddingProviderError


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Native Gemini embedContent adapter."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        dimension: int,
        client: httpx.Client,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = dimension
        self._client = client

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> list[float]:
        try:
            response = self._client.post(
                f"{self._base_url}/models/{self._model}:embedContent",
                json={
                    "model": f"models/{self._model}",
                    "content": {"parts": [{"text": text}]},
                    "outputDimensionality": self._dimension,
                },
                headers={"x-goog-api-key": self._api_key},
            )
            response.raise_for_status()
            values: list[Any] = response.json()["embedding"]["values"]
            if len(values) != self._dimension:
                raise ValueError(
                    f"returned {len(values)} dimensions; expected {self._dimension}"
                )
            return [float(value) for value in values]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise EmbeddingProviderError("Gemini embedding request failed.") from exc
