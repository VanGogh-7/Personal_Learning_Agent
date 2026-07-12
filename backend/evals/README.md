# Adaptive Graph Evaluation

`adaptive_graph.jsonl` is the versioned, human-labelled Stage 58 golden set.
Each JSONL record validates against `AdaptiveEvaluationCase` and labels intent,
required sources, fixed execution mode, clarification, answer mode, evidence
expectation, and citation expectation. Selected cases also contain synthetic
evidence, correction cost, and citation fixtures. Golden labels—not an LLM
judge—are the primary standard.

Run the deterministic offline evaluation:

```bash
conda activate pla
cd backend
python scripts/evaluate_adaptive_graph.py \
  --dataset evals/adaptive_graph.jsonl \
  --variant adaptive \
  --runs 3 \
  --json-report evals/reports/adaptive.json \
  --markdown-report evals/reports/adaptive.md
```

Compare variants by repeating the command with `direct_answer`, `local_only`,
`web_only`, `academic_only`, `single_source_adaptive`,
`multi_source_adaptive`, `correction_disabled`, `correction_retry_1`, or
`correction_retry_2`. Offline latency and call counts are explicitly labelled
as proxies. They do not replace the Stage 52/54 end-to-end TTFT, Provider,
retrieval, rendering, or persistence measurements.

Real DeepSeek QueryAnalysis evaluation is opt-in and consumes quota:

```bash
PLA_REAL_PROVIDER_TESTS=true python scripts/evaluate_adaptive_graph.py \
  --real-providers --confirm-costs --runs 3 \
  --input-cost-per-million <price> \
  --output-cost-per-million <price>
```

The real adapter uses temperature zero, requests a JSON object, records schema
validity, fallback, latency, stability, and Provider token usage when returned.
Pricing is never hard-coded; estimated cost remains null unless both rates are
provided. API keys remain in backend Settings and are never written to reports.

Evaluation-only experiments are available with `--grader llm-experimental`
and `--semantic-verifier llm-experimental`. They require the same explicit real
Provider confirmation and are not imported by the production graph. Generated
reports belong under `backend/evals/reports/`, which is ignored by Git.

## Stage 59 held-out set

`heldout/cases.jsonl` contains 50 unlabelled inputs whose IDs are disjoint from
the Stage 58 golden set. `heldout/labels.jsonl` contains route and evidence
goldens, while `heldout/claims.jsonl` contains 30 manually authored
claim-to-source support labels. This physical split is intentional: Provider
prompts are built only from the case input or the claim/source pair, never from
golden labels. Do not tune production rules against these files.

The offline runner validates schemas and isolation, scores QueryAnalysis,
deterministic evidence grading, structural citation checking, human evidence
quality labels, confusion matrices, failure categories, and report safety:

```bash
python scripts/evaluate_heldout_research.py --runs 3 \
  --json-report evals/reports/heldout.json \
  --markdown-report evals/reports/heldout.md
```

Run real DeepSeek temperature/stability and semantic-verifier experiments only
with explicit quota confirmation:

```bash
PLA_REAL_PROVIDER_TESTS=true python scripts/evaluate_heldout_research.py \
  --real-query --semantic-verifier --confirm-costs --runs 3 \
  --real-query-max-cases 12 \
  --input-cost-per-million <current-price> \
  --output-cost-per-million <current-price>
```

Real MCP evidence collection additionally requires `MCP_ENABLED=true`,
`MCP_REAL_TESTS=true`, and `--real-mcp`. It records latency, failures, fallback,
deduplication, and bounded normalized samples whose `human_annotation` remains
`pending`; a person must label relevance, authority, freshness, contradiction,
fetch need, citation readiness, and subquery coverage before claiming a quality
result. Missing credentials are a skip condition, never a reason to substitute
mock values.

Generated JSON omits questions, prompts, claim text, full source excerpts, and
secrets. p50/p95 use successful observations only; failures are counted
separately. Cost remains null unless current input/output prices are supplied.

The 2026-07-12 controlled real run used 12 category-balanced cases with two
repetitions for each temperature arm. The configured `deepseek-v4-pro` returned
valid schemas for all 48 QueryAnalysis calls, but repeated-run stability was
66.7%; route accuracy was 58.3% at temperature zero and 62.5% in the identical
production-temperature arm. This difference is sampling variation, not proof
that one identical setting is better. The 30-call semantic experiment measured
83.3% precision, 100% recall, 20% false positives, p50 2.82 s, and p95 5.30 s.
That result selects `keep deterministic only`; it does not wire the adapter into
production. Real MCP evidence sampling remains unexecuted because the MCP real
test switches were disabled.

## Stage 61 legacy-PDF retrieval set

`legacy_pdf_retrieval.jsonl` is a small, versioned offline set for comparing
dense, text-hybrid, OCR-text-hybrid, visual-page, and dual-index rankings. It
covers born-digital, scanned, mixed, formula, theorem/proof, figure, table, OCR
error, and exact-section cases. Each variant records ranked page IDs plus
fixture indexing latency, query latency, storage, and failure state.

Run:

```bash
python scripts/evaluate_pdf_rag.py \
  --dataset evals/legacy_pdf_retrieval.jsonl \
  --json-report evals/reports/pdf-rag.json \
  --markdown-report evals/reports/pdf-rag.md
```

The runner reports Recall@k, MRR, nDCG, correct-page rate, citation-page
accuracy, p50/p95 query latency, indexing mean, storage, and failures. These are
deterministic fixture observations for regression and architecture comparison;
they are not a real Tesseract, OCRmyPDF, ColPali/ColQwen, GPU, or production
corpus benchmark. Real external runs must use explicit `external_ocr` or
`visual_gpu` markers and document the model, hardware, corpus, and environment.

## Stage 62 real scanned-mathematics validation

Stage 62 keeps the Stage 61 fixture benchmark unchanged and adds a strict real
evaluation boundary under `scanned_math/`. Real PDFs and annotations remain
private and untracked. `app.evaluation.stage62` rejects datasets unless they are
sealed, checksum-valid, contain 3–5 books and at least 50 queries, separate
development from held-out books, and cover every required OCR/layout/query case.

`scripts/evaluate_stage62.py --probe-environment` is read-only. External OCR
requires both `PLA_EXTERNAL_OCR_TESTS=true` and `--confirm-external-tools`.
The single visual implementation is ColQwen2; it requires
`PLA_VISUAL_GPU_TESTS=true`, confirmation, CUDA, installed optional packages,
and an existing local model directory. It never downloads weights or creates an
ANN index. Reports call PostgreSQL FTS "PostgreSQL full-text search", never BM25.

Current observed environment, license/deployment risks, explicit skips, and the
production recommendation are recorded in `STAGE62_FINDINGS.md`.
