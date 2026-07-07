from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PDFExtractionError(ValueError):
    """Raised when PDF text cannot be extracted for indexing."""


@dataclass(frozen=True)
class PDFPageText:
    page_number: int
    text: str


def extract_pdf_pages(path: Path) -> list[PDFPageText]:
    """Extract text from a local PDF one page at a time.

    Page numbers are 1-based to match user-facing PDF readers. Empty
    pages are returned with an empty string so callers can preserve page
    accounting while deciding whether to create chunks.
    """
    if path.suffix.lower() != ".pdf":
        raise PDFExtractionError(f"Expected a .pdf file, got: {path}")
    if not path.exists():
        raise PDFExtractionError(f"PDF file does not exist: {path}")
    if not path.is_file():
        raise PDFExtractionError(f"PDF path is not a file: {path}")

    try:
        reader = PdfReader(str(path))
    except (OSError, PdfReadError) as exc:
        raise PDFExtractionError(f"Could not read PDF file: {path}") from exc

    pages: list[PDFPageText] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except (KeyError, PdfReadError, ValueError) as exc:
            raise PDFExtractionError(
                f"Could not extract text from PDF page {index}: {path}"
            ) from exc
        pages.append(PDFPageText(page_number=index, text=text))

    return pages
