import pytest

from app.ingestion.pdf import PDFExtractionError, extract_pdf_pages
from tests.pdf_fixtures import make_pdf_bytes


def test_extract_pdf_pages_returns_text_with_page_numbers(tmp_path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(
        make_pdf_bytes(
            [
                "First page vector spaces.",
                "",
                "Third page compactness.",
            ]
        )
    )

    pages = extract_pdf_pages(pdf_path)

    assert [page.page_number for page in pages] == [1, 2, 3]
    assert pages[0].text == "First page vector spaces."
    assert pages[1].text == ""
    assert pages[2].text == "Third page compactness."


def test_extract_pdf_pages_rejects_missing_pdf(tmp_path) -> None:
    with pytest.raises(PDFExtractionError, match="does not exist"):
        extract_pdf_pages(tmp_path / "missing.pdf")


def test_extract_pdf_pages_rejects_invalid_pdf(tmp_path) -> None:
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_text("not a pdf", encoding="utf-8")

    with pytest.raises(PDFExtractionError, match="Could not read PDF file"):
        extract_pdf_pages(pdf_path)
