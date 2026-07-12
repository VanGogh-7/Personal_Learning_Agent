import pytest
from fastapi.testclient import TestClient

from app.ingestion.chunking import chunk_text
from app.ingestion.loaders import (
    DATA_DIR,
    DataFileNotFoundError,
    PathTraversalError,
    UnsupportedFileTypeError,
    load_text_file,
)
from app.main import app

client = TestClient(app)


@pytest.fixture
def sample_txt_file():
    path = DATA_DIR / "sample_test_file.txt"
    path.write_text(
        "Hello world. This is a sample text file for ingestion tests.", encoding="utf-8"
    )
    yield path.name
    path.unlink(missing_ok=True)


@pytest.fixture
def sample_md_file():
    path = DATA_DIR / "sample_test_file.md"
    path.write_text(
        "# Title\n\nSome **markdown** content for testing.", encoding="utf-8"
    )
    yield path.name
    path.unlink(missing_ok=True)


def test_chunk_text_normal() -> None:
    chunks = chunk_text("abcdefghij", chunk_size=4, chunk_overlap=1)

    assert len(chunks) == 3
    assert chunks[0].index == 0
    assert chunks[0].content == "abcd"
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == 4
    assert chunks[-1].char_end == 10


def test_chunk_text_empty() -> None:
    assert chunk_text("", chunk_size=10, chunk_overlap=2) == []
    assert chunk_text("   \n  ", chunk_size=10, chunk_overlap=2) == []


def test_chunk_text_invalid_chunk_size() -> None:
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=0, chunk_overlap=0)

    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=-5, chunk_overlap=0)


def test_chunk_text_invalid_chunk_overlap() -> None:
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=5, chunk_overlap=-1)

    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=5, chunk_overlap=5)


def test_load_txt_file(sample_txt_file: str) -> None:
    text = load_text_file(sample_txt_file)
    assert "Hello world" in text


def test_load_md_file(sample_md_file: str) -> None:
    text = load_text_file(sample_md_file)
    assert "# Title" in text


def test_load_file_rejects_unsupported_extension() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        load_text_file("something.pdf")


def test_load_file_rejects_path_traversal() -> None:
    with pytest.raises(PathTraversalError):
        load_text_file("../.env")


def test_load_file_missing_file() -> None:
    with pytest.raises(DataFileNotFoundError):
        load_text_file("does_not_exist.txt")


def test_api_chunk_text() -> None:
    response = client.post(
        "/api/ingestion/chunk-text",
        json={"text": "abcdefghij", "chunk_size": 4, "chunk_overlap": 1},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_chunks"] == 3
    assert len(data["chunks"]) == 3


def test_api_chunk_text_invalid_overlap() -> None:
    response = client.post(
        "/api/ingestion/chunk-text",
        json={"text": "abcdefghij", "chunk_size": 4, "chunk_overlap": 4},
    )

    assert response.status_code == 400


def test_api_load_file(sample_txt_file: str) -> None:
    response = client.post(
        "/api/ingestion/load-file",
        json={"file_path": sample_txt_file, "chunk_size": 100, "chunk_overlap": 10},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["file_path"] == sample_txt_file
    assert data["total_chunks"] == len(data["chunks"])
    assert data["total_chunks"] > 0


def test_api_load_file_rejects_path_traversal() -> None:
    response = client.post(
        "/api/ingestion/load-file",
        json={"file_path": "../.env", "chunk_size": 100, "chunk_overlap": 10},
    )

    assert response.status_code == 400


def test_api_load_file_rejects_unsupported_extension() -> None:
    response = client.post(
        "/api/ingestion/load-file",
        json={"file_path": "something.pdf", "chunk_size": 100, "chunk_overlap": 10},
    )

    assert response.status_code == 400


def test_api_load_file_missing_file() -> None:
    response = client.post(
        "/api/ingestion/load-file",
        json={
            "file_path": "does_not_exist.txt",
            "chunk_size": 100,
            "chunk_overlap": 10,
        },
    )

    assert response.status_code == 404
