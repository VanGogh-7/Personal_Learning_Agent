# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings by default, optional
real Zhipu embeddings, RAG, memory, Library metadata, Notes, and a
Tauri + React desktop frontend.

## Current Stage

Stage 39: Chunk Optimization v1 for Mathematical PDFs.

The frontend now uses Bun + Tauri + React + Vite and opens to a
PDF-centered learning workspace:

```text
Bun + Tauri + React + Vite
PDF Library Explorer | Embedded PDF Workspace | Agent Chat
```

Stage 36 wires the existing OpenAI-compatible LLM provider boundary into
the Agent Chat synthesis path. Stage 36A adds a real Zhipu embedding
provider and backend-only scripts for a single-book PDF RAG smoke test.
Stage 36C adds retrieval-only search output for inspecting single-book
RAG quality before answer generation. Stage 37 adds a small repeatable
retrieval eval query set for comparing future retrieval changes.
Stage 38A classifies chunks by section type and excludes known front/back
matter from default retrieval. Stage 38B polishes the manual reindex and
filtered retrieval baseline workflow. Stage 39 adds larger readable
born-digital math-PDF chunks with lightweight heading metadata:

```text
PDF -> page-aware extraction -> section classification -> math-PDF chunking
    -> heading metadata -> Zhipu embeddings -> pgvector
    -> body-default retrieval -> DeepSeek answer -> citations
```

Deterministic/mock mode remains the default for local development and
tests. Real Zhipu and DeepSeek modes are enabled only through backend
`.env` configuration and secrets stay backend-only.

## Configuration

Use the `pla` conda environment for backend work. The backend runs on
`127.0.0.1:8081`, and the frontend connects to
`http://127.0.0.1:8081`.

Backend local configuration lives in `backend/.env`, which is
automatically loaded for local FastAPI startup and Alembic migrations.
Example placeholders are tracked in `backend/.env.example` only:

```env
LLM_PROVIDER=deterministic
EMBEDDING_PROVIDER=mock
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
ZHIPU_API_KEY=your_zhipu_api_key_here
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZHIPU_EMBEDDING_MODEL=embedding-3
ZHIPU_EMBEDDING_DIMENSION=2048
```

Real single-book smoke mode is opt-in:

```env
EMBEDDING_PROVIDER=zhipu
LLM_PROVIDER=deepseek
```

Do not commit real `.env` files or expose API keys to the frontend.

## What Stage 39 Does

- Reuses the existing embedding and LLM provider abstractions.
- Keeps `LLM_PROVIDER=deterministic` as the default with no API keys or
  network calls.
- Keeps `EMBEDDING_PROVIDER=mock` as the default for tests and local
  deterministic runs.
- Supports `LLM_PROVIDER=deepseek` through the existing
  OpenAI-compatible provider.
- Supports `EMBEDDING_PROVIDER=zhipu` for 2048-dimensional
  `embedding-3` vectors.
- Adds backend scripts to index one local PDF and ask one indexed book.
- Adds `scripts/search_book.py` to print ranked retrieved chunks without
  LLM answer generation.
- Adds `scripts/retrieval_eval_queries.json` and
  `scripts/eval_retrieval.py` for a lightweight retrieval-only baseline
  with keyword hit summaries.
- Adds `document_chunks.section_type` metadata and lightweight PDF page
  heuristics for `body`, `contents`, `index`, `bibliography`, `preface`,
  and `unknown`.
- Excludes known non-body chunks from default retrieval, with
  `--include-non-body` on retrieval scripts for debugging.
- Keeps `scripts/index_pdf.py --reindex` on the same resolved PDF path
  from creating duplicate Library items and prints section-type counts.
- Extends `scripts/eval_retrieval.py` summary output with `top_k`,
  aggregate page/snippet coverage, section-type counts, and non-body
  retrieved count.
- Uses PDF-specific chunking defaults tuned for mathematical textbooks:
  about 4000 characters per chunk, about 650 characters of overlap, and
  a 350-character minimum tail target.
- Combines short adjacent PDF pages where possible while preserving
  `page_start` and `page_end` for citations.
- Adds nullable `document_chunks.chapter_title` and
  `document_chunks.section_title` metadata populated from obvious
  chapter/section headings and page headers.
- Keeps `/api/agent/chat` request and response compatibility.
- Adds tests with mocked providers/clients only; no real API key is
  required for tests.
- Adds a minimal Alembic migration that changes `document_chunks.embedding`
  to `vector(2048)`. Existing stored chunks are deleted and affected books
  should be re-indexed.

Manual single-book smoke test:

```bash
conda activate pla
cd backend
alembic upgrade head
python scripts/index_pdf.py "../Analysis.pdf" --reindex
python scripts/eval_retrieval.py --library-item-id <library_item_id> \
  --top-k 5 2>&1 | tee stage39_analysis1_chunk_optimized_baseline.txt
python scripts/search_book.py --library-item-id <library_item_id> \
  "complete metric spaces"
python scripts/ask_book.py --library-item-id <library_item_id> \
  "What does this book say about completeness, Banach spaces, or metric spaces? Answer with citations."
```

The long-term product direction is:

```text
PDF is the main workspace.
Library is a collapsible PDF file explorer.
Agent Chat is a dockable/collapsible assistant.
Today Log is the learning record; Calendar remains future expansion.
Settings will stay simple: theme + long-term memory only.
```

## What Stage 39 Does Not Do

No frontend changes, settings UI, auth/user accounts, tool-calling
framework, autonomous planner, web browsing implementation, new RAG
algorithm, BM25/hybrid search/reranking, OCR, PDF annotation, or
frontend PDF viewer changes. `scripts/search_book.py` does not call the
LLM provider or generate answers. `scripts/eval_retrieval.py` does not
call the LLM provider, change chunking, or add a complex benchmark
framework. Stage 39 does not add complex theorem/definition/proof
parsing, ML-based document layout parsing, OCR, reranking, hybrid
search, provider changes, frontend changes, or retrieval ranking
changes.

## Commands

Install/update backend dependencies:

```bash
conda activate pla
cd backend
pip install -r requirements.txt
```

Backend tests:

```bash
conda activate pla
cd backend
pytest
```

Frontend build:

```bash
cd frontend
bun install
bun run build
```

See `backend/README.md` and `frontend/README.md` for detailed setup and
development notes.
