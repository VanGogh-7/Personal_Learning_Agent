from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.document import Document
from app.models.pdf_processing import (
    DocumentPage,
    PdfProcessingVersion,
    VisualPageEmbedding,
)
from app.observability.latency import AgentLatencyTrace, latency_trace_context
from app.rag.visual import (
    DeterministicVisualEncoder,
    activate_visual_index,
    build_visual_index,
    render_pdf_pages,
    search_visual_pages,
)
from tests.pdf_fixtures import make_pdf_bytes


def _fixture(
    session: Session,
) -> tuple[Document, PdfProcessingVersion, list[DocumentPage]]:
    document = Document(title="Visual math", file_type="pdf")
    session.add(document)
    session.flush()
    processing = PdfProcessingVersion(
        document_id=document.id,
        status="ready",
        pdf_type="scanned",
        detection_evidence={},
        parser_name="fixture",
        parser_version="1",
        is_active=True,
    )
    session.add(processing)
    session.flush()
    document.active_processing_version_id = processing.id
    pages = [
        DocumentPage(
            document_id=document.id,
            processing_version_id=processing.id,
            page_number=index,
            text=text,
            extraction_method="ocr",
            source_type="scanned",
            language="eng",
            ocr_confidence=0.8,
            bounding_boxes=[],
            text_character_count=len(text),
            image_coverage_ratio=1,
            width_points=612,
            height_points=792,
            page_checksum=f"checksum-{index}",
        )
        for index, text in enumerate(("formula", "diagram"), start=1)
    ]
    session.add_all(pages)
    session.flush()
    return document, processing, pages


def test_visual_index_is_versioned_and_dimension_isolated() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    document, processing, pages = _fixture(session)
    encoder = DeterministicVisualEncoder(dimension=8)
    trace = AgentLatencyTrace()
    with latency_trace_context(trace):
        version = build_visual_index(
            session,
            processing_version_id=processing.id,
            rendered_pages={pages[0].id: b"formula", pages[1].id: b"diagram"},
            encoder=encoder,
        )
        activate_visual_index(session, version.id)
        candidates = search_visual_pages(
            session,
            question="formula",
            document_ids=[document.id],
            limit=2,
            encoder=encoder,
        )
        wrong_space = search_visual_pages(
            session,
            question="formula",
            document_ids=[document.id],
            limit=2,
            encoder=DeterministicVisualEncoder(dimension=16),
        )

    assert candidates[0].page_number == 1
    assert wrong_space == []
    stored = session.execute(select(VisualPageEmbedding)).scalars().all()
    assert all(len(item.embedding[0]) == 8 for item in stored)
    assert all(item.page_version.startswith("checksum-") for item in stored)
    assert {"visual_index", "visual_search"} <= set(trace.timings_ms)
    session.close()


def test_page_checksum_change_invalidates_visual_candidate() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    document, processing, pages = _fixture(session)
    encoder = DeterministicVisualEncoder(dimension=8)
    version = build_visual_index(
        session,
        processing_version_id=processing.id,
        rendered_pages={pages[0].id: b"formula"},
        encoder=encoder,
    )
    activate_visual_index(session, version.id)
    pages[0].page_checksum = "new-page-version"
    session.flush()

    assert (
        search_visual_pages(
            session,
            question="formula",
            document_ids=[document.id],
            limit=5,
            encoder=encoder,
        )
        == []
    )
    session.close()


def test_render_pdf_pages_is_explicit_and_bounded(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    _, _, pages = _fixture(session)
    path = tmp_path / "visual.pdf"
    path.write_bytes(make_pdf_bytes(["formula page", "diagram page"]))

    rendered = render_pdf_pages(path, pages, dpi=96)

    assert set(rendered) == {page.id for page in pages}
    assert all(value.startswith(b"\x89PNG") for value in rendered.values())
    session.close()
