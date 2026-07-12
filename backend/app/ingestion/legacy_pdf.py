from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from time import perf_counter
from typing import Literal, Protocol

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.observability.latency import current_latency_trace

PDFType = Literal["born_digital", "scanned", "mixed", "damaged"]
ElementType = Literal[
    "title",
    "heading",
    "paragraph",
    "definition",
    "theorem",
    "lemma",
    "proof",
    "formula",
    "figure_caption",
    "table",
    "footnote",
    "header",
    "footer",
    "bibliography",
    "index",
    "contents",
]


class LegacyPDFError(ValueError):
    """Base error for classification/OCR/layout processing."""


class OCRRetryableError(LegacyPDFError):
    """OCR could not run without changing the original document."""


@dataclass(frozen=True)
class BoundingBox:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str = ""
    confidence: float | None = None
    coordinate_space: str = "pdf_points"

    def as_dict(self) -> dict[str, float | str | None]:
        return {
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
            "text": self.text[:500],
            "confidence": self.confidence,
            "coordinate_space": self.coordinate_space,
        }


@dataclass(frozen=True)
class PageDetectionMetrics:
    page_number: int
    text: str
    text_characters: int
    printable_ratio: float
    image_count: int
    image_coverage_ratio: float
    font_count: int
    width_points: float
    height_points: float
    extraction_error: bool = False
    bounding_boxes: tuple[BoundingBox, ...] = ()

    @property
    def has_usable_text(self) -> bool:
        # Short theorem statements and title pages are valid born-digital text.
        return self.text_characters >= 20 and self.printable_ratio >= 0.75


@dataclass(frozen=True)
class PDFClassification:
    pdf_type: PDFType
    confidence: float
    page_count: int
    text_page_ratio: float
    image_page_ratio: float
    empty_page_ratio: float
    extraction_error_count: int
    likely_ocr_layer: bool
    pages: tuple[PageDetectionMetrics, ...]

    def evidence(self) -> dict[str, object]:
        return {
            "confidence": round(self.confidence, 4),
            "page_count": self.page_count,
            "text_page_ratio": round(self.text_page_ratio, 4),
            "image_page_ratio": round(self.image_page_ratio, 4),
            "empty_page_ratio": round(self.empty_page_ratio, 4),
            "extraction_error_count": self.extraction_error_count,
            "likely_ocr_layer": self.likely_ocr_layer,
            "page_metrics": [
                {
                    "page_number": page.page_number,
                    "text_characters": page.text_characters,
                    "printable_ratio": round(page.printable_ratio, 4),
                    "image_count": page.image_count,
                    "image_coverage_ratio": round(page.image_coverage_ratio, 4),
                    "font_count": page.font_count,
                    "extraction_error": page.extraction_error,
                }
                for page in self.pages
            ],
        }


@dataclass(frozen=True)
class OCRPageResult:
    text: str
    confidence: float | None
    bounding_boxes: tuple[BoundingBox, ...]
    language: str
    engine: str
    version: str


class OCRBackend(Protocol):
    name: str
    version: str

    def recognize_page(
        self, path: Path, page_number: int, language: str
    ) -> OCRPageResult:
        """Recognize one 1-based page without modifying the source PDF."""


@dataclass(frozen=True)
class LayoutElement:
    element_type: ElementType
    text: str
    bbox: BoundingBox | None = None


@dataclass(frozen=True)
class ProcessedPDFPage:
    page_number: int
    text: str
    extraction_method: str
    source_type: str
    language: str | None
    ocr_confidence: float | None
    bounding_boxes: tuple[BoundingBox, ...]
    image_coverage_ratio: float
    width_points: float
    height_points: float
    elements: tuple[LayoutElement, ...] = ()

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProcessedPDF:
    classification: PDFClassification
    pages: tuple[ProcessedPDFPage, ...]
    parser_name: str
    parser_version: str
    ocr_engine: str | None = None
    ocr_version: str | None = None
    searchable_pdf_path: str | None = None
    warnings: tuple[str, ...] = ()


