from __future__ import annotations

import hashlib
import json
import math
import platform
import shutil
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ingestion.legacy_pdf import (
    OCRRetryableError,
    TesseractOCRBackend,
    detect_pdf_type,
    generate_searchable_pdf,
)

QueryKind = Literal[
    "theorem_name",
    "theorem_number",
    "definition",
    "proof",
    "math_symbol",
    "formula_context",
    "figure",
    "ocr_error",
    "exact_page_or_section",
]
RetrievalVariant = Literal[
    "dense",
    "postgres_fts",
    "hybrid",
    "reranked",
    "parent_context",
    "visual",
    "dual",
]

REQUIRED_DOCUMENT_FEATURES = {
    "rotated_pages",
    "skewed_scan",
    "blur_or_low_contrast",
    "two_column",
    "formula_dense",
    "mixed_text_and_scan",
    "headers_footers",
    "contents",
    "index",
}
REQUIRED_QUERY_KINDS = set(QueryKind.__args__)


class RegionLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float]
    coordinate_space: Literal["pdf_points", "image_pixels"] = "pdf_points"


class ScannedMathBook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    title: str = Field(min_length=1)
    pdf_file: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    split: Literal["development", "held_out"]
    document_features: set[str] = Field(min_length=1)
    source_and_permission_notes: str = Field(min_length=1)


class ScannedMathQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    book_id: str
    query: str = Field(min_length=1)
    query_kind: QueryKind
    relevant_pages: list[int] = Field(min_length=1)
    relevant_regions: list[RegionLabel] = Field(min_length=1)
    expected_section: str = Field(min_length=1)
    citation_page: int = Field(ge=1)
    ocr_difficulty: Literal["low", "medium", "high"]
    visual_layout_dependency: bool
    split: Literal["development", "held_out"]

    @model_validator(mode="after")
    def validate_page_labels(self) -> "ScannedMathQuery":
        if self.citation_page not in self.relevant_pages:
            raise ValueError("citation_page must be a relevant page")
        if any(
            region.page not in self.relevant_pages for region in self.relevant_regions
        ):
            raise ValueError("every labelled region must be on a relevant page")
        return self


class DatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    version: str
    annotation_status: Literal["draft", "sealed"]
    tuning_prohibited_on_held_out: bool = True
    books: list[ScannedMathBook]


class RetrievalRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    query_id: str
    variant: RetrievalVariant
    ranked_pages: list[int] = Field(default_factory=list)
    query_ms: float = Field(ge=0)
    indexing_ms: float = Field(ge=0)
    storage_bytes: int = Field(ge=0)
    failed: bool = False
    failure_category: str | None = None
    page_embedding_ms: float | None = Field(default=None, ge=0)
    gpu_memory_mb: float | None = Field(default=None, ge=0)
    cold_start_ms: float | None = Field(default=None, ge=0)
    patch_vector_count: int | None = Field(default=None, ge=0)
    fusion_ms: float | None = Field(default=None, ge=0)


