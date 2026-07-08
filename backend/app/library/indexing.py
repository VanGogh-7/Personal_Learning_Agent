import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.embeddings.base import EmbeddingProvider
from app.embeddings.providers import get_embedding_provider
from app.ingestion.chunking import chunk_text
from app.ingestion.pdf import PDFExtractionError, PDFPageText, extract_pdf_pages
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.library_item import LibraryItem

SUPPORTED_LIBRARY_INDEX_TYPES = {"txt", "md", "pdf"}
DEFAULT_INDEX_CHUNK_SIZE = 800
DEFAULT_INDEX_CHUNK_OVERLAP = 100
SECTION_BODY = "body"
SECTION_CONTENTS = "contents"
SECTION_INDEX = "index"
SECTION_BIBLIOGRAPHY = "bibliography"
SECTION_PREFACE = "preface"
SECTION_UNKNOWN = "unknown"


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
    section_type: str = SECTION_UNKNOWN


def index_library_item(
    session: Session,
    item_id: uuid.UUID,
    embedding_provider: EmbeddingProvider | None = None,
) -> LibraryIndexResult | None:
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
        provider = embedding_provider or get_embedding_provider()
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
                    section_type=chunk.section_type,
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
        pages = [
            PDFPageText(page_number=page.page_number, text=_clean_text_for_storage(page.text))
            for page in pages
        ]
        return _chunk_pdf_pages(pages), _content_hash(
            "\n\n".join(f"Page {page.page_number}\n{page.text}" for page in pages)
        )

    text = _clean_text_for_storage(_read_text_file(path))
    chunks = [
        IndexChunk(
            index=chunk.index,
            content=chunk.content,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            section_type=SECTION_BODY,
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
    current_section_type = SECTION_UNKNOWN

    for page in pages:
        detected_section_type = classify_pdf_section_type(page.text)
        section_type = _resolve_pdf_page_section_type(
            page.text,
            detected_section_type=detected_section_type,
            current_section_type=current_section_type,
        )
        if section_type != SECTION_UNKNOWN:
            current_section_type = section_type
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
                    section_type=section_type,
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


def _clean_text_for_storage(text: str) -> str:
    return text.replace("\x00", "")


def classify_pdf_section_type(text: str) -> str:
    normalized = _normalize_for_section_detection(text)
    if not normalized:
        return SECTION_UNKNOWN

    first_line = normalized.splitlines()[0]
    first_words = " ".join(normalized.split()[:12])

    if re.match(r"^([ivxlcdm]+\s+)?contents\b", first_line):
        return SECTION_CONTENTS
    if re.match(r"^table of contents\b", first_line):
        return SECTION_CONTENTS
    if _looks_like_contents_page(normalized):
        return SECTION_CONTENTS
    if re.match(r"^(index|name index|subject index)\b", first_line):
        return SECTION_INDEX
    if re.match(r"^(bibliography|references)\b", first_line):
        return SECTION_BIBLIOGRAPHY
    if re.match(r"^(preface|foreword|introduction to the .*edition)\b", first_line):
        return SECTION_PREFACE
    if " preface " in f" {first_words} ":
        return SECTION_PREFACE

    return SECTION_BODY


def _resolve_pdf_page_section_type(
    text: str,
    *,
    detected_section_type: str,
    current_section_type: str,
) -> str:
    non_body_sections = {
        SECTION_CONTENTS,
        SECTION_INDEX,
        SECTION_BIBLIOGRAPHY,
        SECTION_PREFACE,
    }
    if detected_section_type in non_body_sections:
        return detected_section_type
    if (
        current_section_type in non_body_sections
        and detected_section_type == SECTION_BODY
        and not _looks_like_body_start(text)
    ):
        return current_section_type
    return detected_section_type


def _normalize_for_section_detection(text: str) -> str:
    lines = [" ".join(line.strip().split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines).casefold()


def _looks_like_contents_page(normalized: str) -> bool:
    dot_leaders = normalized.count("...")
    has_many_numbered_headings = len(re.findall(r"\b\d+\s+[a-z]", normalized)) >= 4
    has_contents_heading = "contents" in normalized[:120]
    return has_contents_heading and (dot_leaders >= 3 or has_many_numbered_headings)


def _looks_like_body_start(text: str) -> bool:
    normalized = _normalize_for_section_detection(text)
    if not normalized:
        return False
    first_line = normalized.splitlines()[0]
    first_words = " ".join(normalized.split()[:10])
    return bool(
        re.match(r"^(chapter\s+[ivxlcdm]+|[ivxlcdm]+\.\d+)\b", first_line)
        or re.match(r"^\d+\s+[ivxlcdm]+\s+[a-z]", first_line)
        or re.search(r"\b[ivxlcdm]+\.\d+\s+[a-z]", first_words)
    )


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
