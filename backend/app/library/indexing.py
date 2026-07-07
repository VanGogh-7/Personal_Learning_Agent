import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.embeddings.mock import MockEmbeddingProvider
from app.ingestion.chunking import chunk_text
from app.ingestion.pdf import PDFExtractionError, PDFPageText, extract_pdf_pages
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.library_item import LibraryItem

SUPPORTED_LIBRARY_INDEX_TYPES = {"txt", "md", "pdf"}
DEFAULT_INDEX_CHUNK_SIZE = 800
DEFAULT_INDEX_CHUNK_OVERLAP = 100


class LibraryIndexingError(ValueError):
    """Raised when a library item cannot be indexed due to user-facing input."""


@dataclass
class LibraryIndexResult:
    item_id: uuid.UUID
    document_id: uuid.UUID | None
    status: str
    chunks_created: int
    embeddings_created: int
    message: str


@dataclass(frozen=True)
class IndexChunk:
    index: int
    content: str
    char_start: int
    char_end: int
    page_start: int | None = None
    page_end: int | None = None


def index_library_item(session: Session, item_id: uuid.UUID) -> LibraryIndexResult | None:
    item = session.get(LibraryItem, item_id)
    if item is None:
        return None

    try:
        item.status = "indexing"
        session.flush()

        path = _validate_file_path(item.file_path)
        file_type = _detect_supported_file_type(item.file_type, path)
        chunks, content_hash = _prepare_index_chunks(path, file_type)

        document = _get_or_create_document(session, item, path, file_type)
        document.title = item.title
        document.file_path = str(path)
        document.file_type = file_type
        document.content_hash = content_hash
        session.flush()

        session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        provider = MockEmbeddingProvider()
        embeddings = provider.embed_texts([chunk.content for chunk in chunks])

        for chunk, embedding in zip(chunks, embeddings, strict=True):
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    embedding=embedding,
                )
            )

        item.status = "indexed"
        session.flush()

        return LibraryIndexResult(
            item_id=item.id,
            document_id=document.id,
            status=item.status,
            chunks_created=len(chunks),
            embeddings_created=len(embeddings),
            message="Library item indexed successfully.",
        )
    except Exception:
        item.status = "index_failed"
        session.flush()
        raise


def _validate_file_path(file_path: str | None) -> Path:
    if not file_path or not file_path.strip():
        raise LibraryIndexingError("Library item has no local file path to index.")

    path = Path(file_path).expanduser()
    if not path.exists():
        raise LibraryIndexingError(f"Library item file does not exist: {path}")
    if not path.is_file():
        raise LibraryIndexingError(f"Library item path is not a file: {path}")
    return path


def _detect_supported_file_type(file_type: str | None, path: Path) -> str:
    if path.suffix:
        extension = path.suffix.lower().lstrip(".")
        if extension in SUPPORTED_LIBRARY_INDEX_TYPES:
            return extension
        raise LibraryIndexingError(
            "Only .pdf, .txt, and .md library item indexing is supported."
        )

    if file_type and file_type.strip():
        normalized = file_type.strip().lower().lstrip(".")
        if normalized in SUPPORTED_LIBRARY_INDEX_TYPES:
            return normalized

    raise LibraryIndexingError(
        "Only .pdf, .txt, and .md library item indexing is supported."
    )


def _prepare_index_chunks(path: Path, file_type: str) -> tuple[list[IndexChunk], str]:
    if file_type == "pdf":
        try:
            pages = extract_pdf_pages(path)
        except PDFExtractionError as exc:
            raise LibraryIndexingError(str(exc)) from exc
        return _chunk_pdf_pages(pages), _content_hash(
            "\n\n".join(f"Page {page.page_number}\n{page.text}" for page in pages)
        )

    text = _read_text_file(path)
    chunks = [
        IndexChunk(
            index=chunk.index,
            content=chunk.content,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
        )
        for chunk in chunk_text(
            text,
            chunk_size=DEFAULT_INDEX_CHUNK_SIZE,
            chunk_overlap=DEFAULT_INDEX_CHUNK_OVERLAP,
        )
    ]
    return chunks, _content_hash(text)


def _chunk_pdf_pages(pages: list[PDFPageText]) -> list[IndexChunk]:
    chunks: list[IndexChunk] = []
    next_index = 0

    for page in pages:
        page_chunks = chunk_text(
            page.text,
            chunk_size=DEFAULT_INDEX_CHUNK_SIZE,
            chunk_overlap=DEFAULT_INDEX_CHUNK_OVERLAP,
        )
        for chunk in page_chunks:
            chunks.append(
                IndexChunk(
                    index=next_index,
                    content=chunk.content,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    page_start=page.page_number,
                    page_end=page.page_number,
                )
            )
            next_index += 1

    return chunks


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise LibraryIndexingError(
            f"Library item file is not valid UTF-8 text: {path}"
        ) from exc
    except OSError as exc:
        raise LibraryIndexingError(f"Could not read library item file: {path}") from exc


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _get_or_create_document(
    session: Session, item: LibraryItem, path: Path, file_type: str
) -> Document:
    existing = session.execute(
        select(Document).where(Document.library_item_id == item.id).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    document = Document(
        library_item_id=item.id,
        title=item.title,
        file_path=str(path),
        file_type=file_type,
    )
    session.add(document)
    session.flush()
    return document