def load_scanned_math_dataset(
    dataset_dir: Path, *, verify_files: bool = True
) -> tuple[DatasetManifest, list[ScannedMathQuery]]:
    manifest_path = dataset_dir / "manifest.json"
    query_path = dataset_dir / "queries.jsonl"
    manifest = DatasetManifest.model_validate_json(manifest_path.read_text("utf-8"))
    queries = _load_jsonl(query_path, ScannedMathQuery)
    if manifest.annotation_status != "sealed":
        raise ValueError("Real evaluation requires a sealed human-labelled dataset")
    if not manifest.tuning_prohibited_on_held_out:
        raise ValueError("Held-out labels must be prohibited from tuning")
    if not 3 <= len(manifest.books) <= 5:
        raise ValueError("Dataset must contain 3 to 5 scanned mathematics books")
    if len(queries) < 50:
        raise ValueError("Dataset must contain at least 50 labelled queries")
    book_ids = {book.book_id for book in manifest.books}
    if len(book_ids) != len(manifest.books):
        raise ValueError("Duplicate book_id")
    query_ids = {query.query_id for query in queries}
    if len(query_ids) != len(queries):
        raise ValueError("Duplicate query_id")
    if any(query.book_id not in book_ids for query in queries):
        raise ValueError("Every query must reference a manifest book")
    book_splits = {book.book_id: book.split for book in manifest.books}
    if any(query.split != book_splits[query.book_id] for query in queries):
        raise ValueError("Query and book splits must match")
    held_out_queries = [query for query in queries if query.split == "held_out"]
    if {query.query_kind for query in held_out_queries} != REQUIRED_QUERY_KINDS:
        raise ValueError("Held-out dataset does not cover every required query kind")
    held_out_books = [book for book in manifest.books if book.split == "held_out"]
    features = set().union(*(book.document_features for book in held_out_books))
    missing = REQUIRED_DOCUMENT_FEATURES - features
    if missing:
        raise ValueError(
            f"Held-out dataset is missing document features: {sorted(missing)}"
        )
    if not {"development", "held_out"} <= {book.split for book in manifest.books}:
        raise ValueError(
            "Dataset needs physically identified development and held-out books"
        )
    if verify_files:
        for book in manifest.books:
            path = _safe_pdf_path(dataset_dir, book.pdf_file)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != book.sha256:
                raise ValueError(f"PDF checksum mismatch for {book.book_id}")
    return manifest, queries


def load_retrieval_runs(path: Path) -> list[RetrievalRun]:
    return _load_jsonl(path, RetrievalRun)


def evaluate_real_retrieval(
    manifest: DatasetManifest,
    queries: list[ScannedMathQuery],
    runs: list[RetrievalRun],
    *,
    environment: dict[str, object],
) -> dict[str, object]:
    labels = {query.query_id: query for query in queries if query.split == "held_out"}
    if not labels:
        raise ValueError("No held-out query labels")
    unknown = {run.query_id for run in runs} - set(labels)
    if unknown:
        raise ValueError(
            f"Runs include non-held-out or unknown query IDs: {sorted(unknown)}"
        )
    variants: dict[str, dict[str, object]] = {}
    grouped: dict[str, list[RetrievalRun]] = defaultdict(list)
    for run in runs:
        grouped[run.variant].append(run)
    for variant in RetrievalVariant.__args__:
        variants[variant] = _score_variant(grouped.get(variant, []), labels)
    return {
        "stage": 62,
        "dataset": {
            "dataset_id": manifest.dataset_id,
            "version": manifest.version,
            "book_count": len(manifest.books),
            "held_out_query_count": len(labels),
            "human_labelled": True,
            "held_out": True,
        },
        "environment": environment,
        "terminology": {
            "postgres_fts": "PostgreSQL full-text search; not complete BM25"
        },
        "variants": variants,
        "production_decision": production_decision(variants),
    }


def reciprocal_rank_fusion(
    text_pages: list[int], visual_pages: list[int], *, k: int = 60, limit: int = 10
) -> list[int]:
    """Fuse ranks only; raw scores from unlike vector spaces never mix."""
    if k < 1 or limit < 1:
        raise ValueError("k and limit must be positive")
    scores: dict[int, float] = defaultdict(float)
    best_rank: dict[int, int] = {}
    for ranking in (text_pages, visual_pages):
        for rank, page in enumerate(ranking, 1):
            scores[page] += 1 / (k + rank)
            best_rank[page] = min(best_rank.get(page, rank), rank)
    return sorted(scores, key=lambda page: (-scores[page], best_rank[page], page))[
        :limit
    ]


