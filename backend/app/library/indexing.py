import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.embeddings.base import EmbeddingProvider
from app.embeddings.providers import get_embedding_provider
from app.ingestion.chunking import chunk_text
from app.ingestion.pdf import PDFExtractionError, PDFPageText, extract_pdf_pages
from app.ingestion.legacy_pdf import (
    LegacyPDFError,
    OCRBackend,
    OCRRetryableError,
    ProcessedPDF,
    ProcessedPDFPage,
    classify_layout_element,
    process_pdf,
)
from app.core.config import BACKEND_DIR, get_settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.embedding_index import ChunkEmbedding
from app.models.pdf_processing import DocumentPage, PdfProcessingVersion
from app.models.library_item import LibraryItem
from app.settings.runtime import current_embedding_index_version_id

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
    element_type: str = "paragraph"
    section_path: tuple[str, ...] = ()
    bounding_boxes: tuple[dict, ...] = ()
    extraction_method: str = "text"
    ocr_confidence: float | None = None


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
    ocr_backend: OCRBackend | None = None,
) -> LibraryIndexResult | None:
    item = session.get(LibraryItem, item_id)
    if item is None:
        return None

    processing_version: PdfProcessingVersion | None = None
    text_index_started: float | None = None
    try:
        item.status = "indexing"
        session.flush()

        path = _validate_file_path(item.file_path)
        file_type = _detect_supported_file_type(item.file_type, path)
        document = _get_or_create_document(session, item, path, file_type)
        document.title = item.title
        document.file_path = str(path)
        document.file_type = file_type
        session.flush()

        processed_pdf: ProcessedPDF | None = None
        if file_type == "pdf":
            settings = get_settings()
            processing_version = PdfProcessingVersion(
                document_id=document.id,
                status="processing",
                parser_name="pending",
                parser_version="pending",
                pdf_type="extraction_failed",
                detection_evidence={},
                text_index_version_id=(
                    uuid.UUID(current_embedding_index_version_id())
                    if current_embedding_index_version_id()
                    else None
                ),
            )
            session.add(processing_version)
            session.flush()
            try:
                output_dir = Path(settings.pdf_ocr_output_dir)
                if not output_dir.is_absolute():
                    output_dir = BACKEND_DIR / output_dir
                processed_pdf = process_pdf(
                    path,
                    ocr_enabled=settings.pdf_ocr_enabled,
                    ocr_backend=ocr_backend,
                    language=settings.pdf_ocr_language,
                    searchable_output_dir=output_dir,
                )
            except OCRRetryableError as exc:
                processing_version.status = "failed"
                processing_version.retryable = True
                processing_version.error_category = "ocr_unavailable"
                item.status = "index_failed"
                session.flush()
                _increment_extraction_failure()
                raise LibraryIndexingError(str(exc)) from exc
            except LegacyPDFError as exc:
                processing_version.status = "failed"
                processing_version.retryable = True
                processing_version.error_category = "extraction_failed"
                item.status = "index_failed"
                session.flush()
                _increment_extraction_failure()
                raise LibraryIndexingError(str(exc)) from exc
            processing_version.pdf_type = processed_pdf.classification.pdf_type
            processing_version.detection_evidence = (
                processed_pdf.classification.evidence()
            )
            processing_version.parser_name = processed_pdf.parser_name
            processing_version.parser_version = processed_pdf.parser_version
            processing_version.ocr_engine = processed_pdf.ocr_engine
            processing_version.ocr_version = processed_pdf.ocr_version
            _persist_processed_pages(
                session, document.id, processing_version.id, processed_pdf
            )
            pages = [
                PDFPageText(
                    page_number=page.page_number,
                    text=_clean_text_for_storage(page.text),
                )
                for page in processed_pdf.pages
            ]
            chunks = _enrich_pdf_chunks(_chunk_pdf_pages(pages), processed_pdf.pages)
            content_hash = _content_hash(
                "\n\n".join(f"Page {page.page_number}\n{page.text}" for page in pages)
            )
        else:
            chunks, content_hash = _prepare_index_chunks(path, file_type)
            session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
            )
        document.content_hash = content_hash
        text_index_started = perf_counter()
        provider = embedding_provider or get_embedding_provider()
        embeddings = provider.embed_texts([chunk.content for chunk in chunks])

        index_version_id = current_embedding_index_version_id()
        stored_chunks: list[DocumentChunk] = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            stored = DocumentChunk(
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
                processing_version_id=processing_version.id
                if processing_version
                else None,
                element_type=chunk.element_type,
                section_path=list(chunk.section_path),
                bounding_boxes=list(chunk.bounding_boxes),
                extraction_method=chunk.extraction_method,
                ocr_confidence=chunk.ocr_confidence,
                embedding=embedding if index_version_id is None else None,
            )
            session.add(stored)
            stored_chunks.append(stored)
        session.flush()
        if index_version_id is not None:
            for stored, embedding in zip(stored_chunks, embeddings, strict=True):
                session.add(
                    ChunkEmbedding(
                        chunk_id=stored.id,
                        index_version_id=uuid.UUID(index_version_id),
                        embedding=embedding,
                    )
                )

        if processing_version is not None:
            _assign_parent_chunks(stored_chunks)
            for previous in session.execute(
                select(PdfProcessingVersion)
                .where(PdfProcessingVersion.document_id == document.id)
                .where(PdfProcessingVersion.id != processing_version.id)
                .where(PdfProcessingVersion.is_active.is_(True))
            ).scalars():
                previous.is_active = False
            processing_version.status = "ready"
            processing_version.is_active = True
            processing_version.completed_at = datetime.now(UTC)
            document.active_processing_version_id = processing_version.id

        item.status = "indexed"
        session.flush()
        _record_text_index(text_index_started)
        text_index_started = None

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
        if processing_version is not None and processing_version.status != "ready":
            processing_version.status = "failed"
            processing_version.retryable = True
            processing_version.error_category = (
                processing_version.error_category or "indexing_failed"
            )
        session.flush()
        if text_index_started is not None:
            _record_text_index(text_index_started)
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


