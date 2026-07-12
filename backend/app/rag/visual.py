from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import Protocol, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.vector_search import SimilarChunkResult
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.pdf_processing import (
    DocumentPage,
    VisualIndexVersion,
    VisualPageEmbedding,
)
from app.observability.latency import current_latency_trace


class VisualPageEncoder(Protocol):
    model_name: str
    dimension: int

    def encode_page(self, image_bytes: bytes) -> list[list[float]]:
        """Return page token vectors for late interaction."""

    def encode_query(self, query: str) -> list[list[float]]:
        """Return query token vectors in the visual model space."""


@dataclass(frozen=True)
class VisualPageCandidate:
    document_id: uuid.UUID
    document_page_id: uuid.UUID
    page_number: int
    score: float
    visual_index_version_id: uuid.UUID


class VisualEncoderRegistry:
    """Process-local experiment adapter; no model is downloaded automatically."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._encoder: VisualPageEncoder | None = None

    def set(self, encoder: VisualPageEncoder | None) -> None:
        with self._lock:
            self._encoder = encoder

    def get(self) -> VisualPageEncoder | None:
        with self._lock:
            return self._encoder


visual_encoder_registry = VisualEncoderRegistry()


class DeterministicVisualEncoder:
    """Fixture/smoke encoder, explicitly not a production multimodal model."""

    model_name = "mock-colpali"

    def __init__(self, dimension: int = 16) -> None:
        self.dimension = dimension

    def encode_page(self, image_bytes: bytes) -> list[list[float]]:
        return [self._vector(image_bytes)]

    def encode_query(self, query: str) -> list[list[float]]:
        return [self._vector(query.encode("utf-8"))]

    def _vector(self, value: bytes) -> list[float]:
        digest = hashlib.sha256(value).digest()
        vector = [
            ((digest[index % len(digest)] / 255) * 2) - 1
            for index in range(self.dimension)
        ]
        norm = math.sqrt(sum(item * item for item in vector)) or 1
        return [item / norm for item in vector]


def build_visual_index(
    session: Session,
    *,
    processing_version_id: uuid.UUID,
    rendered_pages: dict[uuid.UUID, bytes],
    encoder: VisualPageEncoder,
) -> VisualIndexVersion:
    """Build an isolated experimental page index from caller-rendered images."""
    started = perf_counter()
    version = VisualIndexVersion(
        processing_version_id=processing_version_id,
        model=encoder.model_name,
        dimension=encoder.dimension,
        index_format="late_interaction_json",
        status="building",
    )
    session.add(version)
    session.flush()
    pages = (
        session.execute(
            select(DocumentPage).where(
                DocumentPage.processing_version_id == processing_version_id
            )
        )
        .scalars()
        .all()
    )
    total_storage = 0
    try:
        indexed_page_count = 0
        for page in pages:
            image = rendered_pages.get(page.id)
            if image is None:
                continue
            vectors = encoder.encode_page(image)
            _validate_vectors(vectors, encoder.dimension)
            serialized = json.dumps(vectors, separators=(",", ":")).encode("utf-8")
            total_storage += len(serialized)
            session.add(
                VisualPageEmbedding(
                    visual_index_version_id=version.id,
                    document_page_id=page.id,
                    page_version=page.page_checksum,
                    embedding=vectors,
                    storage_bytes=len(serialized),
                )
            )
            indexed_page_count += 1
        version.page_count = indexed_page_count
        version.storage_bytes = total_storage
        version.status = "ready"
        session.flush()
        return version
    except Exception:
        version.status = "failed"
        session.flush()
        raise
    finally:
        _record("visual_index", started)


def activate_visual_index(
    session: Session, version_id: uuid.UUID
) -> VisualIndexVersion:
    version = session.get(VisualIndexVersion, version_id)
    if version is None or version.status not in {"ready", "active"}:
        raise ValueError("Visual index must be ready before activation")
    for active in session.execute(
        select(VisualIndexVersion).where(
            VisualIndexVersion.processing_version_id == version.processing_version_id,
            VisualIndexVersion.is_active.is_(True),
        )
    ).scalars():
        active.is_active = False
        active.status = "ready"
    version.is_active = True
    version.status = "active"
    session.flush()
    return version


def render_pdf_pages(
    path: Path,
    pages: Sequence[DocumentPage],
    *,
    dpi: int = 144,
) -> dict[uuid.UUID, bytes]:
    """Render selected pages for an explicitly enabled visual experiment."""
    if dpi < 72 or dpi > 300:
        raise ValueError("Visual page rendering DPI must be between 72 and 300")
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - dependency validation
        raise RuntimeError("PyMuPDF is required for visual page rendering") from exc
    document = fitz.open(path)
    rendered: dict[uuid.UUID, bytes] = {}
    try:
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        for page in pages:
            if page.page_number < 1 or page.page_number > document.page_count:
                raise ValueError("Document page is outside the source PDF")
            pixmap = document.load_page(page.page_number - 1).get_pixmap(
                matrix=matrix,
                alpha=False,
            )
            rendered[page.id] = pixmap.tobytes("png")
    finally:
        document.close()
    return rendered


def search_visual_pages(
    session: Session,
    *,
    question: str,
    document_ids: Sequence[uuid.UUID],
    limit: int,
    encoder: VisualPageEncoder,
) -> list[VisualPageCandidate]:
    started = perf_counter()
    query_vectors = encoder.encode_query(question)
    _validate_vectors(query_vectors, encoder.dimension)
    rows = session.execute(
        select(VisualPageEmbedding, VisualIndexVersion, DocumentPage)
        .join(
            VisualIndexVersion,
            VisualIndexVersion.id == VisualPageEmbedding.visual_index_version_id,
        )
        .join(DocumentPage, DocumentPage.id == VisualPageEmbedding.document_page_id)
        .join(Document, Document.id == DocumentPage.document_id)
        .where(DocumentPage.document_id.in_(list(document_ids)))
        .where(
            Document.active_processing_version_id == DocumentPage.processing_version_id
        )
        .where(VisualIndexVersion.is_active.is_(True))
        .where(VisualIndexVersion.model == encoder.model_name)
        .where(VisualIndexVersion.dimension == encoder.dimension)
    ).all()
    candidates = [
        VisualPageCandidate(
            page.document_id,
            page.id,
            page.page_number,
            late_interaction_score(query_vectors, stored.embedding),
            version.id,
        )
        for stored, version, page in rows
        if stored.page_version == page.page_checksum
    ]
    candidates.sort(key=lambda item: (-item.score, item.page_number))
    _record("visual_search", started)
    return candidates[:limit]


def visual_candidates_to_chunks(
    session: Session, candidates: Sequence[VisualPageCandidate]
) -> list[SimilarChunkResult]:
    output: list[SimilarChunkResult] = []
    seen: set[uuid.UUID] = set()
    for candidate in candidates:
        chunk = (
            session.execute(
                select(DocumentChunk)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(DocumentChunk.document_id == candidate.document_id)
                .where(
                    DocumentChunk.processing_version_id
                    == Document.active_processing_version_id
                )
                .where(DocumentChunk.page_start <= candidate.page_number)
                .where(DocumentChunk.page_end >= candidate.page_number)
                .order_by(DocumentChunk.chunk_index)
            )
            .scalars()
            .first()
        )
        if chunk is None or chunk.id in seen:
            continue
        seen.add(chunk.id)
        output.append(
            SimilarChunkResult(
                chunk.id,
                chunk.document_id,
                chunk.chunk_index,
                chunk.content,
                chunk.char_start,
                chunk.char_end,
                distance=1.0 / (1.0 + max(0.0, candidate.score)),
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_type=chunk.section_type,
                chapter_title=chunk.chapter_title,
                section_title=chunk.section_title,
                parent_chunk_id=chunk.parent_chunk_id,
                element_type=chunk.element_type,
                extraction_method=chunk.extraction_method,
                ocr_confidence=chunk.ocr_confidence,
                section_path=tuple(chunk.section_path or ()),
                bounding_boxes=tuple(chunk.bounding_boxes or ()),
            )
        )
    return output


def late_interaction_score(
    query_vectors: Sequence[Sequence[float]], page_vectors: Sequence[Sequence[float]]
) -> float:
    if not query_vectors or not page_vectors:
        return 0.0
    return sum(
        max(_dot(query, page) for page in page_vectors) for query in query_vectors
    ) / len(query_vectors)


def _validate_vectors(vectors: Sequence[Sequence[float]], dimension: int) -> None:
    if not vectors or any(len(vector) != dimension for vector in vectors):
        raise ValueError("Visual vectors do not match the index dimension")


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Visual query and page dimensions do not match")
    return sum(a * b for a, b in zip(left, right))


def _record(stage: str, started: float) -> None:
    trace = current_latency_trace()
    if trace is not None:
        trace.record(stage, (perf_counter() - started) * 1000)