def build_dual_runs(
    text_runs: list[RetrievalRun], visual_runs: list[RetrievalRun]
) -> list[RetrievalRun]:
    """Pair repeated text/visual observations and create rank-only fusion runs."""
    text_by_query: dict[str, list[RetrievalRun]] = defaultdict(list)
    visual_by_query: dict[str, list[RetrievalRun]] = defaultdict(list)
    for run in text_runs:
        if run.variant == "parent_context":
            text_by_query[run.query_id].append(run)
    for run in visual_runs:
        if run.variant == "visual":
            visual_by_query[run.query_id].append(run)
    if set(text_by_query) != set(visual_by_query):
        raise ValueError("Text and visual observations must cover identical queries")
    output = []
    for query_id in sorted(text_by_query):
        text_query_runs = text_by_query[query_id]
        visual_query_runs = visual_by_query[query_id]
        if len(text_query_runs) != len(visual_query_runs):
            raise ValueError("Text and visual repeat counts must match")
        for repeat, (text_run, visual_run) in enumerate(
            zip(text_query_runs, visual_query_runs, strict=True), 1
        ):
            started = perf_counter()
            ranking = reciprocal_rank_fusion(
                text_run.ranked_pages, visual_run.ranked_pages
            )
            fusion_ms = (perf_counter() - started) * 1000
            output.append(
                RetrievalRun(
                    run_id=f"dual-repeat-{repeat}",
                    query_id=query_id,
                    variant="dual",
                    ranked_pages=ranking,
                    query_ms=text_run.query_ms + visual_run.query_ms + fusion_ms,
                    indexing_ms=text_run.indexing_ms + visual_run.indexing_ms,
                    storage_bytes=text_run.storage_bytes + visual_run.storage_bytes,
                    failed=text_run.failed or visual_run.failed,
                    failure_category=(
                        text_run.failure_category or visual_run.failure_category
                    ),
                    page_embedding_ms=visual_run.page_embedding_ms,
                    gpu_memory_mb=visual_run.gpu_memory_mb,
                    cold_start_ms=visual_run.cold_start_ms,
                    patch_vector_count=visual_run.patch_vector_count,
                    fusion_ms=fusion_ms,
                )
            )
    return output


def probe_environment() -> dict[str, object]:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "pymupdf": _pymupdf_version(),
        "tesseract": _command_version("tesseract", "--version"),
        "ocrmypdf": _command_version("ocrmypdf", "--version"),
        "nvidia_smi": _command_version(
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader",
        ),
        "colpali_engine_installed": _module_available("colpali_engine"),
        "torch_installed": _module_available("torch"),
    }


def benchmark_external_ocr(
    dataset_dir: Path, manifest: DatasetManifest, *, language: str = "eng"
) -> dict[str, object]:
    """Run installed OCR tools. Caller owns explicit opt-in and output location."""
    environment = probe_environment()
    if environment["tesseract"] is None:
        return _skipped("tesseract_unavailable", environment)
    if environment["ocrmypdf"] is None:
        return _skipped("ocrmypdf_unavailable", environment)
    backend = TesseractOCRBackend()
    pages: list[dict[str, object]] = []
    failures = 0
    output_dir = dataset_dir / ".stage62-ocr-output"
    for book in manifest.books:
        pdf = _safe_pdf_path(dataset_dir, book.pdf_file)
        classification = detect_pdf_type(pdf)
        try:
            searchable = generate_searchable_pdf(pdf, output_dir, language)
        except OCRRetryableError:
            searchable = None
            failures += 1
        ocr_source = Path(searchable) if searchable is not None else pdf
        for page in classification.pages:
            started = perf_counter()
            try:
                result = backend.recognize_page(ocr_source, page.page_number, language)
                pages.append(
                    {
                        "book_id": book.book_id,
                        "page": page.page_number,
                        "success": True,
                        "ocr_page_ms": round((perf_counter() - started) * 1000, 2),
                        "ocr_confidence": result.confidence,
                        "extracted_character_count": len(result.text),
                        "bbox_count": len(result.bounding_boxes),
                        "coordinate_spaces": sorted(
                            {box.coordinate_space for box in result.bounding_boxes}
                        ),
                        "extraction_failure": False,
                        "searchable_pdf_created": searchable is not None,
                    }
                )
            except OCRRetryableError:
                failures += 1
                pages.append(
                    {
                        "book_id": book.book_id,
                        "page": page.page_number,
                        "success": False,
                        "ocr_page_ms": round((perf_counter() - started) * 1000, 2),
                        "ocr_confidence": None,
                        "extracted_character_count": 0,
                        "bbox_count": 0,
                        "coordinate_spaces": [],
                        "extraction_failure": True,
                        "searchable_pdf_created": searchable is not None,
                    }
                )
    successful = [page for page in pages if page["success"]]
    return {
        "status": "executed",
        "real_external_ocr": True,
        "environment": environment,
        "page_count": len(pages),
        "ocr_success_rate": len(successful) / len(pages) if pages else 0,
        "ocr_page_ms_p50": _percentile(
            [float(page["ocr_page_ms"]) for page in successful], 50
        ),
        "ocr_page_ms_p95": _percentile(
            [float(page["ocr_page_ms"]) for page in successful], 95
        ),
        "ocr_confidence_mean": _mean(
            [
                float(page["ocr_confidence"])
                for page in successful
                if page["ocr_confidence"] is not None
            ]
        ),
        "extracted_character_count": sum(
            int(page["extracted_character_count"]) for page in successful
        ),
        "indexing_failure_count": failures,
        "pages": pages,
    }


