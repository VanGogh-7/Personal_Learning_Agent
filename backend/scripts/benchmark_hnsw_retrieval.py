"""Benchmark exact and HNSW 1024-d retrieval in an isolated unlogged table."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
import statistics
import time
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_database_url

TABLE = "pla_stage64d_hnsw_benchmark"
HNSW_INDEX = f"{TABLE}_embedding_hnsw"
FTS_INDEX = f"{TABLE}_fts"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--sizes", default="10000,50000,100000,300000")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--ef-search", type=int, default=40)
    parser.add_argument("--keep-table", action="store_true")
    return parser.parse_args()


def _vector_for(value: int) -> str:
    head = [
        (value % 10007) / 10007,
        (value % 10009) / 10009,
        (value % 10037) / 10037,
        (value % 10039) / 10039,
    ]
    return "[" + ",".join([*(f"{item:.8f}" for item in head), *(["0"] * 1020)]) + "]"


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def _timed_ids(
    connection, sql: str, params: dict[str, Any], runs: int
) -> tuple[list[int], dict[str, float]]:
    samples: list[float] = []
    ids: list[int] = []
    for _ in range(runs):
        started = time.perf_counter()
        ids = [int(row[0]) for row in connection.execute(text(sql), params)]
        samples.append((time.perf_counter() - started) * 1000)
    return ids, {
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(_percentile(samples, 0.95), 3),
    }


def _plan(connection, sql: str, params: dict[str, Any]) -> dict[str, Any]:
    payload = connection.execute(
        text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"), params
    ).scalar_one()
    root = payload[0]
    nodes: list[str] = []

    def visit(node: dict[str, Any]) -> None:
        nodes.append(str(node.get("Node Type")))
        if node.get("Index Name"):
            nodes.append(str(node["Index Name"]))
        for child in node.get("Plans", []):
            visit(child)

    visit(root["Plan"])
    return {
        "execution_ms": round(float(root["Execution Time"]), 3),
        "planning_ms": round(float(root["Planning Time"]), 3),
        "nodes": nodes,
    }


def run_benchmark(sizes: list[int], runs: int, ef_search: int) -> list[dict[str, Any]]:
    engine = create_engine(get_database_url(), future=True)
    reports: list[dict[str, Any]] = []
    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        connection.execute(
            text(
                f"CREATE UNLOGGED TABLE {TABLE} ("
                "id bigint PRIMARY KEY, library_id integer NOT NULL, "
                "content text NOT NULL, embedding vector(1024) NOT NULL)"
            )
        )
    for size in sizes:
        target = size // 2 + 17
        query = _vector_for(target)
        topic = f"topic{target % 1000}"
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {TABLE}"))
            connection.execute(
                text(
                    f"INSERT INTO {TABLE} (id, library_id, content, embedding) "
                    "SELECT i, (i % 100)::integer, 'topic' || (i % 1000), "
                    "(ARRAY[(i % 10007)::real / 10007, "
                    "(i % 10009)::real / 10009, "
                    "(i % 10037)::real / 10037, "
                    "(i % 10039)::real / 10039] || "
                    "array_fill(0::real, ARRAY[1020]))::vector(1024) "
                    "FROM generate_series(1, :size) AS i"
                ),
                {"size": size},
            )
            connection.execute(text(f"DROP INDEX IF EXISTS {HNSW_INDEX}"))
            connection.execute(text(f"DROP INDEX IF EXISTS {FTS_INDEX}"))
            started = time.perf_counter()
            connection.execute(
                text(
                    f"CREATE INDEX {HNSW_INDEX} ON {TABLE} "
                    "USING hnsw (embedding vector_l2_ops)"
                )
            )
            build_seconds = time.perf_counter() - started
            connection.execute(
                text(
                    f"CREATE INDEX {FTS_INDEX} ON {TABLE} USING gin "
                    "(to_tsvector('simple', content))"
                )
            )
            connection.execute(text(f"ANALYZE {TABLE}"))
            index_bytes = connection.execute(
                text("SELECT pg_relation_size(:name)"), {"name": HNSW_INDEX}
            ).scalar_one()

        exact_sql = (
            f"SELECT id FROM {TABLE} "
            "ORDER BY embedding <-> CAST(:query AS vector(1024)) LIMIT 10"
        )
        ann_sql = exact_sql
        selected_one_sql = (
            f"SELECT id FROM {TABLE} WHERE library_id = :library_id "
            "ORDER BY embedding <-> CAST(:query AS vector(1024)) LIMIT 10"
        )
        selected_five_sql = (
            f"SELECT id FROM {TABLE} WHERE library_id IN (0,1,2,3,4) "
            "ORDER BY embedding <-> CAST(:query AS vector(1024)) LIMIT 10"
        )
        hybrid_sql = f"""
            WITH dense AS MATERIALIZED (
              SELECT id, row_number() OVER (
                ORDER BY embedding <-> CAST(:query AS vector(1024))
              ) AS rank
              FROM {TABLE}
              ORDER BY embedding <-> CAST(:query AS vector(1024)) LIMIT 40
            ), keyword AS MATERIALIZED (
              SELECT id, row_number() OVER (ORDER BY id) AS rank
              FROM {TABLE}
              WHERE to_tsvector('simple', content) @@ websearch_to_tsquery('simple', :topic)
              LIMIT 40
            )
            SELECT id FROM (
              SELECT id, sum(score) AS score FROM (
                SELECT id, 1.0 / (60 + rank) AS score FROM dense
                UNION ALL
                SELECT id, 1.0 / (60 + rank) AS score FROM keyword
              ) candidates GROUP BY id
            ) fused ORDER BY score DESC LIMIT 10
        """
        params = {"query": query, "topic": topic, "library_id": target % 100}
        with engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(text("SET LOCAL enable_indexscan = off"))
            connection.execute(text("SET LOCAL enable_bitmapscan = off"))
            exact_ids, exact_timing = _timed_ids(connection, exact_sql, params, runs)
            exact_plan = _plan(connection, exact_sql, params)
            selected_one_ids, selected_one_timing = _timed_ids(
                connection, selected_one_sql, params, runs
            )
            selected_five_ids, selected_five_timing = _timed_ids(
                connection, selected_five_sql, params, runs
            )
            transaction.rollback()

        with engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(text(f"SET LOCAL hnsw.ef_search = {ef_search}"))
            ann_ids, ann_timing = _timed_ids(connection, ann_sql, params, runs)
            ann_plan = _plan(connection, ann_sql, params)
            _, hybrid_timing = _timed_ids(connection, hybrid_sql, params, runs)
            hybrid_plan = _plan(connection, hybrid_sql, params)
            transaction.rollback()
        overlap = len(set(exact_ids) & set(ann_ids))
        first_exact = exact_ids[0] if exact_ids else None
        reciprocal_rank = (
            1.0 / (ann_ids.index(first_exact) + 1) if first_exact in ann_ids else 0.0
        )
        reports.append(
            {
                "vectors": size,
                "index_build_seconds": round(build_seconds, 3),
                "index_bytes": int(index_bytes),
                "recall_at_10": round(overlap / max(1, len(exact_ids)), 3),
                "mrr": round(reciprocal_rank, 3),
                "exact": exact_timing,
                "hnsw": ann_timing,
                "selected_1_exact": selected_one_timing,
                "selected_5_exact": selected_five_timing,
                "hybrid": hybrid_timing,
                "exact_plan": exact_plan,
                "hnsw_plan": ann_plan,
                "hybrid_plan": hybrid_plan,
            }
        )
    engine.dispose()
    return reports


def main() -> int:
    args = _parse_args()
    if not args.confirm:
        print("Refusing to allocate benchmark data without --confirm.")
        return 2
    sizes = [int(value) for value in args.sizes.split(",") if value.strip()]
    try:
        reports = run_benchmark(sizes, args.runs, args.ef_search)
        print(json.dumps(reports, indent=2))
    finally:
        if not args.keep_table:
            engine = create_engine(get_database_url(), future=True)
            with engine.begin() as connection:
                connection.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
