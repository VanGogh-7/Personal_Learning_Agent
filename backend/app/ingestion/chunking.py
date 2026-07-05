from app.ingestion.schemas import Chunk


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    """Split text into overlapping character-based chunks.

    Raises ValueError if chunk_size/chunk_overlap are invalid.
    Returns an empty list for empty or whitespace-only text.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be non-negative")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    if not text or not text.strip():
        return []

    step = chunk_size - chunk_overlap
    length = len(text)

    chunks: list[Chunk] = []
    start = 0
    index = 0

    while start < length:
        end = min(start + chunk_size, length)
        chunks.append(
            Chunk(index=index, content=text[start:end], char_start=start, char_end=end)
        )
        index += 1
        if end == length:
            break
        start += step

    return chunks