def production_decision(variants: dict[str, dict[str, object]]) -> str:
    text = variants.get("parent_context", {})
    dual = variants.get("dual", {})
    visual = variants.get("visual", {})
    required = (text, dual, visual)
    if any(int(item.get("successful_observation_count", 0)) == 0 for item in required):
        return "text_hybrid_default_visual_experimental_insufficient_real_evidence"
    recall_gain = float(dual.get("recall_at_5", 0)) - float(text.get("recall_at_5", 0))
    ndcg_gain = float(dual.get("ndcg_at_10", 0)) - float(text.get("ndcg_at_10", 0))
    citation_gain = float(dual.get("citation_page_accuracy", 0)) - float(
        text.get("citation_page_accuracy", 0)
    )
    stable = int(dual.get("distinct_run_count", 0)) >= 3
    if (recall_gain > 0 or ndcg_gain > 0) and citation_gain >= 0.05 and stable:
        return "candidate_only_pending_cost_and_desktop_deployment_review"
    return "text_hybrid_default_visual_experimental_only"


def write_json_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _score_variant(
    runs: list[RetrievalRun], labels: dict[str, ScannedMathQuery]
) -> dict[str, object]:
    successful = [run for run in runs if not run.failed]
    metrics: dict[str, object] = {
        "observation_count": len(runs),
        "successful_observation_count": len(successful),
        "failure_count": len(runs) - len(successful),
        "distinct_run_count": len({run.run_id for run in successful}),
    }
    for cutoff in (1, 3, 5, 10):
        recalls = []
        ndcgs = []
        for run in successful:
            golden = set(labels[run.query_id].relevant_pages)
            ranked = run.ranked_pages[:cutoff]
            recalls.append(len(golden.intersection(ranked)) / len(golden))
            gains = [1.0 if page in golden else 0.0 for page in ranked]
            dcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, 1))
            ideal = sum(
                1 / math.log2(rank + 1)
                for rank in range(1, min(len(golden), cutoff) + 1)
            )
            ndcgs.append(dcg / ideal if ideal else 0)
        metrics[f"recall_at_{cutoff}"] = _mean(recalls)
        metrics[f"ndcg_at_{cutoff}"] = _mean(ndcgs)
    reciprocal_ranks = []
    for run in successful:
        golden = set(labels[run.query_id].relevant_pages)
        first = next(
            (rank for rank, page in enumerate(run.ranked_pages, 1) if page in golden),
            None,
        )
        reciprocal_ranks.append(1 / first if first else 0)
    metrics.update(
        {
            "mrr": _mean(reciprocal_ranks),
            "correct_page_rate": _mean(
                [
                    float(
                        bool(
                            set(labels[run.query_id].relevant_pages).intersection(
                                run.ranked_pages
                            )
                        )
                    )
                    for run in successful
                ]
            ),
            "citation_page_accuracy": _mean(
                [
                    float(
                        bool(run.ranked_pages)
                        and run.ranked_pages[0] == labels[run.query_id].citation_page
                    )
                    for run in successful
                ]
            ),
            "query_ms_p50": _percentile([run.query_ms for run in successful], 50),
            "query_ms_p95": _percentile([run.query_ms for run in successful], 95),
            "indexing_ms_mean": _mean([run.indexing_ms for run in successful]),
            "storage_bytes_max": max(
                (run.storage_bytes for run in successful), default=0
            ),
            "page_embedding_ms_mean": _mean(
                [
                    run.page_embedding_ms
                    for run in successful
                    if run.page_embedding_ms is not None
                ]
            ),
            "visual_gpu_memory_mb_max": max(
                (
                    run.gpu_memory_mb
                    for run in successful
                    if run.gpu_memory_mb is not None
                ),
                default=0,
            ),
            "cold_start_ms_mean": _mean(
                [
                    run.cold_start_ms
                    for run in successful
                    if run.cold_start_ms is not None
                ]
            ),
            "patch_vector_count_max": max(
                (
                    run.patch_vector_count
                    for run in successful
                    if run.patch_vector_count is not None
                ),
                default=0,
            ),
            "fusion_ms_mean": _mean(
                [run.fusion_ms for run in successful if run.fusion_ms is not None]
            ),
            "slices": {
                "high_ocr_difficulty": _score_slice(
                    [
                        run
                        for run in successful
                        if labels[run.query_id].ocr_difficulty == "high"
                    ],
                    labels,
                ),
                "visual_layout_dependent": _score_slice(
                    [
                        run
                        for run in successful
                        if labels[run.query_id].visual_layout_dependency
                    ],
                    labels,
                ),
                "query_kind": {
                    kind: _score_slice(
                        [
                            run
                            for run in successful
                            if labels[run.query_id].query_kind == kind
                        ],
                        labels,
                    )
                    for kind in QueryKind.__args__
                },
            },
        }
    )
    return metrics


