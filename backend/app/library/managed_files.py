from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, Settings, get_settings
from app.models.library_item import LibraryItem


class ManagedPdfError(ValueError):
    """Base error for the managed-PDF open boundary."""


class ManagedPdfNotFoundError(ManagedPdfError):
    """The requested Library item does not exist."""


class ManagedPdfUnavailableError(ManagedPdfError):
    """The managed PDF is missing or cannot be opened."""


class ManagedPdfSecurityError(ManagedPdfError):
    """The stored path is outside the managed PDF trust boundary."""


PdfOpener = Callable[[Path], None]


def resolve_managed_pdf(
    session: Session,
    library_item_id: uuid.UUID,
    *,
    settings: Settings | None = None,
) -> Path:
    item = session.get(LibraryItem, library_item_id)
    if item is None:
        raise ManagedPdfNotFoundError("Library item was not found")
    if (item.file_type or "").strip().lower().removeprefix(".") != "pdf":
        raise ManagedPdfSecurityError("Only managed PDF Library items can be opened")
    stored_path = (item.file_path or "").strip()
    if not stored_path:
        raise ManagedPdfUnavailableError("The managed PDF path is unavailable")

    raw_path = Path(stored_path).expanduser()
    if ".." in raw_path.parts:
        raise ManagedPdfSecurityError("Managed PDF path traversal was rejected")

    root = _managed_root(settings or get_settings())
    if not root.is_dir():
        raise ManagedPdfUnavailableError("The managed PDF root is unavailable")
    canonical_root = root.resolve(strict=True)
    candidate = raw_path if raw_path.is_absolute() else canonical_root / raw_path
    try:
        canonical_path = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ManagedPdfUnavailableError("The managed PDF file does not exist") from exc
    try:
        canonical_path.relative_to(canonical_root)
    except ValueError as exc:
        raise ManagedPdfSecurityError("Managed PDF path escaped its root") from exc
    if not canonical_path.is_file() or canonical_path.suffix.lower() != ".pdf":
        raise ManagedPdfSecurityError("Managed file is not a PDF")
    try:
        with canonical_path.open("rb") as file:
            if file.read(5) != b"%PDF-":
                raise ManagedPdfSecurityError("Managed file is not a valid PDF")
    except OSError as exc:
        raise ManagedPdfUnavailableError("The managed PDF could not be read") from exc
    return canonical_path


def open_managed_pdf(
    session: Session,
    library_item_id: uuid.UUID,
    *,
    settings: Settings | None = None,
    opener: PdfOpener | None = None,
) -> None:
    path = resolve_managed_pdf(session, library_item_id, settings=settings)
    try:
        (opener or _open_with_system_reader)(path)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ManagedPdfUnavailableError(
            "The PDF could not be opened with the system reader"
        ) from exc


def _managed_root(settings: Settings) -> Path:
    configured = Path(settings.library_storage_dir).expanduser()
    return configured if configured.is_absolute() else BACKEND_DIR / configured


def _open_with_system_reader(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    command = "open" if sys.platform == "darwin" else "xdg-open"
    executable = shutil.which(command)
    if executable is None:
        raise OSError("No system PDF opener is available")
    subprocess.run(
        [executable, str(path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )
