from pathlib import Path

DATA_DIR = (Path(__file__).resolve().parent.parent.parent / "data").resolve()

ALLOWED_EXTENSIONS = {".txt", ".md"}


class UnsupportedFileTypeError(ValueError):
    pass


class PathTraversalError(ValueError):
    pass


class DataFileNotFoundError(FileNotFoundError):
    pass


def resolve_data_path(file_path: str) -> Path:
    """Resolve file_path relative to the backend data directory.

    Rejects paths that escape DATA_DIR before checking extension or
    existence, so no information about files outside the data
    directory is ever read or exposed.
    """
    candidate = (DATA_DIR / file_path).resolve()

    if not candidate.is_relative_to(DATA_DIR):
        raise PathTraversalError(
            f"File path '{file_path}' resolves outside the allowed data directory"
        )

    if candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{candidate.suffix}'. Allowed types: "
            f"{sorted(ALLOWED_EXTENSIONS)}"
        )

    if not candidate.is_file():
        raise DataFileNotFoundError(
            f"File '{file_path}' was not found in the data directory"
        )

    return candidate


def load_text_file(file_path: str) -> str:
    resolved = resolve_data_path(file_path)
    return resolved.read_text(encoding="utf-8")
