from abc import ABC, abstractmethod

# Stage 36A aligns the persisted pgvector column with the configured
# Zhipu embedding-3 dimension used for real PDF indexing.
EMBEDDING_DIMENSION = 2048


class EmbeddingProvider(ABC):
    """Abstract base for embedding providers."""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Return a fixed-length embedding vector for a single text."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the provider's embedding dimension."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """Normalized Provider-facing query embedding operation."""
        return self.embed_text(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Normalized Provider-facing document embedding operation."""
        return self.embed_texts(texts)
