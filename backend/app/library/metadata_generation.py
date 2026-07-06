import re
import uuid
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.library_item import LibraryItem

DEFAULT_METADATA_MAX_CHUNKS = 6
DEFAULT_METADATA_MAX_TAGS = 8
MIN_METADATA_MAX_CHUNKS = 1
MAX_METADATA_MAX_CHUNKS = 8
MIN_METADATA_MAX_TAGS = 1
MAX_METADATA_MAX_TAGS = 12
DETERMINISTIC_METADATA_MODE = "deterministic"

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9'-]*")
_STOPWORDS = {
    "about",
    "above",
    "after",
    "again",
    "against",
    "also",
    "among",
    "because",
    "been",
    "before",
    "being",
    "between",
    "both",
    "cannot",
    "chapter",
    "could",
    "does",
    "doing",
    "down",
    "each",
    "from",
    "further",
    "have",
    "having",
    "here",
    "into",
    "itself",
    "more",
    "most",
    "other",
    "over",
    "same",
    "section",
    "should",
    "some",
    "such",
    "than",
    "that",
    "their",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "under",
    "until",
    "very",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "your",
}


class LibraryMetadataGenerationError(ValueError):
    """Raised when a Library item is not ready for metadata generation."""


@dataclass(frozen=True)
class LibraryMetadataDraftResult:
    library_item_id: uuid.UUID
    title: str
    summary: str
    topic_tags: list[str]
    chunks_used: int
    mode: str = DETERMINISTIC_METADATA_MODE


def generate_library_metadata_draft(
    session: Session,
    library_item_id: uuid.UUID,
    max_chunks: int = DEFAULT_METADATA_MAX_CHUNKS,
    max_tags: int = DEFAULT_METADATA_MAX_TAGS,
) -> LibraryMetadataDraftResult | None:
    _validate_bounds(max_chunks, max_tags)

    item = session.get(LibraryItem, library_item_id)
    if item is None:
        return None
    if item.status != "indexed":
        raise LibraryMetadataGenerationError(
            "Index this item before generating summary and tags."
        )

    chunks = _load_representative_chunks(session, library_item_id, max_chunks=max_chunks)
    if not chunks:
        raise LibraryMetadataGenerationError(
            "Indexed library item has no chunks for metadata generation."
        )

    topic_tags = generate_library_topic_tags_draft_from_chunks(
        chunks=chunks,
        title=item.title,
        max_tags=max_tags,
    )
    summary = generate_library_summary_draft_from_chunks(
        item=item,
        chunks=chunks,
        topic_tags=topic_tags,
    )

    return LibraryMetadataDraftResult(
        library_item_id=item.id,
        title=item.title,
        summary=summary,
        topic_tags=topic_tags,
        chunks_used=len(chunks),
    )


def generate_library_summary_draft(
    session: Session,
    library_item_id: uuid.UUID,
    max_chunks: int = DEFAULT_METADATA_MAX_CHUNKS,
    max_tags: int = DEFAULT_METADATA_MAX_TAGS,
) -> str | None:
    draft = generate_library_metadata_draft(
        session,
        library_item_id,
        max_chunks=max_chunks,
        max_tags=max_tags,
    )
    return draft.summary if draft is not None else None


def generate_library_topic_tags_draft(
    session: Session,
    library_item_id: uuid.UUID,
    max_chunks: int = DEFAULT_METADATA_MAX_CHUNKS,
    max_tags: int = DEFAULT_METADATA_MAX_TAGS,
) -> list[str] | None:
    draft = generate_library_metadata_draft(
        session,
        library_item_id,
        max_chunks=max_chunks,
        max_tags=max_tags,
    )
    return draft.topic_tags if draft is not None else None


def generate_library_summary_draft_from_chunks(
    item: LibraryItem,
    chunks: list[DocumentChunk],
    topic_tags: list[str],
) -> str:
    title = item.title.strip()
    source_label = title or "this Library item"
    file_type = item.file_type.strip().lower().lstrip(".") if item.file_type else None
    topic_phrase = _topic_phrase(topic_tags)
    format_phrase = f" {file_type.upper()} material" if file_type else " material"

    return (
        f"This{format_phrase} appears to cover topics related to {topic_phrase}. "
        f"It is based on {len(chunks)} indexed chunks from {source_label}."
    )


def generate_library_topic_tags_draft_from_chunks(
    chunks: list[DocumentChunk],
    title: str,
    max_tags: int = DEFAULT_METADATA_MAX_TAGS,
) -> list[str]:
    counter: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    position = 0

    for text in [title, *[chunk.content for chunk in chunks]]:
        for token in _tokenize(text):
            counter[token] += 1
            if token not in first_seen:
                first_seen[token] = position
            position += 1

    ranked = sorted(counter, key=lambda token: (-counter[token], first_seen[token], token))
    return ranked[:max_tags]


def _load_representative_chunks(
    session: Session,
    library_item_id: uuid.UUID,
    max_chunks: int,
) -> list[DocumentChunk]:
    stmt = (
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.library_item_id == library_item_id)
        .order_by(Document.created_at.asc(), Document.id.asc(), DocumentChunk.chunk_index.asc())
        .limit(max_chunks)
    )
    return list(session.execute(stmt).scalars().all())


def _validate_bounds(max_chunks: int, max_tags: int) -> None:
    if not (MIN_METADATA_MAX_CHUNKS <= max_chunks <= MAX_METADATA_MAX_CHUNKS):
        raise LibraryMetadataGenerationError(
            f"max_chunks must be between {MIN_METADATA_MAX_CHUNKS} and {MAX_METADATA_MAX_CHUNKS}."
        )
    if not (MIN_METADATA_MAX_TAGS <= max_tags <= MAX_METADATA_MAX_TAGS):
        raise LibraryMetadataGenerationError(
            f"max_tags must be between {MIN_METADATA_MAX_TAGS} and {MAX_METADATA_MAX_TAGS}."
        )


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text.lower()):
        token = match.group(0).strip("'-")
        if len(token) < 4:
            continue
        if token in _STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _topic_phrase(topic_tags: list[str]) -> str:
    if not topic_tags:
        return "the indexed source text"
    if len(topic_tags) == 1:
        return topic_tags[0]
    if len(topic_tags) == 2:
        return f"{topic_tags[0]} and {topic_tags[1]}"
    selected = topic_tags[:5]
    return f"{', '.join(selected[:-1])}, and {selected[-1]}"
