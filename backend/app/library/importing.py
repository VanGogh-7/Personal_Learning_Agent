import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, Settings, get_settings
from app.library.indexing import LibraryIndexResult, LibraryIndexingError, index_library_item
from app.library.service import LibraryItemResult, create_library_item, get_library_item


class LibraryImportError(ValueError):
    """Raised when a local PDF cannot be imported into managed storage."""


@dataclass(frozen=True)
class LibraryPdfImportResult:
    item: LibraryItemResult
    index_result: LibraryIndexResult
    original_filename: str
    original_source_path: str
    managed_file_path: str
    file_size_bytes: int


def import_pdf_paths(
    session: Session,
    source_paths: list[str],
    settings: Settings | None = None,
) -> list[LibraryPdfImportResult]:
    if not source_paths:
        raise LibraryImportError("At least one PDF path is required.")

    # Repository imports always copy PDFs into backend-managed storage before
    # indexing so later retrieval never depends on the user's original path.
    app_settings = settings or get_settings()
    storage_dir = _resolve_storage_dir(app_settings.library_storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)

    results: list[LibraryPdfImportResult] = []
    for source_path in source_paths:
        result = import_pdf_path(session, source_path, storage_dir=storage_dir)
        results.append(result)
    return results


def import_pdf_path(
    session: Session,
    source_path: str,
    storage_dir: Path,
) -> LibraryPdfImportResult:
    source = _validate_pdf_source_path(source_path)
    managed_path = _copy_pdf_to_managed_storage(source, storage_dir)
    file_size = managed_path.stat().st_size
    title = _title_from_pdf_path(source)
    description = (
        f"Imported PDF: {source.name}\n"
        f"Managed file: {managed_path.name}\n"
        f"File size: {file_size} bytes"
    )

    try:
        # Create the Library item against the managed copy, then index through
        # the normal PDF extraction/chunking/embedding pipeline.
        item = create_library_item(
            session,
            title=title,
            description=description,
            file_path=str(managed_path),
            file_type="pdf",
            status="registered",
        )
        index_result = index_library_item(session, item.item_id)
        if index_result is None:
            raise LibraryIndexingError("Imported library item could not be indexed.")

        refreshed = get_library_item(session, item.item_id)
        if refreshed is None:
            raise LibraryImportError("Imported library item could not be loaded.")
    except Exception:
        managed_path.unlink(missing_ok=True)
        raise

    return LibraryPdfImportResult(
        item=refreshed,
        index_result=index_result,
        original_filename=source.name,
        original_source_path=str(source),
        managed_file_path=str(managed_path),
        file_size_bytes=file_size,
    )


def _validate_pdf_source_path(source_path: str) -> Path:
    if not source_path or not source_path.strip():
        raise LibraryImportError("PDF source path must not be empty.")

    source = Path(source_path).expanduser()
    if not source.exists():
        raise LibraryImportError(f"PDF source file does not exist: {source}")
    if not source.is_file():
        raise LibraryImportError(f"PDF source path is not a file: {source}")
    if source.suffix.lower() != ".pdf":
        raise LibraryImportError("Only .pdf files can be imported.")
    with source.open("rb") as file:
        if file.read(5) != b"%PDF-":
            raise LibraryImportError("Selected file is not a valid PDF.")
    return source


def _copy_pdf_to_managed_storage(source: Path, storage_dir: Path) -> Path:
    storage_dir.mkdir(parents=True, exist_ok=True)
    destination = storage_dir / f"{uuid.uuid4().hex}_{_safe_filename(source.name)}"
    shutil.copy2(source, destination)
    return destination


def _resolve_storage_dir(storage_dir: str) -> Path:
    path = Path(storage_dir).expanduser()
    if path.is_absolute():
        return path
    return BACKEND_DIR / path


def _safe_filename(filename: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in {".", "-", "_"} else "_"
        for character in filename
    ).strip("._")
    return safe or "imported.pdf"


def _title_from_pdf_path(path: Path) -> str:
    title = path.stem.strip()
    return title or "Untitled PDF"