def detect_pdf_type(path: Path) -> PDFClassification:
    started = perf_counter()
    try:
        pages = tuple(_inspect_pages(path))
        if not pages:
            return PDFClassification("damaged", 1, 0, 0, 0, 1, 1, False, ())
        count = len(pages)
        text_pages = sum(page.has_usable_text for page in pages)
        image_pages = sum(
            page.image_count > 0 or page.image_coverage_ratio >= 0.25 for page in pages
        )
        font_pages = sum(page.font_count > 0 for page in pages)
        empty_pages = sum(page.text_characters < 20 for page in pages)
        failures = sum(page.extraction_error for page in pages)
        text_ratio = text_pages / count
        image_ratio = image_pages / count
        empty_ratio = empty_pages / count
        likely_ocr = text_ratio >= 0.6 and image_ratio >= 0.6
        if failures == count:
            pdf_type: PDFType = "damaged"
            confidence = 1.0
        elif (
            text_ratio >= 0.8
            or (text_ratio >= 0.6 and image_ratio < 0.5)
            or (
                image_ratio < 0.2
                and font_pages > 0
                and any(page.text_characters > 0 for page in pages)
            )
        ):
            pdf_type = "born_digital"
            confidence = min(1.0, 0.75 + text_ratio * 0.25)
        elif text_ratio <= 0.2 and image_ratio >= 0.5:
            pdf_type = "scanned"
            confidence = min(1.0, 0.6 + image_ratio * 0.3 + empty_ratio * 0.1)
        else:
            pdf_type = "mixed"
            confidence = 0.7 + min(0.25, abs(text_ratio - 0.5))
        return PDFClassification(
            pdf_type,
            confidence,
            count,
            text_ratio,
            image_ratio,
            empty_ratio,
            failures,
            likely_ocr,
            pages,
        )
    finally:
        trace = current_latency_trace()
        if trace is not None:
            trace.record("pdf_type_detection", (perf_counter() - started) * 1000)


def process_pdf(
    path: Path,
    *,
    ocr_enabled: bool,
    ocr_backend: OCRBackend | None = None,
    language: str = "eng",
    searchable_output_dir: Path | None = None,
) -> ProcessedPDF:
    classification = detect_pdf_type(path)
    if classification.pdf_type == "damaged":
        raise LegacyPDFError("PDF extraction failed on every page")
    pages: list[ProcessedPDFPage] = []
    warnings: list[str] = []
    ocr_started = perf_counter()
    searchable_pdf: str | None = None
    needs_ocr = classification.pdf_type in {"scanned", "mixed"}
    if needs_ocr and ocr_enabled and ocr_backend is None:
        ocr_backend = TesseractOCRBackend()
    if needs_ocr and not ocr_enabled:
        warnings.append("OCR is disabled; low-text pages remain unavailable.")
    if needs_ocr and ocr_enabled and ocr_backend is None:
        raise OCRRetryableError("OCR backend is unavailable")
    if needs_ocr and ocr_enabled and searchable_output_dir is not None:
        searchable_pdf = generate_searchable_pdf(path, searchable_output_dir, language)
        if searchable_pdf is None:
            warnings.append(
                "OCRmyPDF is unavailable; indexed OCR text without a derived PDF."
            )
    for metrics in classification.pages:
        if metrics.has_usable_text or not needs_ocr:
            pages.append(
                ProcessedPDFPage(
                    metrics.page_number,
                    metrics.text,
                    "pdf_text",
                    "born_digital" if not needs_ocr else "mixed_text",
                    None,
                    None,
                    metrics.bounding_boxes,
                    metrics.image_coverage_ratio,
                    metrics.width_points,
                    metrics.height_points,
                )
            )
            continue
        if not ocr_enabled or ocr_backend is None:
            pages.append(
                ProcessedPDFPage(
                    metrics.page_number,
                    metrics.text,
                    "unavailable",
                    "scanned",
                    language,
                    None,
                    (),
                    metrics.image_coverage_ratio,
                    metrics.width_points,
                    metrics.height_points,
                )
            )
            continue
        result = ocr_backend.recognize_page(path, metrics.page_number, language)
        pages.append(
            ProcessedPDFPage(
                metrics.page_number,
                result.text,
                "ocr",
                "scanned" if classification.pdf_type == "scanned" else "mixed_ocr",
                result.language,
                result.confidence,
                result.bounding_boxes,
                metrics.image_coverage_ratio,
                metrics.width_points,
                metrics.height_points,
            )
        )
    if needs_ocr:
        trace = current_latency_trace()
        if trace is not None:
            trace.record("ocr", (perf_counter() - ocr_started) * 1000)
            confidences = [
                page.ocr_confidence for page in pages if page.ocr_confidence is not None
            ]
            if confidences:
                trace.set_counter("ocr_confidence", round(fmean(confidences), 4))
    parse_started = perf_counter()
    parser = PyMuPDFRuleLayoutParser()
    parsed_pages = parser.parse(pages)
    trace = current_latency_trace()
    if trace is not None:
        trace.record("layout_parse", (perf_counter() - parse_started) * 1000)
    engine = ocr_backend.name if needs_ocr and ocr_backend else None
    version = ocr_backend.version if needs_ocr and ocr_backend else None
    return ProcessedPDF(
        classification,
        tuple(parsed_pages),
        parser.name,
        parser.version,
        engine,
        version,
        searchable_pdf,
        tuple(warnings),
    )