def _persist_processed_pages(
    session: Session,
    document_id: uuid.UUID,
    processing_version_id: uuid.UUID,
    processed: ProcessedPDF,
) -> None:
    for page in processed.pages:
        session.add(
            DocumentPage(
                document_id=document_id,
                processing_version_id=processing_version_id,
                page_number=page.page_number,
                text=page.text,
                extraction_method=page.extraction_method,
                source_type=page.source_type,
                language=page.language,
                ocr_confidence=page.ocr_confidence,
                bounding_boxes=[box.as_dict() for box in page.bounding_boxes[:512]],
                text_character_count=len(page.text),
                image_coverage_ratio=page.image_coverage_ratio,
                width_points=page.width_points,
                height_points=page.height_points,
                page_checksum=page.checksum,
            )
        )
    session.flush()


def _enrich_pdf_chunks(
    chunks: list[IndexChunk], pages: tuple[ProcessedPDFPage, ...]
) -> list[IndexChunk]:
    pages_by_number = {page.page_number: page for page in pages}
    output: list[IndexChunk] = []
    for chunk in chunks:
        intersecting = [
            pages_by_number[page_number]
            for page_number in range(chunk.page_start or 0, (chunk.page_end or 0) + 1)
            if page_number in pages_by_number
        ]
        boxes = tuple(
            {"page_number": page.page_number, **box.as_dict()}
            for page in intersecting
            for box in page.bounding_boxes[:64]
        )
        confidences = [
            page.ocr_confidence
            for page in intersecting
            if page.ocr_confidence is not None
        ]
        methods = {page.extraction_method for page in intersecting}
        first_line = next(
            (line.strip() for line in chunk.content.splitlines() if line.strip()),
            chunk.content[:200],
        )
        element_type = _element_type_for_chunk(
            chunk.section_type,
            first_line,
            {
                element.element_type
                for page in intersecting
                for element in page.elements
            },
        )
        output.append(
            IndexChunk(
                index=chunk.index,
                content=chunk.content,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_type=chunk.section_type,
                chapter_title=chunk.chapter_title,
                section_title=chunk.section_title,
                element_type=element_type,
                section_path=tuple(
                    value
                    for value in (chunk.chapter_title, chunk.section_title)
                    if value
                ),
                bounding_boxes=boxes,
                extraction_method=(
                    next(iter(methods))
                    if len(methods) == 1
                    else "mixed"
                    if methods
                    else "text"
                ),
                ocr_confidence=(sum(confidences) / len(confidences))
                if confidences
                else None,
            )
        )
    return output


def _element_type_for_chunk(
    section_type: str,
    first_line: str,
    page_element_types: set[str] | None = None,
) -> str:
    if section_type in {SECTION_CONTENTS, SECTION_INDEX, SECTION_BIBLIOGRAPHY}:
        return section_type
    available = page_element_types or set()
    for element_type in (
        "theorem",
        "lemma",
        "definition",
        "proof",
        "formula",
        "figure_caption",
        "table",
    ):
        if element_type in available:
            return element_type
    return classify_layout_element(first_line)


def _assign_parent_chunks(chunks: list[DocumentChunk]) -> None:
    parents: dict[tuple[str, str | None, str | None], uuid.UUID] = {}
    for chunk in chunks:
        key = (chunk.section_type, chunk.chapter_title, chunk.section_title)
        parent_id = parents.get(key)
        if parent_id is None:
            parents[key] = chunk.id
        elif parent_id != chunk.id:
            chunk.parent_chunk_id = parent_id


def _increment_extraction_failure() -> None:
    from app.observability.latency import current_latency_trace

    trace = current_latency_trace()
    if trace is not None:
        trace.increment("extraction_failure_count")


def _record_text_index(started: float) -> None:
    from app.observability.latency import current_latency_trace

    trace = current_latency_trace()
    if trace is not None:
        trace.record("text_index", (perf_counter() - started) * 1000)


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
            PDFPageText(
                page_number=page.page_number, text=_clean_text_for_storage(page.text)
            )
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


def _prepare_pdf_pages_for_chunking(
    pages: list[PDFPageText],
) -> list[PdfPageForChunking]:
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
                chapter_title=current_chapter_title
                if section_type == SECTION_BODY
                else None,
                section_title=current_section_title
                if section_type == SECTION_BODY
                else None,
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
            next_start = min(
                start + config.chunk_size_chars - config.chunk_overlap_chars, length
            )
        start = next_start

    return spans


def _adjust_chunk_end(
    text: str, start: int, target_end: int, min_chunk_chars: int
) -> int:
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
    return [span for span in page_spans if max(start, span.start) < min(end, span.end)]


def _heading_context_for_chunk(
    page_spans: list[PageSpan],
) -> tuple[str | None, str | None]:
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
