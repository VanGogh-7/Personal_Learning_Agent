# Stage 62 real scanned-mathematics dataset

This directory defines the local, human-labelled evaluation contract. Real PDFs,
queries derived from copyrighted page content, rendered pages, OCR output, model
weights, and generated reports are deliberately not committed.

A runnable dataset contains:

```text
<dataset-dir>/
  manifest.json
  queries.jsonl
  books/
    *.pdf
```

`manifest.json` must declare 3–5 genuinely scanned mathematics books, their
SHA-256 digests, source/permission notes, immutable development/held-out splits,
and collective coverage of rotated pages, skew, blur/low contrast, two columns,
formula-heavy pages, mixed text/scans, headers/footers, contents, and indexes.
Set `annotation_status` to `sealed` only after a second human pass.

`queries.jsonl` must contain at least 50 human-authored records. Every record
contains `query_id`, `book_id`, `query`, one of the required query kinds,
`relevant_pages`, one or more `relevant_regions`, `expected_section`,
`citation_page`, `ocr_difficulty`, `visual_layout_dependency`, and the same split
as its book. Held-out books and labels must never be used for tuning.

The loader intentionally rejects placeholders, missing PDF files, checksum
mismatches, incomplete category coverage, fewer than 50 queries, fewer than
three books, draft annotations, and mixed split labels. This prevents a fixture
or tuning set from being reported as the requested real evaluation.

Probe dependencies without running tools:

```bash
python scripts/evaluate_stage62.py --probe-environment \
  --json-report evals/reports/stage62-environment.json
```

Run real Tesseract + OCRmyPDF only after installing them and assembling the
sealed dataset:

```bash
PLA_EXTERNAL_OCR_TESTS=true python scripts/evaluate_stage62.py \
  --dataset-dir /absolute/private/scanned-math \
  --run-ocr --confirm-external-tools \
  --json-report evals/reports/stage62-ocr.json
```

Run the single selected visual implementation, ColQwen2, with audited weights
already present locally. The command never downloads weights and uses brute-force
late interaction rather than adding an ANN index:

```bash
PLA_VISUAL_GPU_TESTS=true python scripts/evaluate_stage62.py \
  --dataset-dir /absolute/private/scanned-math \
  --run-visual --local-colqwen2-model /absolute/local/weights \
  --visual-observations evals/reports/stage62-visual.jsonl \
  --confirm-external-tools --json-report evals/reports/stage62-visual-run.json
```

Text observations must use the same held-out query IDs and the variants `dense`,
`postgres_fts`, `hybrid`, `reranked`, and `parent_context`. PostgreSQL FTS is
PostgreSQL full-text search, not complete BM25. Dual observations must be created
with rank-based fusion (the evaluator exports reciprocal-rank fusion); raw text
and visual scores must never be mixed.
