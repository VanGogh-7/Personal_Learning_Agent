from abc import ABC, abstractmethod

# Stage 4 uses a small deterministic dimension for development/testing only;
# this is not a production-scale embedding size.
EMBEDDING_DIMENSION = 16


class EmbeddingProvider(ABC):
    """Abstract base for embedding providers."""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Return a fixed-length embedding vector for a single text."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]
