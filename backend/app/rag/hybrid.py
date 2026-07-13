from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import replace
from difflib import SequenceMatcher
from time import perf_counter
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.vector_search import (
    DEFAULT_EXCLUDED_SECTION_TYPES,
    SimilarChunkResult,
    active_processing_filter,
    search_similar_chunks_for_documents,
)
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.observability.latency import current_latency_trace

RRF_K = 60
MAX_CANDIDATE_MULTIPLIER = 4


def hybrid_search_chunks(
    session: Session,
    *,
    question: str,
    query_embedding: Sequence[float],
    document_ids: Sequence[uuid.UUID],
    limit: int,
    exclude_section_types: Sequence[str] = DEFAULT_EXCLUDED_SECTION_TYPES,
    dense_weight: float = 1.0,
    keyword_weight: float = 1.0,
    force_ann: bool = False,
) -> list[SimilarChunkResult]:
    """Fuse dense and keyword ranks, then apply bounded deterministic reranking."""
    candidate_limit = min(100, max(limit, limit * MAX_CANDIDATE_MULTIPLIER))
    dense_started = perf_counter()
    dense = search_similar_chunks_for_documents(
        session,
        query_embedding,
        document_ids,
        limit=candidate_limit,
        exclude_section_types=exclude_section_types,
        force_ann=force_ann,
    )
    _record("dense_search", dense_started)
    keyword_started = perf_counter()
    keyword = keyword_search_chunks(
        session,
        question=question,
        document_ids=document_ids,
        limit=candidate_limit,
        exclude_section_types=exclude_section_types,
    )
    _record("keyword_search", keyword_started)
    fusion_started = perf_counter()
    fused = reciprocal_rank_fusion(
        dense,
        keyword,
        dense_weight=dense_weight,
        keyword_weight=keyword_weight,
    )
    _record("fusion", fusion_started)
    rerank_started = perf_counter()
    reranked = rerank_hybrid_candidates(question, fused)
    expanded = expand_parent_context(session, reranked[:limit])
    _record("rerank", rerank_started)
    return expanded


def keyword_search_chunks(
    session: Session,
    *,
    question: str,
    document_ids: Sequence[uuid.UUID],
    limit: int,
    exclude_section_types: Sequence[str],
) -> list[SimilarChunkResult]:
    if not document_ids:
        return []
    base = (
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.document_id.in_(list(document_ids)))
        .where(active_processing_filter())
    )
    if exclude_section_types:
        base = base.where(
            DocumentChunk.section_type.not_in(list(exclude_section_types))
        )
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        terms = _search_terms(question)
        if not terms:
            return []
        query = func.websearch_to_tsquery("simple", " ".join(terms))
        vector = func.to_tsvector(
            "simple",
            func.coalesce(DocumentChunk.chapter_title, "")
            + " "
            + func.coalesce(DocumentChunk.section_title, "")
            + " "
            + DocumentChunk.content,
        )
        rank = func.ts_rank_cd(vector, query)
        stmt = (
            base.add_columns(rank.label("keyword_rank"))
            .where(vector.op("@@")(query))
            .order_by(rank.desc())
            .limit(limit)
        )
        return [
            _to_result(chunk, max(0.0, 1.0 - float(rank_value)))
            for chunk, rank_value in session.execute(stmt).all()
        ]
    chunks = session.execute(base).scalars().all()
    scored = [(chunk, _keyword_score(question, chunk)) for chunk in chunks]
    scored = [(chunk, score) for chunk, score in scored if score > 0]
    scored.sort(key=lambda item: (-item[1], item[0].chunk_index))
    return [_to_result(chunk, 1.0 - min(score, 1.0)) for chunk, score in scored[:limit]]


def reciprocal_rank_fusion(
    dense: Sequence[SimilarChunkResult],
    keyword: Sequence[SimilarChunkResult],
    *,
    dense_weight: float,
    keyword_weight: float,
) -> list[tuple[SimilarChunkResult, float]]:
    candidates: dict[uuid.UUID, SimilarChunkResult] = {}
    scores: defaultdict[uuid.UUID, float] = defaultdict(float)
    for weight, results in ((dense_weight, dense), (keyword_weight, keyword)):
        for rank, result in enumerate(results, start=1):
            candidates.setdefault(result.chunk_id, result)
            scores[result.chunk_id] += weight / (RRF_K + rank)
    return sorted(
        ((candidates[chunk_id], score) for chunk_id, score in scores.items()),
        key=lambda item: (-item[1], item[0].chunk_index),
    )


