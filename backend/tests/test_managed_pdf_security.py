from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.library.managed_files import (
    ManagedPdfSecurityError,
    ManagedPdfUnavailableError,
    open_managed_pdf,
    resolve_managed_pdf,
)
from app.models.library_item import LibraryItem


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    LibraryItem.__table__.create(engine)
    with Session(engine) as database_session:
        yield database_session
    engine.dispose()


def _settings(root: Path) -> Settings:
    return Settings(_env_file=None, library_storage_dir=str(root))


def _item(session: Session, path: str, *, file_type: str = "pdf") -> LibraryItem:
    item = LibraryItem(
        title="Managed PDF",
        file_path=path,
        file_type=file_type,
        status="indexed",
    )
    session.add(item)
    session.flush()
    return item


def _pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n% managed test\n")


def test_opens_pdf_with_spaces_and_non_ascii_name(
    session: Session, tmp_path: Path
) -> None:
    root = tmp_path / "managed root"
    path = root / "拓扑 学.pdf"
    _pdf(path)
    item = _item(session, str(path))
    opened: list[Path] = []

    open_managed_pdf(
        session,
        item.id,
        settings=_settings(root),
        opener=opened.append,
    )

    assert opened == [path.resolve()]


def test_rejects_missing_managed_pdf(session: Session, tmp_path: Path) -> None:
    root = tmp_path / "managed"
    root.mkdir()
    item = _item(session, str(root / "missing.pdf"))

    with pytest.raises(ManagedPdfUnavailableError, match="does not exist"):
        resolve_managed_pdf(session, item.id, settings=_settings(root))


def test_rejects_parent_traversal(session: Session, tmp_path: Path) -> None:
    root = tmp_path / "managed"
    root.mkdir()
    outside = tmp_path / "outside.pdf"
    _pdf(outside)
    item = _item(session, str(root / ".." / outside.name))

    with pytest.raises(ManagedPdfSecurityError, match="traversal"):
        resolve_managed_pdf(session, item.id, settings=_settings(root))


def test_rejects_symlink_escape(session: Session, tmp_path: Path) -> None:
    root = tmp_path / "managed"
    root.mkdir()
    outside = tmp_path / "outside.pdf"
    _pdf(outside)
    link = root / "linked.pdf"
    link.symlink_to(outside)
    item = _item(session, str(link))

    with pytest.raises(ManagedPdfSecurityError, match="escaped"):
        resolve_managed_pdf(session, item.id, settings=_settings(root))


def test_rejects_absolute_path_outside_root(session: Session, tmp_path: Path) -> None:
    root = tmp_path / "managed"
    root.mkdir()
    outside = tmp_path / "outside.pdf"
    _pdf(outside)
    item = _item(session, str(outside))

    with pytest.raises(ManagedPdfSecurityError, match="escaped"):
        resolve_managed_pdf(session, item.id, settings=_settings(root))


def test_rejects_non_pdf_item(session: Session, tmp_path: Path) -> None:
    root = tmp_path / "managed"
    path = root / "notes.txt"
    _pdf(path)
    item = _item(session, str(path), file_type="txt")

    with pytest.raises(ManagedPdfSecurityError, match="Only managed PDF"):
        resolve_managed_pdf(session, item.id, settings=_settings(root))


def test_unknown_library_item_is_not_resolved(session: Session, tmp_path: Path) -> None:
    from app.library.managed_files import ManagedPdfNotFoundError

    root = tmp_path / "managed"
    root.mkdir()
    with pytest.raises(ManagedPdfNotFoundError):
        resolve_managed_pdf(session, uuid.uuid4(), settings=_settings(root))