class PyMuPDFRuleLayoutParser:
    """Primary lightweight parser: PyMuPDF blocks plus math-aware rules."""

    name = "pymupdf-rule-layout"
    version = "1"

    def parse(self, pages: list[ProcessedPDFPage]) -> list[ProcessedPDFPage]:
        repeated_headers, repeated_footers = _repeated_marginal_lines(pages)
        output: list[ProcessedPDFPage] = []
        for page in pages:
            kept_lines = []
            elements: list[LayoutElement] = []
            lines = [line.strip() for line in page.text.splitlines() if line.strip()]
            for index, line in enumerate(lines):
                if index == 0 and _normalize_marginal(line) in repeated_headers:
                    elements.append(LayoutElement("header", line))
                    continue
                if (
                    index == len(lines) - 1
                    and _normalize_marginal(line) in repeated_footers
                ):
                    elements.append(LayoutElement("footer", line))
                    continue
                element_type = classify_layout_element(line)
                elements.append(LayoutElement(element_type, line))
                kept_lines.append(line)
            output.append(
                ProcessedPDFPage(
                    page.page_number,
                    "\n".join(kept_lines),
                    page.extraction_method,
                    page.source_type,
                    page.language,
                    page.ocr_confidence,
                    page.bounding_boxes,
                    page.image_coverage_ratio,
                    page.width_points,
                    page.height_points,
                    tuple(elements),
                )
            )
        return output


def classify_layout_element(text: str) -> ElementType:
    normalized = " ".join(text.split())
    lower = normalized.casefold()
    if re.match(r"^(theorem|proposition|corollary)\s+[\divxlc0-9.:-]+", lower):
        return "theorem"
    if re.match(r"^lemma\s+[\divxlc0-9.:-]+", lower):
        return "lemma"
    if lower.startswith("definition"):
        return "definition"
    if lower.startswith(("proof", "demonstration")) or lower in {"qed", "□", "∎"}:
        return "proof"
    if re.match(r"^(figure|fig\.)\s*\d+", lower):
        return "figure_caption"
    if re.match(r"^(table)\s*\d+", lower) or normalized.count("|") >= 2:
        return "table"
    if lower in {"contents", "table of contents"}:
        return "contents"
    if lower in {"bibliography", "references"}:
        return "bibliography"
    if lower in {"index", "subject index"}:
        return "index"
    math_symbols = sum(character in "=∑∫√≤≥∞∂∇→↦⊂⊆∈∀∃λμσπ" for character in normalized)
    if math_symbols >= 2 or ("\\(" in normalized or "$$" in normalized):
        return "formula"
    if len(normalized) <= 100 and (
        normalized.isupper() or re.match(r"^(chapter|section|§|\d+(?:\.\d+)*)\b", lower)
    ):
        return "heading"
    if re.match(r"^\d{1,3}[.)]\s+", normalized) and len(normalized) < 180:
        return "footnote"
    return "paragraph"


class TesseractOCRBackend:
    name = "tesseract"

    def __init__(self, executable: str = "tesseract", dpi: int = 300) -> None:
        self.executable = executable
        self.dpi = dpi
        binary = shutil.which(executable)
        if not binary:
            raise OCRRetryableError("Tesseract executable is unavailable")
        self._binary = binary
        version = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, check=False
        ).stdout.splitlines()
        self.version = version[0][:80] if version else "unknown"

    def recognize_page(
        self, path: Path, page_number: int, language: str
    ) -> OCRPageResult:
        try:
            import fitz
        except ImportError as exc:
            raise OCRRetryableError("PyMuPDF is required for OCR rendering") from exc
        with tempfile.TemporaryDirectory(prefix="pla-ocr-") as temp_dir:
            image_path = Path(temp_dir) / f"page-{page_number}.png"
            document = fitz.open(path)
            try:
                page = document.load_page(page_number - 1)
                pixmap = page.get_pixmap(dpi=self.dpi, alpha=False)
                pixmap.save(image_path)
            finally:
                document.close()
            command = [
                self._binary,
                str(image_path),
                "stdout",
                "-l",
                language,
                "--psm",
                "6",
                "tsv",
            ]
            result = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            if result.returncode != 0:
                raise OCRRetryableError("Tesseract page recognition failed")
            boxes, text, confidence = _parse_tesseract_tsv(result.stdout)
            return OCRPageResult(
                text, confidence, tuple(boxes), language, self.name, self.version
            )


def generate_searchable_pdf(
    source: Path, output_dir: Path, language: str
) -> str | None:
    executable = shutil.which("ocrmypdf")
    if not executable:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    output = output_dir / f"{source.stem}-{digest}-searchable.pdf"
    command = [
        executable,
        "--skip-text",
        "--rotate-pages",
        "--deskew",
        "--clean",
        "--language",
        language,
        str(source),
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not output.exists():
        raise OCRRetryableError("OCRmyPDF searchable PDF generation failed")
    return str(output)


def _inspect_pages(path: Path) -> list[PageDetectionMetrics]:
    if not path.exists() or path.suffix.lower() != ".pdf":
        raise LegacyPDFError("Expected an existing PDF file")
    try:
        reader = PdfReader(str(path))
    except (OSError, PdfReadError) as exc:
        raise LegacyPDFError("Could not read PDF file") from exc
    fitz_document = None
    try:
        import fitz

        fitz_document = fitz.open(path)
    except (ImportError, RuntimeError, ValueError):
        fitz_document = None
    pages: list[PageDetectionMetrics] = []
    try:
        for index, page in enumerate(reader.pages, start=1):
            extraction_error = False
            try:
                text = page.extract_text() or ""
            except (KeyError, PdfReadError, ValueError):
                text = ""
                extraction_error = True
            printable = sum(
                character.isprintable() and not character.isspace()
                for character in text
            )
            nonspace = sum(not character.isspace() for character in text)
            ratio = printable / nonspace if nonspace else 0
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            image_count = 0
            coverage = 0.0
            font_count = 0
            boxes: tuple[BoundingBox, ...] = ()
            if fitz_document is not None:
                fitz_page = fitz_document.load_page(index - 1)
                images = fitz_page.get_images(full=True)
                image_count = len(images)
                page_area = max(1.0, fitz_page.rect.width * fitz_page.rect.height)
                image_area = 0.0
                for image in images:
                    for rectangle in fitz_page.get_image_rects(image[0]):
                        image_area += max(0.0, rectangle.width * rectangle.height)
                coverage = min(1.0, image_area / page_area)
                fonts = fitz_page.get_fonts(full=True)
                font_count = len(fonts)
                blocks = fitz_page.get_text("blocks")
                boxes = tuple(
                    BoundingBox(
                        float(x0), float(y0), float(x1), float(y1), str(block_text)
                    )
                    for x0, y0, x1, y1, block_text, *_ in blocks
                    if str(block_text).strip()
                )
            else:
                resources = page.get("/Resources") or {}
                xobjects = (
                    resources.get("/XObject") if hasattr(resources, "get") else None
                )
                image_count = len(xobjects or {})
                coverage = 0.9 if image_count and nonspace < 20 else 0.0
                fonts = resources.get("/Font") if hasattr(resources, "get") else None
                font_count = len(fonts or {})
            pages.append(
                PageDetectionMetrics(
                    index,
                    text,
                    nonspace,
                    ratio,
                    image_count,
                    coverage,
                    font_count,
                    width,
                    height,
                    extraction_error,
                    boxes,
                )
            )
    finally:
        if fitz_document is not None:
            fitz_document.close()
    return pages


def _parse_tesseract_tsv(value: str) -> tuple[list[BoundingBox], str, float | None]:
    reader = csv.DictReader(io.StringIO(value), delimiter="\t")
    boxes: list[BoundingBox] = []
    words: list[str] = []
    confidences: list[float] = []
    for row in reader:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            confidence = float(row.get("conf") or -1)
            left = float(row.get("left") or 0)
            top = float(row.get("top") or 0)
            width = float(row.get("width") or 0)
            height = float(row.get("height") or 0)
        except ValueError:
            continue
        normalized_confidence = confidence / 100 if confidence >= 0 else None
        boxes.append(
            BoundingBox(
                left,
                top,
                left + width,
                top + height,
                text,
                normalized_confidence,
                "ocr_pixels",
            )
        )
        words.append(text)
        if normalized_confidence is not None:
            confidences.append(normalized_confidence)
    return boxes, " ".join(words), fmean(confidences) if confidences else None


def _repeated_marginal_lines(
    pages: list[ProcessedPDFPage],
) -> tuple[set[str], set[str]]:
    header_counts: Counter[str] = Counter()
    footer_counts: Counter[str] = Counter()
    for page in pages:
        lines = [line.strip() for line in page.text.splitlines() if line.strip()]
        header_counts.update(_normalize_marginal(line) for line in lines[:2])
        footer_counts.update(_normalize_marginal(line) for line in lines[-2:])
    threshold = max(2, int(len(pages) * 0.5))
    return (
        {line for line, count in header_counts.items() if line and count >= threshold},
        {line for line, count in footer_counts.items() if line and count >= threshold},
    )


def _normalize_marginal(value: str) -> str:
    return re.sub(r"\d+", "#", " ".join(value.casefold().split()))


def serialize_detection(classification: PDFClassification) -> str:
    """Safe bounded JSON for diagnostics/tests; it never contains page text."""
    return json.dumps(classification.evidence(), sort_keys=True)