def rerank_hybrid_candidates(
    question: str, candidates: Sequence[tuple[SimilarChunkResult, float]]
) -> list[SimilarChunkResult]:
    normalized_question = _normalize(question)
    theorem_numbers = set(
        re.findall(
            r"(?:theorem|lemma|proposition|section|§)\s*([\divxlc0-9.:-]+)",
            normalized_question,
        )
    )
    scored: list[tuple[SimilarChunkResult, float]] = []
    for result, fusion_score in candidates:
        text = _normalize(
            " ".join(
                value
                for value in (
                    result.chapter_title,
                    result.section_title,
                    result.content,
                )
                if value
            )
        )
        score = fusion_score
        if normalized_question and normalized_question in text:
            score += 0.04
        for number in theorem_numbers:
            if re.search(
                rf"(?:theorem|lemma|proposition|section|§)\s*{re.escape(number)}\b",
                text,
            ):
                score += 0.08
        query_terms = set(_search_terms(normalized_question))
        content_terms = set(_search_terms(text))
        if query_terms:
            score += 0.03 * len(query_terms & content_terms) / len(query_terms)
        if result.ocr_confidence is not None:
            score *= 0.75 + 0.25 * result.ocr_confidence
        scored.append((result, score))
    scored.sort(key=lambda item: (-item[1], item[0].chunk_index))
    return [
        replace(result, distance=1.0 / (1.0 + score * 1000)) for result, score in scored
    ]


def expand_parent_context(
    session: Session, results: Sequence[SimilarChunkResult]
) -> list[SimilarChunkResult]:
    parent_ids = [
        result.parent_chunk_id for result in results if result.parent_chunk_id
    ]
    parents = (
        {
            chunk.id: chunk
            for chunk in session.execute(
                select(DocumentChunk).where(DocumentChunk.id.in_(parent_ids))
            ).scalars()
        }
        if parent_ids
        else {}
    )
    output: list[SimilarChunkResult] = []
    for result in results:
        parent = parents.get(result.parent_chunk_id)
        if parent is None or parent.id == result.chunk_id:
            output.append(result)
            continue
        context = parent.content[:1200]
        output.append(
            replace(
                result,
                content=f"{result.content}\n\nParent section context:\n{context}",
            )
        )
    return output


def _keyword_score(question: str, chunk: DocumentChunk) -> float:
    query = _normalize(question)
    text = _normalize(
        " ".join(
            value
            for value in (chunk.chapter_title, chunk.section_title, chunk.content)
            if value
        )
    )
    query_terms = _search_terms(query)
    if not query_terms:
        return 0
    exact = 1.0 if query in text else 0.0
    overlap = sum(term in text for term in query_terms) / len(query_terms)
    fuzzy = max(
        (
            SequenceMatcher(None, term, candidate).ratio()
            for term in query_terms
            for candidate in _search_terms(text)
            if abs(len(term) - len(candidate)) <= 2
        ),
        default=0.0,
    )
    metadata = 0.0
    heading = _normalize(
        " ".join(filter(None, [chunk.chapter_title, chunk.section_title]))
    )
    if heading and any(term in heading for term in query_terms):
        metadata = 0.2
    return min(1.0, 0.55 * overlap + 0.2 * exact + 0.15 * fuzzy + metadata)


def _search_terms(value: str) -> list[str]:
    return list(
        dict.fromkeys(
            token.casefold()
            for token in re.findall(
                r"[A-Za-zÀ-žΑ-ω\u4e00-\u9fa50-9]+(?:[.:-][A-Za-z0-9]+)*", value
            )
            if len(token) > 1 or token.isdigit()
        )
    )[:24]


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _to_result(chunk: DocumentChunk, distance: float) -> SimilarChunkResult:
    return SimilarChunkResult(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        chunk_index=chunk.chunk_index,
        content=chunk.content,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        distance=distance,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        section_type=chunk.section_type,
        chapter_title=chunk.chapter_title,
        section_title=chunk.section_title,
        parent_chunk_id=chunk.parent_chunk_id,
        element_type=chunk.element_type,
        extraction_method=chunk.extraction_method,
        ocr_confidence=chunk.ocr_confidence,
        section_path=tuple(chunk.section_path or ()),
        bounding_boxes=tuple(chunk.bounding_boxes or ()),
    )


def _record(stage: str, started: float) -> None:
    trace = current_latency_trace()
    if trace is not None:
        trace.record(stage, (perf_counter() - started) * 1000)
