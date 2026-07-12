from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RetrievalVariant = Literal["dense", "hybrid", "ocr_hybrid", "visual", "dual"]


class RetrievalObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ranked_pages: list[int] = Field(default_factory=list)
    indexing_ms: float = Field(ge=0)
    query_ms: float = Field(ge=0)
    storage_bytes: int = Field(ge=0)
    failed: bool = False


class PDFRetrievalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    category: str
    pdf_type: Literal["born_digital", "scanned", "mixed"]
    query_kind: Literal[
        "concept",
        "theorem",
        "proof",
        "formula",
        "figure",
        "table",
        "ocr_error",
        "exact_section",
    ]
    golden_pages: list[int] = Field(min_length=1)
    expected_citation_page: int
    observations: dict[RetrievalVariant, RetrievalObservation]

    @model_validator(mode="after")
    def validate_variants(self) -> "PDFRetrievalCase":
        required = {"dense", "hybrid", "ocr_hybrid", "visual", "dual"}
        if set(self.observations) != required:
            raise ValueError("Every case must contain all retrieval variants")
        if self.expected_citation_page not in self.golden_pages:
            raise ValueError("Citation page must be one of the golden pages")
        return self


def load_pdf_retrieval_dataset(path: Path) -> list[PDFRetrievalCase]:
    cases: list[PDFRetrievalCase] = []
    seen: set[str] = set()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            case = PDFRetrievalCase.model_validate_json(line)
        except Exception as exc:
            raise ValueError(
                f"Invalid PDF retrieval case at line {line_number}"
            ) from exc
        if case.case_id in seen:
            raise ValueError(f"Duplicate PDF retrieval case: {case.case_id}")
        seen.add(case.case_id)
        cases.append(case)
    if not cases:
        raise ValueError("PDF retrieval dataset is empty")
    return cases


def evaluate_pdf_retrieval(
    cases: list[PDFRetrievalCase], *, top_k: int = 5
) -> dict[str, object]:
    if top_k < 1:
        raise ValueError("top_k must be positive")
    variants: dict[str, dict[str, float | int]] = {}
    for variant in ("dense", "hybrid", "ocr_hybrid", "visual", "dual"):
        recall: list[float] = []
        reciprocal_ranks: list[float] = []
        ndcg: list[float] = []
        correct_pages = 0
        citation_pages = 0
        query_latencies: list[float] = []
        indexing_latencies: list[float] = []
        storage = 0
        failures = 0
        for case in cases:
            observation = case.observations[variant]  # type: ignore[index]
            if observation.failed:
                failures += 1
                continue
            ranked = observation.ranked_pages[:top_k]
            golden = set(case.golden_pages)
            hits = [page in golden for page in ranked]
            recall.append(len(golden.intersection(ranked)) / len(golden))
            first_rank = next((index for index, hit in enumerate(hits, 1) if hit), None)
            reciprocal_ranks.append(1 / first_rank if first_rank else 0)
            gains = [1.0 if hit else 0.0 for hit in hits]
            dcg = sum(
                gain / math.log2(index + 1) for index, gain in enumerate(gains, 1)
            )
            ideal_hits = min(len(golden), top_k)
            ideal = sum(1 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
            ndcg.append(dcg / ideal if ideal else 0)
            correct_pages += int(any(hits))
            citation_pages += int(
                bool(ranked) and ranked[0] == case.expected_citation_page
            )
            query_latencies.append(observation.query_ms)
            indexing_latencies.append(observation.indexing_ms)
            storage += observation.storage_bytes
        successes = len(cases) - failures
        variants[variant] = {
            "case_count": len(cases),
            "success_count": successes,
            "failure_count": failures,
            f"recall_at_{top_k}": _mean(recall),
            "mrr": _mean(reciprocal_ranks),
            "ndcg": _mean(ndcg),
            "correct_page_rate": correct_pages / successes if successes else 0,
            "citation_page_accuracy": citation_pages / successes if successes else 0,
            "indexing_ms_mean": _mean(indexing_latencies),
            "query_ms_p50": _percentile(query_latencies, 50),
            "query_ms_p95": _percentile(query_latencies, 95),
            "storage_bytes": storage,
            "failure_rate": failures / len(cases),
        }
    return {
        "dataset": {
            "case_count": len(cases),
            "fixture_based": True,
            "external_ocr_executed": False,
            "real_visual_model_executed": False,
        },
        "top_k": top_k,
        "variants": variants,
        "recommendation": _recommend(variants, top_k),
    }


def write_pdf_retrieval_reports(
    report: dict[str, object], *, json_path: Path, markdown_path: Path
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    variants = report["variants"]
    assert isinstance(variants, dict)
    top_k = report["top_k"]
    lines = [
        "# Legacy PDF Retrieval Evaluation",
        "",
        "> Offline fixture benchmark only. No external OCR or real visual model was executed.",
        "",
        f"| Variant | Recall@{top_k} | MRR | nDCG | Correct page | Citation page | Query p50 | Query p95 | Storage | Failures |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, value in variants.items():
        assert isinstance(value, dict)
        lines.append(
            f"| {name} | {value[f'recall_at_{top_k}']:.3f} | "
            f"{value['mrr']:.3f} | {value['ndcg']:.3f} | "
            f"{value['correct_page_rate']:.3f} | "
            f"{value['citation_page_accuracy']:.3f} | "
            f"{value['query_ms_p50']:.1f} ms | {value['query_ms_p95']:.1f} ms | "
            f"{value['storage_bytes']} B | {value['failure_count']} |"
        )
    lines.extend(["", f"Recommendation: **{report['recommendation']}**", ""])
    markdown_path.write_text("\n".join(lines), encoding="utf-8")


def _recommend(variants: dict[str, dict[str, float | int]], top_k: int) -> str:
    hybrid = float(variants["hybrid"][f"recall_at_{top_k}"])
    dense = float(variants["dense"][f"recall_at_{top_k}"])
    visual = float(variants["visual"][f"recall_at_{top_k}"])
    dual = float(variants["dual"][f"recall_at_{top_k}"])
    if hybrid > dense and dual > hybrid and visual > dense:
        return "keep_visual_experimental_pending_real_model_validation"
    return "text_hybrid_only"


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile / 100
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)
