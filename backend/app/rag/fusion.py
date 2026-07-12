from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Sequence

from app.db.vector_search import SimilarChunkResult

FUSION_K = 60


def fuse_text_and_visual(
    text: Sequence[SimilarChunkResult],
    visual: Sequence[SimilarChunkResult],
    *,
    text_weight: float = 1.0,
    visual_weight: float = 0.7,
    limit: int = 5,
) -> list[SimilarChunkResult]:
    """RRF page/chunk candidates without adding incomparable raw scores."""
    candidates: dict[tuple[str, int | None], SimilarChunkResult] = {}
    scores: defaultdict[tuple[str, int | None], float] = defaultdict(float)
    for weight, results in ((text_weight, text), (visual_weight, visual)):
        for rank, result in enumerate(results, start=1):
            key = (str(result.document_id), result.page_start)
            candidates.setdefault(key, result)
            scores[key] += weight / (FUSION_K + rank)
    ranked = sorted(scores, key=lambda key: (-scores[key], key))[:limit]
    return [
        replace(candidates[key], distance=1.0 / (1.0 + scores[key] * 1000))
        for key in ranked
    ]
