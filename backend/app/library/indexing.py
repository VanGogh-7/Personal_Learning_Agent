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
PDF_INDEX_CHUNK_SIZE_CHARS = 4000
PDF_INDEX_CHUNK_OVERLAP_CHARS = 650
PDF_INDEX_MIN_CHUNK_CHARS = 350
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
    chapter_title: str | None = None
    section_title: str | None = None


@dataclass(frozen=True)
class PdfChunkingConfig:
    chunk_size_chars: int = PDF_INDEX_CHUNK_SIZE_CHARS
    chunk_overlap_chars: int = PDF_INDEX_CHUNK_OVERLAP_CHARS
    min_chunk_chars: int = PDF_INDEX_MIN_CHUNK_CHARS


@dataclass(frozen=True)
class PdfPageForChunking:
    page_number: int
    text: str
    section_type: str
    char_start: int
    char_end: int
    chapter_title: str | None = None
    section_title: str | None = None


@dataclass(frozen=True)
class PageSpan:
    page_number: int
    start: int
    end: int
    chapter_title: str | None
    section_title: str | None


@dataclass(frozen=True)
class PdfHeadingContext:
    chapter_title: str | None = None
    section_title: str | None = None


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
                    chapter_title=chunk.chapter_title,
                    section_title=chunk.section_title,
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
    prepared_pages = _prepare_pdf_pages_for_chunking(pages)
    chunks: list[IndexChunk] = []
    next_index = 0
    group: list[PdfPageForChunking] = []
    group_section_type: str | None = None

    for page in prepared_pages:
        if group and page.section_type != group_section_type:
            chunks.extend(
                _chunk_pdf_page_group(
                    group,
                    section_type=group_section_type or SECTION_UNKNOWN,
                    start_index=next_index,
                )
            )
            next_index = len(chunks)
            group = []
        group.append(page)
        group_section_type = page.section_type

    if group:
        chunks.extend(
            _chunk_pdf_page_group(
                group,
                section_type=group_section_type or SECTION_UNKNOWN,
                start_index=next_index,
            )
        )

    return chunks


def _prepare_pdf_pages_for_chunking(pages: list[PDFPageText]) -> list[PdfPageForChunking]:
    prepared_pages: list[PdfPageForChunking] = []
    current_section_type = SECTION_UNKNOWN
    current_chapter_title: str | None = None
    current_section_title: str | None = None
    document_offset = 0

    for page in pages:
        if not page.text.strip():
            document_offset += len(page.text) + 2
            continue
        detected_section_type = classify_pdf_section_type(page.text)
        section_type = _resolve_pdf_page_section_type(
            page.text,
            detected_section_type=detected_section_type,
            current_section_type=current_section_type,
        )
        if section_type != SECTION_UNKNOWN:
            current_section_type = section_type
        heading_context = detect_pdf_heading_context(page.text)
        if section_type == SECTION_BODY:
            if heading_context.chapter_title:
                current_chapter_title = heading_context.chapter_title
            if heading_context.section_title:
                current_section_title = heading_context.section_title
        prepared_pages.append(
            PdfPageForChunking(
                page_number=page.page_number,
                text=page.text,
                section_type=section_type,
                char_start=document_offset,
                char_end=document_offset + len(page.text),
                chapter_title=current_chapter_title if section_type == SECTION_BODY else None,
                section_title=current_section_title if section_type == SECTION_BODY else None,
            )
        )
        document_offset += len(page.text) + 2

    return prepared_pages


def _chunk_pdf_page_group(
    pages: list[PdfPageForChunking],
    *,
    section_type: str,
    start_index: int,
    config: PdfChunkingConfig = PdfChunkingConfig(),
) -> list[IndexChunk]:
    if not pages:
        return []

    combined_text_parts: list[str] = []
    page_spans: list[PageSpan] = []
    offset = 0
    for page_index, page in enumerate(pages):
        if page_index > 0:
            combined_text_parts.append("\n\n")
            offset += 2
        start = offset
        combined_text_parts.append(page.text)
        offset += len(page.text)
        page_spans.append(
            PageSpan(
                page_number=page.page_number,
                start=start,
                end=offset,
                chapter_title=page.chapter_title,
                section_title=page.section_title,
            )
        )

    combined_text = "".join(combined_text_parts)
    base_offset = pages[0].char_start
    chunks: list[IndexChunk] = []
    for local_index, (raw_start, raw_end) in enumerate(
        _build_readable_chunk_spans(combined_text, config)
    ):
        start, end, content = _trim_chunk_span(combined_text, raw_start, raw_end)
        if not content:
            continue
        intersecting_pages = _page_spans_for_chunk(page_spans, start, end)
        page_numbers = [span.page_number for span in intersecting_pages]
        chapter_title, section_title = _heading_context_for_chunk(intersecting_pages)
        chunks.append(
            IndexChunk(
                index=start_index + local_index,
                content=content,
                char_start=base_offset + start,
                char_end=base_offset + end,
                page_start=min(page_numbers) if page_numbers else None,
                page_end=max(page_numbers) if page_numbers else None,
                section_type=section_type,
                chapter_title=chapter_title,
                section_title=section_title,
            )
        )

    return chunks


