from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.embeddings.base import EMBEDDING_DIMENSION
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.pdf_processing import PdfProcessingVersion
from app.observability.latency import AgentLatencyTrace, latency_trace_context
from app.rag.fusion import fuse_text_and_visual
from app.rag.hybrid import hybrid_search_chunks, keyword_search_chunks


def _chunk(
    document_id: uuid.UUID,
    processing_id: uuid.UUID,
    index: int,
    text: str,
    page: int,
    *,
    vector_value: float,
    section_type: str = "body",
    parent_chunk_id: uuid.UUID | None = None,
) -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        processing_version_id=processing_id,
        chunk_index=index,
        content=text,
        char_start=0,
        char_end=len(text),
        page_start=page,
        page_end=page,
        section_type=section_type,
        chapter_title="Closed Operators",
        section_title="Theorem 4.2" if page == 42 else None,
        parent_chunk_id=parent_chunk_id,
        element_type="theorem" if page == 42 else "paragraph",
        section_path=["Closed Operators"],
        bounding_boxes=[],
        extraction_method="ocr" if page == 42 else "pdf_text",
        ocr_confidence=0.88 if page == 42 else None,
        embedding=[vector_value] * EMBEDDING_DIMENSION,
    )


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_hybrid_exact_theorem_query_improves_dense_order_and_page_accuracy() -> None:
    session = _session()
    document = Document(title="Analysis", file_type="pdf")
    session.add(document)
    session.flush()
    version = PdfProcessingVersion(
        document_id=document.id,
        status="ready",
        pdf_type="scanned",
        detection_evidence={},
        parser_name="fixture",
        parser_version="1",
        is_active=True,
    )
    session.add(version)
    session.flush()
    document.active_processing_version_id = version.id
    distractor = _chunk(
        document.id,
        version.id,
        0,
        "General background on metric spaces.",
        7,
        vector_value=0,
    )
    exact = _chunk(
        document.id,
        version.id,
        1,
        "Theorem 4.2. The graph of T is closed if the limit condition holds.",
        42,
        vector_value=1,
    )
    session.add_all([distractor, exact])
    session.flush()

    trace = AgentLatencyTrace()
    with latency_trace_context(trace):
        results = hybrid_search_chunks(
            session,
            question="Theorem 4.2 closed graph",
            query_embedding=[0.0] * EMBEDDING_DIMENSION,
            document_ids=[document.id],
            limit=2,
        )

    assert results[0].chunk_id == exact.id
    assert results[0].page_start == 42
    assert {"dense_search", "keyword_search", "fusion", "rerank"} <= set(
        trace.timings_ms
    )
    session.close()


def test_keyword_search_handles_ocr_spelling_error_and_filters_index() -> None:
    session = _session()
    document = Document(title="Old text", file_type="pdf")
    session.add(document)
    session.flush()
    version = PdfProcessingVersion(
        document_id=document.id,
        status="ready",
        pdf_type="scanned",
        detection_evidence={},
        parser_name="fixture",
        parser_version="1",
        is_active=True,
    )
    session.add(version)
    session.flush()
    document.active_processing_version_id = version.id
    body = _chunk(
        document.id,
        version.id,
        0,
        "Every Banach spacc is a complete normed vector space.",
        10,
        vector_value=0,
    )
    index = _chunk(
        document.id,
        version.id,
        1,
        "Banach space, 10; compactness, 31",
        99,
        vector_value=0,
        section_type="index",
    )
    session.add_all([body, index])
    session.flush()

    results = keyword_search_chunks(
        session,
        question="Banach space",
        document_ids=[document.id],
        limit=5,
        exclude_section_types=("index",),
    )

    assert [result.chunk_id for result in results] == [body.id]
    session.close()


def test_active_processing_version_isolates_old_pdf_chunks() -> None:
    session = _session()
    document = Document(title="Versioned", file_type="pdf")
    session.add(document)
    session.flush()
    old = PdfProcessingVersion(
        document_id=document.id,
        status="ready",
        pdf_type="born_digital",
        detection_evidence={},
        parser_name="old",
        parser_version="1",
    )
    new = PdfProcessingVersion(
        document_id=document.id,
        status="ready",
        pdf_type="mixed",
        detection_evidence={},
        parser_name="new",
        parser_version="2",
        is_active=True,
    )
    session.add_all([old, new])
    session.flush()
    document.active_processing_version_id = new.id
    old_chunk = _chunk(
        document.id, old.id, 0, "Theorem 9.1 obsolete", 1, vector_value=0
    )
    new_chunk = _chunk(
        document.id, new.id, 0, "Theorem 9.1 corrected", 2, vector_value=0
    )
    session.add_all([old_chunk, new_chunk])
    session.flush()

    results = keyword_search_chunks(
        session,
        question="Theorem 9.1",
        document_ids=[document.id],
        limit=5,
        exclude_section_types=(),
    )

    assert [result.chunk_id for result in results] == [new_chunk.id]
    session.close()


def test_rank_fusion_deduplicates_text_and_visual_page() -> None:
    session = _session()
    document_id = uuid.uuid4()
    processing_id = uuid.uuid4()
    chunk = _chunk(document_id, processing_id, 0, "same page", 8, vector_value=0)
    other = _chunk(document_id, processing_id, 1, "visual page", 9, vector_value=0)
    from app.db.vector_search import SimilarChunkResult

    def result(value: DocumentChunk) -> SimilarChunkResult:
        return SimilarChunkResult(
            value.id,
            value.document_id,
            value.chunk_index,
            value.content,
            0,
            len(value.content),
            0.1,
            page_start=value.page_start,
            page_end=value.page_end,
        )

    fused = fuse_text_and_visual(
        [result(chunk)], [result(chunk), result(other)], limit=5
    )

    assert [(item.page_start, item.content) for item in fused] == [
        (8, "same page"),
        (9, "visual page"),
    ]
    session.close()
