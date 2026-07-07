from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.embeddings.base import EMBEDDING_DIMENSION, EmbeddingProvider
from app.embeddings.mock import MockEmbeddingProvider

MOCK_EMBEDDING_PROVIDER_NAMES = {"", "mock", "deterministic"}
ZHIPU_EMBEDDING_PROVIDER_NAME = "zhipu"
DEFAULT_ZHIPU_BATCH_SIZE = 16


class EmbeddingConfigurationError(ValueError):
    """Raised when the requested embedding provider is not configured safely."""


class EmbeddingProviderError(RuntimeError):
    """Raised when a configured embedding provider cannot return embeddings."""


class ZhipuEmbeddingProvider(EmbeddingProvider):
    """Zhipu OpenAI-style embedding provider selected only by backend config."""

    provider_name = ZHIPU_EMBEDDING_PROVIDER_NAME

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        dimension: int,
        client: httpx.Client | None = None,
        batch_size: int = DEFAULT_ZHIPU_BATCH_SIZE,
    ) -> None:
        if not api_key.strip():
            raise EmbeddingConfigurationError(
                "EMBEDDING_PROVIDER=zhipu requires ZHIPU_API_KEY."
            )
        if not base_url.strip():
            raise EmbeddingConfigurationError(
                "EMBEDDING_PROVIDER=zhipu requires ZHIPU_BASE_URL."
            )
        if not model.strip():
            raise EmbeddingConfigurationError(
                "EMBEDDING_PROVIDER=zhipu requires ZHIPU_EMBEDDING_MODEL."
            )
        if dimension != EMBEDDING_DIMENSION:
            raise EmbeddingConfigurationError(
                "ZHIPU_EMBEDDING_DIMENSION must match the configured pgvector "
                f"dimension {EMBEDDING_DIMENSION}; got {dimension}."
            )
        if batch_size < 1:
            raise ValueError("batch_size must be positive")

        self._api_key = api_key.strip()
        self._base_url = base_url.strip().rstrip("/")
        self._model = model.strip()
        self._dimension = dimension
        self._client = client
        self._batch_size = batch_size

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            embeddings.extend(self._embed_batch(batch))
        return embeddings

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self._model, "input": texts}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self._client is not None:
                response = self._client.post(
                    f"{self._base_url}/embeddings",
                    json=payload,
                    headers=headers,
                    timeout=60.0,
                )
            else:
                with httpx.Client(timeout=60.0) as client:
                    response = client.post(
                        f"{self._base_url}/embeddings",
                        json=payload,
                        headers=headers,
                    )
            response.raise_for_status()
            data = response.json()
            return self._extract_embeddings(data, expected_count=len(texts))
        except EmbeddingProviderError:
            raise
        except httpx.HTTPError as exc:
            raise EmbeddingProviderError("Zhipu embedding provider request failed.") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingProviderError(
                "Zhipu embedding provider returned an invalid response."
            ) from exc

    def _extract_embeddings(
        self, data: dict[str, Any], *, expected_count: int
    ) -> list[list[float]]:
        rows = data["data"]
        if len(rows) != expected_count:
            raise EmbeddingProviderError(
                "Zhipu embedding provider returned an unexpected number of embeddings."
            )

        ordered_rows = sorted(
            enumerate(rows),
            key=lambda item: item[1].get("index", item[0]),
        )
        embeddings: list[list[float]] = []
        for _, row in ordered_rows:
            embedding = row["embedding"]
            if len(embedding) != self._dimension:
                raise EmbeddingProviderError(
                    "Zhipu embedding provider returned an embedding with "
                    f"{len(embedding)} dimensions; expected {self._dimension}."
                )
            embeddings.append([float(value) for value in embedding])
        return embeddings


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    resolved_settings = settings or get_settings()
    provider_name = resolved_settings.embedding_provider.strip().lower()

    if provider_name in MOCK_EMBEDDING_PROVIDER_NAMES:
        return MockEmbeddingProvider()

    if provider_name == ZHIPU_EMBEDDING_PROVIDER_NAME:
        return ZhipuEmbeddingProvider(
            api_key=resolved_settings.zhipu_api_key,
            base_url=resolved_settings.zhipu_base_url,
            model=resolved_settings.zhipu_embedding_model,
            dimension=resolved_settings.zhipu_embedding_dimension,
        )

    raise EmbeddingConfigurationError(
        "Unsupported EMBEDDING_PROVIDER "
        f"'{resolved_settings.embedding_provider}'. Supported values: mock, zhipu."
    )

