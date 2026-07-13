import re
from pathlib import Path


HAN_TEXT = re.compile(r"[\u3400-\u9fff]")
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".css"}


def test_product_source_has_no_hard_coded_chinese_text() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    roots = [repository_root / "backend" / "app", repository_root / "frontend" / "src"]
    violations: list[str] = []
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in SOURCE_SUFFIXES or ".test." in path.name:
                continue
            text = path.read_text(encoding="utf-8")
            if HAN_TEXT.search(text):
                violations.append(str(path.relative_to(repository_root)))
    assert violations == []