def _build_readable_chunk_spans(
    text: str, config: PdfChunkingConfig
) -> list[tuple[int, int]]:
    if config.chunk_size_chars <= 0:
        raise ValueError("chunk_size_chars must be positive")
    if config.chunk_overlap_chars < 0:
        raise ValueError("chunk_overlap_chars must be non-negative")
    if config.chunk_overlap_chars >= config.chunk_size_chars:
        raise ValueError("chunk_overlap_chars must be smaller than chunk_size_chars")
    if config.min_chunk_chars < 0:
        raise ValueError("min_chunk_chars must be non-negative")

    length = len(text)
    if length == 0:
        return []
    if length <= config.chunk_size_chars:
        return [(0, length)]

    spans: list[tuple[int, int]] = []
    start = 0
    while start < length:
        target_end = min(start + config.chunk_size_chars, length)
        if 0 < length - target_end < config.min_chunk_chars:
            target_end = length
        end = _adjust_chunk_end(text, start, target_end, config.min_chunk_chars)
        if end <= start:
            end = target_end
        spans.append((start, end))
        if end >= length:
            break

        next_start = max(0, end - config.chunk_overlap_chars)
        next_start = _adjust_chunk_start(text, next_start)
        if next_start <= start:
            next_start = min(start + config.chunk_size_chars - config.chunk_overlap_chars, length)
        start = next_start

    return spans


def _adjust_chunk_end(text: str, start: int, target_end: int, min_chunk_chars: int) -> int:
    if target_end >= len(text):
        return len(text)

    earliest = max(start + min_chunk_chars, target_end - 500)
    if earliest >= target_end:
        return target_end

    window = text[earliest:target_end]
    for boundary in ("\n\n", ". ", "? ", "! "):
        position = window.rfind(boundary)
        if position != -1:
            return earliest + position + len(boundary)
    return target_end


def _adjust_chunk_start(text: str, target_start: int) -> int:
    if target_start <= 0 or target_start >= len(text):
        return target_start
    if text[target_start - 1].isspace() or text[target_start].isspace():
        return target_start

    search_end = min(len(text), target_start + 80)
    for index in range(target_start, search_end):
        if text[index].isspace():
            return index + 1
    return target_start


def _trim_chunk_span(text: str, start: int, end: int) -> tuple[int, int, str]:
    content = text[start:end]
    leading_whitespace = len(content) - len(content.lstrip())
    trailing_whitespace = len(content) - len(content.rstrip())
    trimmed_start = start + leading_whitespace
    trimmed_end = end - trailing_whitespace
    return trimmed_start, trimmed_end, text[trimmed_start:trimmed_end]


def _page_spans_for_chunk(
    page_spans: list[PageSpan], start: int, end: int
) -> list[PageSpan]:
    return [
        span
        for span in page_spans
        if max(start, span.start) < min(end, span.end)
    ]


def _heading_context_for_chunk(page_spans: list[PageSpan]) -> tuple[str | None, str | None]:
    chapter_title = next(
        (span.chapter_title for span in page_spans if span.chapter_title),
        None,
    )
    section_title = next(
        (span.section_title for span in page_spans if span.section_title),
        None,
    )
    return chapter_title, section_title


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


def detect_pdf_heading_context(text: str) -> PdfHeadingContext:
    lines = [" ".join(line.strip().split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    chapter_title: str | None = None
    section_title: str | None = None

    for line in lines[:8]:
        line = _strip_trailing_page_number(line)
        chapter_match = re.match(r"^(Chapter\s+[IVXLCDM]+\s+.{3,80})$", line)
        if chapter_match:
            chapter_title = chapter_match.group(1)
            continue

        header_match = re.match(
            r"^\d+\s+([IVXLCDM]+)\s+(.{3,60}?)\s+(\d+)\s+(.{3,100})$",
            line,
        )
        if header_match:
            chapter_title = f"{header_match.group(1)} {header_match.group(2).strip()}"
            section_title = (
                f"{header_match.group(1)}.{header_match.group(3)} "
                f"{_strip_trailing_page_number(header_match.group(4).strip())}"
            )
            continue

        simple_header_match = re.match(r"^\d+\s+([IVXLCDM]+)\s+(.{3,80})$", line)
        if simple_header_match:
            chapter_title = (
                f"{simple_header_match.group(1)} "
                f"{_strip_trailing_page_number(simple_header_match.group(2).strip())}"
            )
            continue

        section_match = re.match(r"^([IVXLCDM]+\.\d+)\s+(.{3,100})$", line)
        if section_match:
            section_title = (
                f"{section_match.group(1)} "
                f"{_strip_trailing_page_number(section_match.group(2).strip())}"
            )

    return PdfHeadingContext(
        chapter_title=chapter_title,
        section_title=section_title,
    )


def _strip_trailing_page_number(text: str) -> str:
    return re.sub(r"\s+\d+$", "", text).strip()


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
