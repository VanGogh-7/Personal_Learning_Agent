from __future__ import annotations

from pathlib import Path

import fitz
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.ingestion.legacy_pdf import (
    BoundingBox,
    OCRPageResult,
    OCRRetryableError,
    ProcessedPDFPage,
    PyMuPDFRuleLayoutParser,
    classify_layout_element,
    detect_pdf_type,
    process_pdf,
    generate_searchable_pdf,
)
from app.library.indexing import LibraryIndexingError, index_library_item
from app.library.service import create_library_item
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.pdf_processing import DocumentPage, PdfProcessingVersion
from app.observability.latency import AgentLatencyTrace, latency_trace_context
from tests.pdf_fixtures import make_pdf_bytes


class FakeOCR:
    name = "fixture-ocr"
    version = "1"

    def recognize_page(
        self, path: Path, page_number: int, language: str
    ) -> OCRPageResult:
        return OCRPageResult(
            text=f"Theorem 4.2 OCR result on page {page_number}.",
            confidence=0.91,
            bounding_boxes=(
                BoundingBox(
                    10,
                    20,
                    200,
                    50,
                    "Theorem 4.2",
                    0.91,
                    "ocr_pixels",
                ),
            ),
            language=language,
            engine=self.name,
            version=self.version,
        )


def _image_only_pdf(path: Path, *, with_text_page: bool = False) -> None:
    document = fitz.open()
    if with_text_page:
        page = document.new_page()
        page.insert_text(
            (72, 72),
            "Born digital explanatory text with enough characters for detection.",
        )
    page = document.new_page()
    pixmap = fitz.Pixmap(fitz.csRGB, (0, 0, 20, 20), False)
    pixmap.clear_with(245)
    page.insert_image(page.rect, stream=pixmap.tobytes("png"))
    document.save(path)
    document.close()


def test_pdf_type_detection_covers_born_digital_scanned_and_mixed(tmp_path) -> None:
    born = tmp_path / "born.pdf"
    born.write_bytes(
        make_pdf_bytes(["A born digital theorem statement with extractable text."])
    )
    scanned = tmp_path / "scanned.pdf"
    mixed = tmp_path / "mixed.pdf"
    _image_only_pdf(scanned)
    _image_only_pdf(mixed, with_text_page=True)

    assert detect_pdf_type(born).pdf_type == "born_digital"
    assert detect_pdf_type(scanned).pdf_type == "scanned"
    assert detect_pdf_type(mixed).pdf_type == "mixed"


def test_detection_evidence_excludes_page_text(tmp_path) -> None:
    path = tmp_path / "safe.pdf"
    path.write_bytes(
        make_pdf_bytes(["Private page text must not enter tracing evidence."])
    )

    evidence = detect_pdf_type(path).evidence()

    assert "Private page text" not in str(evidence)
    assert evidence["page_metrics"][0]["text_characters"] > 0


def test_scanned_pdf_uses_page_aware_mock_ocr_metadata(tmp_path) -> None:
    path = tmp_path / "scan.pdf"
    _image_only_pdf(path)

    trace = AgentLatencyTrace()
    with latency_trace_context(trace):
        processed = process_pdf(
            path,
            ocr_enabled=True,
            ocr_backend=FakeOCR(),
            language="eng",
        )

    assert processed.classification.pdf_type == "scanned"
    assert processed.ocr_engine == "fixture-ocr"
    assert processed.pages[0].extraction_method == "ocr"
    assert processed.pages[0].ocr_confidence == pytest.approx(0.91)
    assert processed.pages[0].bounding_boxes[0].text == "Theorem 4.2"
    assert processed.pages[0].elements[0].element_type == "theorem"
    assert {"pdf_type_detection", "ocr", "layout_parse"} <= set(trace.timings_ms)
    assert trace.counters["ocr_confidence"] == pytest.approx(0.91)


