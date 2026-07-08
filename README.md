# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings by default, optional
real Zhipu embeddings, RAG, memory, Library metadata, Notes, and a
Tauri + React desktop frontend.

## Current Stage

Stage 40: Citation Formatting and Answer Grounding Polish.

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
born-digital math-PDF chunks with lightweight heading metadata. Stage 40
polishes answer grounding and normalizes local RAG citation formatting:

```text
PDF -> page-aware extraction -> section classification -> math-PDF chunking
    -> heading metadata -> Zhipu embeddings -> pgvector
    -> body-default retrieval -> DeepSeek answer with [S#] citations
    -> normalized Sources metadata
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

## What Stage 40 Does

- Reuses the existing embedding and LLM provider abstractions.
- Keeps `LLM_PROVIDER=deterministic` as the default with no API keys or
  network calls.
- Keeps `EMBEDDING_PROVIDER=mock` as the default for tests and local
  deterministic runs.
- Preserves existing Zhipu embedding, DeepSeek answer generation,
  chunking, section filtering, and pgvector retrieval behavior.
- Keeps `scripts/index_pdf.py`, `scripts/search_book.py`, and
  `scripts/eval_retrieval.py` working without changing their retrieval
  behavior.
- Labels retrieved prompt context with deterministic `[S1]`, `[S2]`,
  `[S3]` source IDs.
- Instructs real LLM answers to cite book-supported claims with the
  same `[S#]` IDs shown in the Sources list.
- Instructs the LLM to say when retrieved context is weak, indirect, or
  insufficient, and to distinguish explanatory rephrasing from claims
  explicitly supported by the book.
- Carries existing `section_type`, `chapter_title`, and `section_title`
  metadata into structured citation responses when available.
- Prints a normalized `Sources` list from `scripts/ask_book.py` with
  title, page/range, chunk index, section metadata, and score.
- Keeps `/api/agent/chat` request and response compatibility.
- Adds tests with mocked providers/clients only; no real API key is
  required for tests.

Manual single-book smoke test:

```bash
conda activate pla
cd backend
alembic upgrade head
python scripts/index_pdf.py "../Analysis.pdf" --reindex
python scripts/eval_retrieval.py --library-item-id <library_item_id> \
  --top-k 5
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

## What Stage 40 Does Not Do

No frontend changes, settings UI, auth/user accounts, tool-calling
framework, autonomous planner, web browsing implementation, new RAG
algorithm, BM25/hybrid search/reranking, OCR, PDF annotation, or
frontend PDF viewer changes. `scripts/search_book.py` does not call the
LLM provider or generate answers. `scripts/eval_retrieval.py` does not
call the LLM provider, change chunking, or add a complex benchmark
framework. Stage 40 does not change database schema, chunking,
embedding providers, LLM provider boundaries, retrieval ranking,
LangGraph topology, frontend behavior, web research behavior, complex
theorem/definition/proof parsing, ML-based layout parsing, OCR,
reranking, or hybrid search.

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