def _score_slice(
    runs: list[RetrievalRun], labels: dict[str, ScannedMathQuery]
) -> dict[str, float | int]:
    recall = []
    ndcg = []
    citations = []
    for run in runs:
        label = labels[run.query_id]
        golden = set(label.relevant_pages)
        ranked5 = run.ranked_pages[:5]
        ranked10 = run.ranked_pages[:10]
        recall.append(len(golden.intersection(ranked5)) / len(golden))
        gains = [1.0 if page in golden else 0.0 for page in ranked10]
        dcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, 1))
        ideal = sum(
            1 / math.log2(rank + 1) for rank in range(1, min(len(golden), 10) + 1)
        )
        ndcg.append(dcg / ideal if ideal else 0)
        citations.append(
            float(bool(run.ranked_pages) and run.ranked_pages[0] == label.citation_page)
        )
    return {
        "observation_count": len(runs),
        "recall_at_5": _mean(recall),
        "ndcg_at_10": _mean(ndcg),
        "citation_page_accuracy": _mean(citations),
    }


def _load_jsonl(path: Path, model: type[BaseModel]):
    output = []
    for line_number, line in enumerate(path.read_text("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            output.append(model.model_validate_json(line))
        except Exception as exc:
            raise ValueError(f"Invalid record at {path}:{line_number}") from exc
    if not output:
        raise ValueError(f"Dataset file is empty: {path}")
    return output


def _safe_pdf_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if (
        root.resolve() not in path.parents
        or path.suffix.lower() != ".pdf"
        or not path.is_file()
    ):
        raise ValueError("Manifest PDF must be an existing .pdf inside dataset_dir")
    return path


def _command_version(command: str, *args: str) -> str | None:
    binary = shutil.which(command)
    if binary is None:
        return None
    result = subprocess.run(
        [binary, *args], capture_output=True, text=True, check=False, timeout=15
    )
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0][:300] if result.returncode == 0 and output else None


def _module_available(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


def _pymupdf_version() -> str | None:
    try:
        import fitz

        return str(fitz.VersionBind)
    except ImportError:
        return None


def _skipped(reason: str, environment: dict[str, object]) -> dict[str, object]:
    return {
        "status": "skipped",
        "reason": reason,
        "real_external_ocr": False,
        "environment": environment,
    }


def _mean(values) -> float:
    values = list(values)
    return statistics.fmean(values) if values else 0


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile / 100
    lower, upper = math.floor(rank), math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)
