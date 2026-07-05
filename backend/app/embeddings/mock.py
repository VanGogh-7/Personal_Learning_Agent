import hashlib

from app.embeddings.base import EMBEDDING_DIMENSION, EmbeddingProvider


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic mock embedding provider for development and tests.

    Not a real embedding model: derives a fixed-length vector from a
    SHA-256 hash of the input text. The same text always yields the same
    vector, and no external API calls or API keys are involved.
    """

    def embed_text(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()

        values = [
            (digest[i % len(digest)] / 255.0) * 2.0 - 1.0 for i in range(EMBEDDING_DIMENSION)
        ]

        norm = sum(value * value for value in values) ** 0.5
        if norm > 0:
            values = [value / norm for value in values]

        return values