def test_scanned_pdf_without_available_backend_remains_retryable(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "scan.pdf"
    _image_only_pdf(path)
    monkeypatch.setattr("app.ingestion.legacy_pdf.shutil.which", lambda _: None)

    with pytest.raises(OCRRetryableError, match="unavailable"):
        process_pdf(path, ocr_enabled=True)


def test_searchable_pdf_reuses_valid_content_addressed_output(
    tmp_path, monkeypatch
) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-source")
    output_dir = tmp_path / "ocr"
    output_dir.mkdir()
    import hashlib

    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    existing = output_dir / f"scan-{digest}-searchable.pdf"
    existing.write_bytes(b"%PDF-existing")
    monkeypatch.setattr(
        "app.ingestion.legacy_pdf.subprocess.run",
        lambda *args, **kwargs: pytest.fail("OCRmyPDF must not rerun"),
    )

    assert generate_searchable_pdf(source, output_dir, "eng") == str(existing)


def test_layout_parser_filters_repeated_margins_and_classifies_math() -> None:
    pages = [
        ProcessedPDFPage(
            page_number=number,
            text=(
                "FUNCTIONAL ANALYSIS\n"
                f"Theorem 4.{number} Closed operators have closed graphs.\n"
                "Proof. Let x_n converge.\n"
                "f(x) = ∫ x² dx\n"
                f"{number}"
            ),
            extraction_method="pdf_text",
            source_type="born_digital",
            language=None,
            ocr_confidence=None,
            bounding_boxes=(),
            image_coverage_ratio=0,
            width_points=612,
            height_points=792,
        )
        for number in (1, 2, 3)
    ]

    parsed = PyMuPDFRuleLayoutParser().parse(pages)

    assert all("FUNCTIONAL ANALYSIS" not in page.text for page in parsed)
    assert all(page.text.splitlines()[-1] != str(page.page_number) for page in parsed)
    types = {element.element_type for element in parsed[0].elements}
    assert {"header", "footer", "theorem", "proof", "formula"} <= types
    assert (
        classify_layout_element("Definition 2.1 A Banach space is complete.")
        == "definition"
    )
    assert classify_layout_element("Figure 3. Commutative diagram") == "figure_caption"


def test_indexing_persists_ocr_page_metadata_and_active_version(tmp_path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    path = tmp_path / "scan.pdf"
    _image_only_pdf(path)
    item = create_library_item(
        session, title="Scanned Analysis", file_path=str(path), file_type="pdf"
    )

    trace = AgentLatencyTrace()
    with latency_trace_context(trace):
        result = index_library_item(session, item.item_id, ocr_backend=FakeOCR())

    assert result is not None
    document = session.get(Document, result.document_id)
    assert document is not None and document.active_processing_version_id is not None
    processing = session.get(
        PdfProcessingVersion, document.active_processing_version_id
    )
    assert processing is not None
    assert (processing.status, processing.pdf_type, processing.is_active) == (
        "ready",
        "scanned",
        True,
    )
    page = session.execute(select(DocumentPage)).scalar_one()
    assert page.extraction_method == "ocr"
    assert page.ocr_confidence == pytest.approx(0.91)
    assert page.bounding_boxes[0]["text"] == "Theorem 4.2"
    assert page.bounding_boxes[0]["coordinate_space"] == "ocr_pixels"
    chunk = session.execute(select(DocumentChunk)).scalar_one()
    assert chunk.element_type == "theorem"
    assert chunk.page_start == 1
    assert "text_index" in trace.timings_ms
    session.close()


def test_indexing_ocr_failure_keeps_retryable_version_and_original(tmp_path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    path = tmp_path / "scan.pdf"
    _image_only_pdf(path)
    original = path.read_bytes()
    item = create_library_item(
        session, title="Scanned Analysis", file_path=str(path), file_type="pdf"
    )

    class FailingOCR(FakeOCR):
        def recognize_page(
            self, path: Path, page_number: int, language: str
        ) -> OCRPageResult:
            raise OCRRetryableError("fixture OCR failure")

    with pytest.raises(LibraryIndexingError, match="fixture OCR failure"):
        index_library_item(session, item.item_id, ocr_backend=FailingOCR())

    processing = session.execute(select(PdfProcessingVersion)).scalar_one()
    assert processing.status == "failed"
    assert processing.retryable is True
    assert path.read_bytes() == original
    session.close()
