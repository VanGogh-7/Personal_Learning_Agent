# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings by default, optional
real Zhipu embeddings, RAG, memory, Library metadata, Notes, and a
Tauri + React desktop frontend.

## Current Stage

Stage 44: Managed PDF Storage and Library Item Robustness.

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
polishes answer grounding and normalizes local RAG citation formatting.
Stage 41 makes `/api/agent/chat` accept the simplified product request
shape expected by the final Agent Chat. Stage 42 updates the right
Agent Chat dock to use that product API as a clean chat box for the
currently selected PDF context. Stage 43 adds the left Library
Explorer product flow for adding PDFs through the desktop file picker
and indexing them through the existing backend pipeline. Stage 44 copies
imported PDFs into backend-managed Library storage before indexing so
imported items do not depend on the original selected file path:

```text
PDF -> page-aware extraction -> section classification -> math-PDF chunking
    -> heading metadata -> Zhipu embeddings -> pgvector
    -> body-default retrieval -> DeepSeek answer with [S#] citations
    -> normalized Sources metadata -> product Agent Chat response
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
LIBRARY_STORAGE_DIR=storage/library
```

Real single-book smoke mode is opt-in:

```env
EMBEDDING_PROVIDER=zhipu
LLM_PROVIDER=deepseek
```

Do not commit real `.env` files or expose API keys to the frontend.

## What Stage 44 Does

- Keeps the existing IDE-like layout: PDF Library Explorer, embedded
  PDF Workspace, and right Agent Chat dock.
- Adds backend-managed PDF storage, configurable with
  `LIBRARY_STORAGE_DIR` and defaulting to `backend/storage/library`.
- Ensures `backend/storage/` is gitignored so imported PDFs are not
  committed.
- Adds a backend `POST /api/library/import-pdfs` path that validates
  selected PDFs, copies them into managed storage with collision-safe
  names, creates Library items, and indexes from the managed copy.
- Reuses the backend PDF extraction, chunking, embedding, pgvector
  storage, and section metadata pipeline.
- Preserves original title/filename metadata while using the managed
  copy path for Library items, documents, embedded viewing, reindexing,
  and "Open in system PDF reader".
- Lets duplicate imports create separate managed copies rather than
  corrupting existing Library items.
- Keeps the frontend Add PDFs flow, Library refresh, Workspace viewer,
  and selected-PDF Agent Chat context working.
- Refreshes the Library list after indexing and selects the newly
  indexed PDF so it opens in the center Workspace.

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

## What Stage 44 Does Not Do

No Settings UI, embedding provider settings, local embedding provider,
database schema changes, chunking/retrieval/citation changes, reranking,
hybrid search, LangGraph topology changes, web search expansion, PDF
viewer redesign, citation-to-page navigation, OCR, annotations,
auth/user accounts, tool-calling framework, or autonomous planner.
Stage 44 does not reintroduce low-level RAG/debug controls in Agent Chat.

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
