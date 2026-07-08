# Personal Learning Agent — Backend

## Purpose

Backend foundation for a local-first Personal Learning Agent that will
eventually help manage learning materials, notes, books, study progress,
and knowledge retrieval.

## Current Stage

Stage 36C: Single-Book RAG Observability Polish.

- FastAPI app with health/status endpoints (Stage 1, completed)
- Document ingestion MVP: text chunking and safe `.txt`/`.md` loading (Stage 2, completed)
- SQLAlchemy models + Alembic migrations for the initial schema (Stage 3, completed)
- pgvector/vector extension support via migration, a nullable `embedding`
  column on `document_chunks`, deterministic mock embeddings, and minimal
  vector persistence/search functions (Stage 4, completed)
- Minimal RAG Q&A: question → mock embedding → pgvector similarity search
  → simple deterministic extractive answer (Stage 5, completed)
- Short-term memory: bounded per-session conversation turns, used as
  simple deterministic context for the RAG answer (Stage 6, completed)
- Long-term memory: manually created memories, listable and
  keyword-searchable, optionally used as bounded deterministic RAG
  context (Stage 7, completed)
- Minimal Tauri + React + TypeScript frontend shell that calls the
  independently running local FastAPI backend for health/status, RAG
  query, and long-term memory create/list/search (Stage 8, completed)
- Backend/frontend integration polish: tighter frontend API types,
  centralized backend URL handling, safer fetch errors, clearer UI
  empty states, and local development docs cleanup (Stage 9, completed)
- Book Library MVP: manually register, list, update, archive, and
  search/filter book or learning-material metadata (Stage 10, completed)
- Open Local Files from Desktop App: the Tauri frontend can ask the
  operating system to open a library item's local `file_path` with the
  system default application (Stage 11, completed)
- Frontend Layout Redesign MVP: the React/Tauri frontend is organized
  into Chat, Library, and Notes pages with sidebar navigation (Stage 12,
  completed)
- Library Detail Page / Panel MVP: the Library page can select a
  library item and show structured metadata plus future placeholders
  without adding backend behavior (Stage 13, completed)
- Library Indexing MVP: a supported `.txt` or `.md` library item can be
  manually indexed into documents, chunks, and deterministic mock
  embeddings (Stage 14, completed)
- Book-Scoped RAG MVP: Chat/RAG can retrieve only chunks associated
  with one selected indexed Library item (Stage 15, completed)
- Notes MVP: database-backed LaTeX notes can be created, listed,
  viewed, edited, associated with Library items, and archived (Stage 16,
  completed)
- Generate LaTeX Notes from Chat: Chat/RAG responses can be converted
  into deterministic LaTeX note drafts and then saved through the
  existing Notes API (Stage 17, completed)
- Local Notes File Export: existing database-backed notes can be
  exported from the Tauri desktop app as local `.tex` files (Stage 18,
  completed)
- Notes Workspace MVP: the Tauri desktop app can remember a local Notes
  workspace folder and export selected notes into it with unique `.tex`
  filenames (Stage 19, completed)
- Open Exported Notes File: after manual or workspace Notes export, the
  Tauri desktop app can open the last successfully exported `.tex` file
  with the system default application (Stage 20, completed)
- Real LLM Integration Boundary: RAG answer generation now goes through
  a small LLM provider abstraction with deterministic mode by default
  and optional DeepSeek/OpenAI-compatible mode only when explicitly
  configured (Stage 21, completed)
- Better Retrieval / Citations / Chunk Metadata: global and book-scoped
  RAG responses include structured citation/source metadata for each
  retrieved chunk, and the frontend Chat page displays a compact Sources
  section (Stage 22, completed)
- Book Summary + Topic Extraction: indexed Library items can generate
  deterministic summary and topic tag drafts from representative indexed
  chunks, then save reviewed metadata through the existing Library
  update endpoint (Stage 23, completed)
- Learning History / Progress Timeline: selected Library, RAG, and
  Notes actions are recorded in a small `learning_events` table and
  exposed through list/filter APIs for the frontend Progress page
  (Stage 24, completed)
- Multi-Book RAG MVP: `POST /api/rag/query/library-items` retrieves
  only from multiple selected indexed Library items, returns selected
  item metadata plus structured citations, preserves memory behavior,
  and records `multi_book_rag_question_asked` events (Stage 25, completed)
- Chat RAG Graph Boundary MVP: `POST /api/agent/chat` runs a minimal
  LangGraph workflow that orchestrates existing validation, RAG
  retrieval, memory, citation, prompt, LLM provider, and learning-event
  services without replacing them (Stage 26, completed)
- Agent Chat Frontend Integration MVP: the frontend Chat flow uses
  `POST /api/agent/chat` while preserving global, single-book, and
  multi-book behavior (Stage 27, completed)
- Agent Chat Stabilization / Regression Polish: the frontend clarifies
  scope display, citations, empty states, common errors, loading states,
  and Chat-to-Notes compatibility (Stage 28, completed)
- Frontend Bun Migration: the frontend uses Bun for dependency
  management and script execution while keeping Tauri, React, Vite, and
  the existing app architecture unchanged (Stage 29A, completed)
- Workspace Layout Refactor MVP: the frontend now opens to a
  PDF-centered Workspace with a collapsible/resizable PDF Library
  Explorer, PDF Workspace placeholder, and docked Agent Chat panel
  (Stage 29B, completed)
- PDF-First Library UX: the frontend Library and Workspace UX now treat
  PDF as the official user-facing supported format, while legacy
  `.txt`/`.md` backend support may remain for tests and internal paths
  (Stage 30, completed)
- Embedded PDF Viewer MVP: the frontend Workspace renders selected
  local PDFs in-app with basic page navigation and zoom while
  preserving the system PDF reader action. The PDF bytes are loaded by
  a minimal Tauri command, not by a FastAPI backend endpoint (Stage 31,
  completed)
- PDF Text Extraction / Page-Aware Indexing: local PDF Library items
  can be indexed with `pypdf`; extracted chunks store nullable
  `page_start` and `page_end` metadata, and RAG citations expose
  additive page fields when available (Stage 32,
  completed)
- Today Log / Calendar MVP: `GET /api/learning-events` accepts an
  additive `date=YYYY-MM-DD` filter, learning event responses include
  related Library item and Note titles when available, and the frontend
  Today Log displays events for the selected day without generating AI
  summaries (Stage 33,
  being implemented separately)
- Backend PDF-to-RAG Pipeline MVP: the existing backend path from local
  PDF Library item through `pypdf` extraction, page-aware chunking,
  deterministic embeddings, pgvector-backed storage/retrieval,
  LangGraph Agent Chat, and structured citations is hardened and covered
  by an end-to-end backend regression test (Stage 34,
  completed)
- Backend Dual-Agent LangGraph MVP: `POST /api/agent/chat` now
  orchestrates a deterministic router, fixed Local Library Agent,
  deterministic/mock Web Research Agent, and synthesis step while
  preserving existing local RAG retrieval and citations (Stage 35,
  completed)
- Real LLM Provider Integration: Agent Chat synthesis now uses the
  configured backend LLM provider. Deterministic remains the default,
  while DeepSeek can be enabled explicitly through the existing
  OpenAI-compatible provider and `backend/.env` configuration (Stage 36,
  completed)
- Zhipu Real Embedding + DeepSeek Single-Book RAG Smoke Test: the
  backend can index one local PDF with Zhipu `embedding-3` vectors,
  store 2048-dimensional pgvector embeddings, retrieve a single indexed
  book, and generate an answer through DeepSeek with citations (Stage
  36A, completed)
- Single-Book RAG Observability Polish: `scripts/search_book.py` prints
  ranked single-book retrieval diagnostics without LLM answer generation
  (Stage 36C, current)

Semantic/vector search over long-term memory, open-ended agent
workflows, MCP, backend auto-start from Tauri, complex Rust backend
logic, repository analysis, and production packaging are planned but
**not implemented yet**. Stage 36C is a backend-only observability pass.
It keeps `/api/agent/chat` as the Agent Chat API and preserves its
existing request/response compatibility. It does not change frontend
workspace behavior, Tauri architecture, Vite architecture, local
retrieval algorithms, memory behavior, learning-event semantics, or
Notes APIs. It does not add frontend settings UI, auth, autonomous
planning, broad tool calling, open-ended multi-agent systems, web
browsing, streaming, reranking, hybrid search, BM25, full-text search,
query expansion, OCR, annotations, selected-text workflows, whole-book
synthesis, background jobs, theme management, or deployment.

## Setup

1. Create and activate the conda environment:

   ```bash
   conda create -n pla python=3.12
   conda activate pla
   ```

   This project uses the `pla` conda environment. Do not create a
   project `.venv`.

2. Install backend Python dependencies:

   ```bash
   conda activate pla
   cd backend
   pip install -r requirements.txt
   ```

   `backend/requirements.txt` is only for backend Python runtime,
   migration, graph orchestration, and test dependencies. Stage 26 adds
   `langgraph`; install it through this same command. Frontend
   dependencies are managed separately by `frontend/package.json`.

3. Copy the example environment file and fill in real values locally.
   The real local development `.env` lives inside `backend/`:

   ```bash
   cp backend/.env.example backend/.env
   ```

4. PostgreSQL + pgvector: have a local PostgreSQL server running with the
   `pgvector` extension installed, and set `DATABASE_URL` in
   `backend/.env` to point at your local development database (see
   [Environment Variables](#environment-variables) below). The `vector`
   extension itself is enabled by the Stage 4 migration (see below), not
   manually.

If the `pla` conda environment already exists, use this shorter workflow:

```bash
conda activate pla
cd backend
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload --host 127.0.0.1 --port 8081
```

## Environment Variables

| Variable            | Description                              | Default                        |
|---------------------|-------------------------------------------|---------------------------------|
| `APP_NAME`          | Application display name                  | `Personal Learning Agent`      |
| `APP_ENV`           | Environment name (development/production)| `development`                   |
| `APP_VERSION`       | Application version                       | `0.1.0`                         |
| `LLM_PROVIDER`      | RAG answer provider: `deterministic` or `deepseek` | `deterministic`        |
| `DEEPSEEK_API_KEY`  | DeepSeek API key                          | *(none — set in `.env`)*        |
| `DEEPSEEK_BASE_URL` | DeepSeek API base URL                     | `https://api.deepseek.com`      |
| `DEEPSEEK_MODEL`    | DeepSeek model name                       | `deepseek-chat`                 |
| `DATABASE_URL`      | PostgreSQL connection string (SQLAlchemy) | *(none — set in `.env`)*        |

`DATABASE_URL` uses the SQLAlchemy + psycopg (v3) format, e.g.
`postgresql+psycopg://user:password@localhost:5432/personal_learning_agent`.

`backend/.env` is loaded automatically for local backend startup and
Alembic migrations, and is never committed. Only `backend/.env.example`
(placeholders) is tracked.

LLM provider selection is backend-only. The frontend never sends API
keys or provider settings. Local development and tests use
`LLM_PROVIDER=deterministic`; real DeepSeek mode is opt-in:

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

## Running the API

The default backend development port is `8081`.

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8081
```

Full backend command:

```bash
conda activate pla
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8081
```

- `GET /health` → `{"status": "ok"}`
- `GET /api/status` → app name, environment, and version

For Stage 8 frontend development, CORS is explicitly allowed only for
local dev origins:

- `http://localhost:1420`
- `http://127.0.0.1:1420`
- `http://localhost:5173`
- `http://127.0.0.1:5173`

The frontend expects the backend at `http://127.0.0.1:8081` by default.
For local experiments only, the Vite frontend can override this with
`VITE_BACKEND_URL`, but do not put secrets in frontend environment
files. The backend remains independently started; the desktop shell
does not auto-start FastAPI.

## Running the Frontend

```bash
cd frontend
bun install
bun run dev
bun run tauri dev
```

Build the React frontend with:

```bash
bun run build
```

If `bun run dev` or `bun run tauri dev` reports a port conflict, stop
the process already using `127.0.0.1:1420` and rerun the command. The
Vite dev server is intentionally pinned to that local port for Tauri
development.

## Running Tests

```bash
conda activate pla
cd backend
pytest
```

Tests do not require a real DeepSeek API key and do not call any
external API. The LLM provider tests use deterministic mode by default
and mock real-provider calls without network access. The
database-related tests validate configuration and model metadata; they
do not require a live PostgreSQL connection. The RAG tests
(`test_rag_schemas.py`, `test_qa.py`, `test_retrieval.py`,
`test_rag_api.py`) monkeypatch the vector search and database session,
so they also run without a live PostgreSQL connection. The memory tests
(`test_memory_service.py`, `test_rag_memory_integration.py`,
`test_memory_long_term_service.py`, `test_memory_long_term_api.py`,
`test_rag_long_term_memory_integration.py`) exercise real SQLAlchemy
query logic against a throwaway in-memory SQLite database (not the
project's real PostgreSQL database).

## Database (PostgreSQL) — Stage 3

Stage 3 added the initial database schema: SQLAlchemy models and an
Alembic migration for `learning_sources`, `documents`,
`document_chunks`, and `agent_runs`.

- ORM: SQLAlchemy 2.x (`app/db/`, `app/models/`)
- Driver: `psycopg` (v3)
- Migrations: Alembic (`backend/alembic/`)
- `DATABASE_URL` is read from `backend/.env` via `app.core.config.get_settings()`.
  No connection string or credential is hard-coded, and migrations are
  never run automatically from application startup.

### Running migrations manually

From `backend/`, with the `pla` environment active and `DATABASE_URL` set
in `backend/.env`:

```bash
conda activate pla
cd backend
# create a new migration after changing models
alembic revision --autogenerate -m "describe the change"

# apply all pending migrations
alembic upgrade head

# roll back the most recent migration
alembic downgrade -1
```

## Embedding + pgvector (Stage 4)

Stage 4 proves a minimal pipeline: document chunk text → deterministic
mock embedding → vector stored in PostgreSQL → basic similarity search.
It adds:

- `CREATE EXTENSION IF NOT EXISTS vector` and a nullable `embedding`
  vector column on `document_chunks`, via an Alembic migration
  (`backend/alembic/versions/d9b287f324f9_add_pgvector_embedding_column.py`)
- A deterministic mock embedding provider (`backend/app/embeddings/`) —
  same text always produces the same fixed-length vector; no external
  API calls or API keys involved
- Minimal vector persistence/search functions
  (`backend/app/db/vector_search.py`): `set_chunk_embedding` and
  `search_similar_chunks` (pgvector L2 distance ordering)

**Requires PostgreSQL with the `pgvector` extension installed.** The
`vector` extension is enabled by the migration above
(`CREATE EXTENSION IF NOT EXISTS vector`), not manually. Apply it the
same way as any other migration:

```bash
alembic upgrade head
```

Stage 4 originally used deterministic mock embeddings only. Stage 36A
keeps that mock provider as the default for tests and local deterministic
runs, and adds an opt-in Zhipu embedding provider for real PDF smoke
tests.

## Minimal RAG Q&A (Stage 5)

Stage 5 proves a minimal end-to-end pipeline: user question →
deterministic mock embedding → pgvector similarity search over
`document_chunks` → simple deterministic (extractive) answer → answer
plus retrieved chunks and source metadata. Stage 21 keeps that default
behavior but routes answer generation through a small LLM provider
boundary.

- Retrieval service (`backend/app/rag/retrieval.py`): embeds the
  question with the Stage 4 mock embedding provider and reuses the
  Stage 4 `search_similar_chunks` pgvector search — no new tables, no
  new migration
- QA service (`backend/app/rag/qa.py`): builds a deterministic,
  non-LLM answer from the top retrieved chunk by default, or a clear
  fallback message when nothing relevant is found; when
  `LLM_PROVIDER=deepseek` is explicitly configured, the same retrieved
  context is sent through the LLM provider boundary
- Schemas (`backend/app/rag/schemas.py`): validates `question`
  (required, non-empty after stripping) and `top_k` (default 5, must be
  between 1 and 20)

By default, RAG still uses **deterministic mock embeddings and a simple
deterministic extractive answer generator**. Stage 21 adds an optional
real LLM provider boundary for answer text, Stage 36 wires it into Agent
Chat synthesis, and Stage 36A adds an opt-in real Zhipu embedding
provider for backend smoke tests. See
[Short-term Memory (Stage 6)](#short-term-memory-stage-6) below for the
current endpoint contract, which extends this with `session_id` and
memory metadata.

## Real LLM Provider Integration (Stages 21 and 36)

Stage 21 added a small backend LLM provider abstraction, and Stage 36
wires that provider into Agent Chat synthesis:

```text
Agent Chat synthesis -> LLM provider interface -> deterministic or DeepSeek
```

Provider code lives in `backend/app/llm/providers.py`.

- `DeterministicLLMProvider` is the default and preserves current RAG
  answer text for tests and local development.
- `DeepSeekLLMProvider` is an OpenAI-compatible chat-completions
  provider selected only when `LLM_PROVIDER=deepseek`.
- `get_llm_provider(settings)` validates provider selection and fails
  clearly for unsupported providers or missing DeepSeek config.
- Stage 36 makes the Stage 35 synthesis step call `get_llm_provider()`.
  With deterministic mode, tests and local development keep stable
  output. With `LLM_PROVIDER=deepseek`, `/api/agent/chat` calls the real
  OpenAI-compatible model after local/web evidence is prepared.
- RAG prompt construction lives in `backend/app/rag/qa.py` and includes
  the user question, retrieved chunks, optional short-term memory,
  optional long-term memory, and book context for book-scoped RAG.
  Agent Chat synthesis prompt construction lives in
  `backend/app/agents/synthesis.py` and includes the question, route,
  Local Library summary, Web Research summary, and deterministic
  reference answer.

Enable deterministic mode:

```env
LLM_PROVIDER=deterministic
```

Enable real DeepSeek mode:

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

The DeepSeek key must live only in `backend/.env`. Tests use
deterministic providers or mocked HTTP clients and do not require a real
API key or network access.

Retrieval remains unchanged: global RAG still searches the global
document chunk index, book-scoped RAG still searches only chunks for the
selected indexed Library item, and the default embedding provider is
still deterministic/mock. Retrieved chunks are still returned in API
responses.

Chat-to-Notes remains deterministic/template-based in Stage 21. This
stage does not add real LLM note generation, automatic book summaries,
whole-book summarization, complex mathematical proof generation,
streaming responses, function/tool calling, agent planning, LangGraph,
MCP, frontend provider settings, background
jobs, Redis/Celery/RQ, authentication, deployment, or Docker changes.

## Real Embedding Provider and Single-Book Smoke Test (Stage 36A/36C)

Stage 36A adds an opt-in real embedding provider for backend-only
single-book PDF RAG smoke tests. Stage 36C adds retrieval-only
observability output for the same single-book path:

```text
local PDF -> page-aware extraction -> chunking -> Zhipu embedding
-> pgvector -> single-book retrieval -> search diagnostics
                                  \-> DeepSeek answer -> citations
```

Provider code lives in `backend/app/embeddings/providers.py`.

- `EMBEDDING_PROVIDER=mock` is the default and requires no API key or
  network access.
- `EMBEDDING_PROVIDER=zhipu` uses the Zhipu OpenAI-style embeddings API.
- `ZHIPU_EMBEDDING_DIMENSION` must match the configured pgvector column
  dimension. Stage 36A sets this project to `2048`.
- Tests force deterministic/mock providers and use mocked HTTP clients;
  pytest does not require real Zhipu or DeepSeek keys.

Enable real Zhipu embeddings:

```env
EMBEDDING_PROVIDER=zhipu
ZHIPU_API_KEY=your_zhipu_api_key_here
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZHIPU_EMBEDDING_MODEL=embedding-3
ZHIPU_EMBEDDING_DIMENSION=2048
```

Keep DeepSeek enabled for answer generation:

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

Run the one-book smoke test from `backend/`:

```bash
alembic upgrade head
python scripts/index_pdf.py "../Analysis I (Herbert Amann etc.).pdf"
python scripts/search_book.py --library-item-id <library_item_id> \
  "complete metric spaces"
python scripts/ask_book.py --library-item-id <library_item_id> \
  "What does this book say about completeness, Banach spaces, or metric spaces? Answer with citations."
```

The index script creates or reuses a Library item for the exact PDF
path, indexes the PDF page by page, stores chunk embeddings, and prints
the `library_item_id`, `document_id`, `chunk_count`,
`embedding_provider`, `embedding_dimension`, and empty-page count.
The search script runs retrieval only and prints ranked chunks with
score, title metadata, chunk ID/index, page range, and snippets. It does
not call the LLM provider or generate an answer.

Stage 36A adds Alembic revision
`9d4a6f1b2c30_set_document_chunk_embedding_dimension_2048`, which
changes `document_chunks.embedding` to `vector(2048)`. The migration
deletes existing chunks because vectors cannot be safely converted from
the prior dimension. Re-index affected Library items after applying it.

Secrets must stay only in `backend/.env`. Real PDF books should remain
untracked local files and should not be committed.

## Better Retrieval / Citations / Chunk Metadata (Stage 22)

Stage 22 adds citation/source metadata to RAG responses. The retrieval
algorithm, pgvector search, mock embedding provider, global RAG scope,
and book-scoped RAG filtering are unchanged.

Each response keeps the existing `retrieved_chunks` list and also
returns a top-level `citations` list. Each retrieved chunk includes a
matching `citation` object. Citation IDs are deterministic per response:
`S1`, `S2`, `S3`, and so on.

Citation fields:

```json
{
  "citation_id": "S1",
  "chunk_id": "...",
  "document_id": "...",
  "library_item_id": "...",
  "library_title": "Linear Algebra",
  "library_author": "Some Author",
  "document_title": "linear-algebra.md",
  "document_source_path": "/path/to/linear-algebra.md",
  "chunk_index": 0,
  "score": 0.123,
  "excerpt": "A vector space over a field...",
  "content": "full retrieved chunk content"
}
```

Book-scoped citations identify the selected Library item when available.
Global RAG citations can include Library item metadata when the retrieved
document is associated with a Library item. Excerpts are whitespace
normalized, length-limited, and deterministic.

The frontend Chat page displays a compact Sources section showing
citation ID, source title, author when available, document title/path,
chunk index, score, and excerpt.

Stage 22 does not add reranking, hybrid search, full-text search, BM25,
query expansion, multi-book reasoning, LangGraph, agents, tool calling,
MCP, streaming, real embedding providers, embedding dimension changes,
chunking/indexing changes, PDF page extraction, PDF/DOCX/LaTeX parsing,
OCR, automatic summaries, citation formatting engines, CSL/BibTeX/Zotero
integration, authentication, deployment, or a large UI redesign.

## Book Summary + Topic Extraction (Stage 23)

Stage 23 adds deterministic Library metadata draft generation for
already indexed Library items. It reuses existing fields:
`library_items.description` stores the reviewed summary, and
`library_items.topic_tags` stores reviewed tags. No migration is needed.

**`POST /api/library/items/{item_id}/metadata-draft`** generates a draft
and does not mutate the Library item.

Response:

```json
{
  "library_item_id": "...",
  "title": "Linear Algebra",
  "summary": "This TXT material appears to cover topics related to linear, vector, maps, algebra, and spaces. It is based on 3 indexed chunks from Linear Algebra.",
  "topic_tags": ["linear", "vector", "maps", "algebra", "spaces"],
  "chunks_used": 3,
  "mode": "deterministic"
}
```

The endpoint validates that the Library item exists and has
`status == "indexed"`, then loads associated chunks through
`documents.library_item_id`. If the item does not exist it returns 404.
If the item is not indexed or has no chunks, it returns a clear 409
state error.

Representative chunk selection is intentionally simple: the first few
chunks by document/chunk order. Summary generation is a stable template
using title, file type, chunks used, and extracted tags.
Topic tag extraction lowercases/tokenizes representative chunk text,
removes a small stopword set and short tokens, counts frequencies, and
returns stable top terms.

Reviewed metadata is saved through the existing update endpoint:

```http
PATCH /api/library/items/{item_id}
```

```json
{
  "description": "Reviewed summary...",
  "topic_tags": ["linear", "vector", "basis"]
}
```

Stage 23 remains deterministic by default and does not require API keys
or network calls. It does not add real LLM summary/tag generation by
default, automatic summary jobs, background queues, parser changes,
real embeddings, retrieval changes, whole-book deep summarization,
multi-book synthesis, knowledge graphs, prompt template storage,
LangGraph, agents, tool calling, MCP, authentication, or deployment.

## Learning History / Progress Timeline (Stage 24)

Stage 24 adds a minimal append-only event log for learning-related
actions. The new `learning_events` table includes:

- `event_type`, `title`, optional `description`
- optional `source_type` and `source_id`
- optional `library_item_id` foreign key to `library_items.id`
- optional `note_id` foreign key to `notes.id`
- optional `session_id`
- optional `metadata_json`
- indexed `created_at`

Current event types:

- `library_indexed`
- `metadata_draft_generated`
- `book_rag_question_asked`
- `multi_book_rag_question_asked`
- `agent_chat_question_asked`
- `note_created`
- `note_from_chat_created`
- `note_exported`
- `note_workspace_exported`

API endpoints:

- `POST /api/learning-events` creates a manual event.
- `GET /api/learning-events` lists events newest-first, with optional
  filters for `event_type`, `source_type`, `library_item_id`, `note_id`,
  `session_id`, `date=YYYY-MM-DD`, `limit`, and `offset`.
- `GET /api/learning-events/recent` returns the latest events.
- `GET /api/learning-events/{event_id}` returns one event or 404.

Stage 33 extends learning event responses with related
`library_item_title` and `note_title` when available. The date filter
uses the selected calendar day against event `created_at` timestamps and
preserves existing filters and pagination.

The backend currently records these events automatically:

- successful Library indexing: `library_indexed`
- successful metadata draft generation: `metadata_draft_generated`
- successful book-scoped RAG question: `book_rag_question_asked`
- successful multi-book RAG question: `multi_book_rag_question_asked`
- successful graph-orchestrated agent chat question:
  `agent_chat_question_asked`
- successful note creation: `note_created`, or
  `note_from_chat_created` when the saved note carries a chat session id

Stage 24 does not add learning analytics, charts, calendar views, goal
management, spaced repetition, flashcards, reminders, notifications,
pomodoro timers, AI progress evaluation, weakness diagnosis, real
LLM-based progress analysis, background jobs, Redis/Celery/RQ, event
streaming, sync, user accounts, authentication, deployment, LangGraph,
agents, tool calling, MCP, or a large UI redesign.

## Short-term Memory (Stage 6)

Stage 6 adds a minimal short-term memory layer on top of Stage 5's RAG
pipeline: user question (with an optional `session_id`) → recent
conversation turns for that session are loaded → the deterministic
answer generator notes when recent context was considered → the current
question/answer turn is saved → the response returns the answer,
retrieved chunks, `session_id`, and memory metadata.

- Model (`backend/app/models/conversation_turn.py`) and migration
  (`backend/alembic/versions/ffbb0aa351cd_add_conversation_turns_table.py`):
  a `conversation_turns` table (`session_id`, `question`, `answer`,
  `turn_index`, `metadata_json`, `created_at`), indexed on `session_id`.
  No vector columns, no long-term/semantic memory tables.
- Memory service (`backend/app/memory/short_term.py`): `create_session_id`,
  `get_recent_turns` (bounded, session-scoped, default last 5 turns),
  `save_turn`, and `build_memory_context` (deterministic, no LLM
  summarization, no external API calls)
- `session_id` is optional on request: if omitted, a new one is
  generated and returned; if provided, it is reused so the same session
  builds up conversation history over subsequent calls

Stage 6 is **short-term memory only** — bounded, per-session, in
PostgreSQL. See [Long-term Memory (Stage 7)](#long-term-memory-stage-7)
below for the current `POST /api/rag/query` endpoint contract, which
extends this with optional long-term memory context.

## Long-term Memory (Stage 7)

Stage 7 adds a minimal long-term memory MVP: memories are created
**manually only** (no automatic extraction, no promotion from
short-term memory), stored in PostgreSQL, listable/searchable by type,
importance, and keyword, and optionally usable as a small bounded
deterministic context in RAG answers.

- Model (`backend/app/models/long_term_memory.py`) and migration
  (`backend/alembic/versions/4fe6d409baff_add_long_term_memories_table.py`):
  a `long_term_memories` table (`memory_type`, `content`, `importance`
  1–5, `source`, `tags`, `metadata_json`, `last_accessed_at`,
  `created_at`, `updated_at`), indexed on `memory_type`, `importance`,
  and `created_at`. No vector columns, no semantic/embedding search.
- Memory service (`backend/app/memory/long_term.py`): `create_memory`,
  `get_memory`, `list_memories` (filter by type/importance, bounded
  limit), `search_memories` (simple case-insensitive `ILIKE` keyword
  match, not vector search), and `build_long_term_memory_context`
  (deterministic, bounded to a few memories, no LLM summarization, no
  external API calls)

### Endpoints

**`POST /api/memory/long-term`** — manually create a memory

Request:

```json
{
  "memory_type": "learning_goal",
  "content": "I want to learn algebraic topology after finishing point-set topology.",
  "importance": 4,
  "source": "manual",
  "tags": ["math", "topology"]
}
```

Response:

```text
{
  "id": "...",
  "memory_type": "learning_goal",
  "content": "...",
  "importance": 4,
  "source": "manual",
  "tags": ["math", "topology"],
  "created_at": "...",
  "updated_at": "..."
}
```

**`GET /api/memory/long-term`** — list memories

Query params: `memory_type` (optional), `min_importance` (optional,
1–5), `limit` (optional, default 20, 1–50).

```text
{ "memories": [ ... ], "total": 3 }
```

**`GET /api/memory/long-term/search`** — keyword search

Query params: `keyword` (required, non-empty), `memory_type`
(optional), `min_importance` (optional, 1–5), `limit` (optional,
default 20, 1–50).

```text
{ "memories": [ ... ], "total": 2 }
```

Only create/list/search are provided — no update/delete endpoints in
Stage 7.

### RAG integration

`POST /api/rag/query` gained an optional `include_long_term_memory`
field (default `false`, so existing behavior is unchanged unless a
caller opts in):

```json
{
  "question": "What did I ask before?",
  "top_k": 5,
  "session_id": "optional-existing-session-id",
  "include_long_term_memory": false
}
```

```text
{
  "answer": "...",
  "retrieved_chunks": [
    {
      "chunk_id": "...",
      "document_id": "...",
      "document_title": "...",
      "chunk_index": 0,
      "content": "...",
      "char_start": 0,
      "char_end": 500,
      "score": 0.123
    }
  ],
  "total_retrieved": 1,
  "session_id": "generated-or-existing-session-id",
  "memory": {
    "used_recent_turns": 2,
    "saved_current_turn": true,
    "used_long_term_memories": 1
  }
}
```

When `include_long_term_memory` is `true`, a small bounded keyword
search (using the question text itself) runs against long-term memory
content; if a match is found, the deterministic answer gains one short
extra line naming the single most relevant memory (truncated) — never
the full memory list. `score` is the raw pgvector L2 distance between
the question embedding and the chunk embedding (lower means more
similar). `memory` reports how many recent turns and long-term memories
were used as context, and confirms the current turn was saved.

Stage 7 is **manual long-term memory only**. It does **not** include
automatic memory extraction, automatic promotion from short-term
memory, semantic memory embeddings, long-term memory vector search,
memory decay/reflection, LangGraph, agent planning, tool calling, real
embedding providers, production LLM answer generation, frontend, Tauri,
MCP, PDF/LaTeX/DOCX parsing, or repository analysis. Those remain
planned for later stages.

## Frontend (Stage 8)

Stage 8 adds a minimal Tauri + React + TypeScript frontend shell in
`frontend/`. It proves the desktop/web UI can call the existing FastAPI
backend on `127.0.0.1:8081` while keeping the backend independently
started.

Current frontend features:

- Backend health/status check using `GET /health` and `GET /api/status`
- RAG query form using `POST /api/rag/query`
- Long-term memory create form using `POST /api/memory/long-term`
- Long-term memory list/search using `GET /api/memory/long-term` and
  `GET /api/memory/long-term/search`
- Simple React hook state, validation, loading states, and error
  messages

Backend command:

```bash
conda activate pla
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8081
```

Frontend commands:

```bash
cd frontend
bun install
bun run dev
bun run tauri dev
bun run build
```

Stage 8 limitations:

- Does not auto-start the backend from Tauri
- No MCP
- No LangGraph
- No real embedding provider integration
- No complex Rust local backend logic
- No PDF/LaTeX/DOCX parsing
- No document ingestion UI
- No repository analysis
- No production packaging workflow yet

## Backend/Frontend Integration Polish (Stage 9)

Stage 9 keeps the Stage 8 feature set and focuses on local integration
quality:

- Frontend API request/response types aligned with backend Pydantic
  schemas
- Centralized frontend backend URL handling, defaulting to
  `http://127.0.0.1:8081`
- Safer fetch error handling for non-2xx responses, network failures,
  and invalid JSON
- Clearer loading, error, and empty states in the existing UI
- Explicit local-development CORS for the frontend dev server and Tauri
  shell
- Documentation and ignore-rule cleanup for local development

Stage 9 does **not** add MCP, LangGraph, real embedding providers,
production LLM answer generation, automatic memory extraction,
long-term memory vector search, document ingestion UI, file parsing,
repository analysis, backend auto-start from Tauri, authentication,
Docker, Redis, queues, or production packaging.

## Book Library (Stage 10)

Stage 10 adds a minimal metadata-only book/library system. A library
item represents a manually registered book or learning material. The
record can store title, author, description, optional `file_path`,
optional `file_type`, topic tags, and status.

`file_path` is metadata only in this stage. The backend does not open
the file, verify that it exists, parse contents, index documents, create
embeddings, or scope RAG queries by selected book.

### Library endpoints

**`POST /api/library/items`** — create a library item

```json
{
  "title": "Linear Algebra Done Right",
  "author": "Sheldon Axler",
  "description": "Finite-dimensional vector spaces.",
  "file_path": "/books/linear-algebra.pdf",
  "file_type": "pdf",
  "topic_tags": ["linear algebra", "math"],
  "status": "registered"
}
```

**`GET /api/library/items`** — list items

Query params: `status` (optional), `tag` (optional), `limit` (optional,
default 20, 1–100).

**`GET /api/library/items/search`** — search/filter items

Query params: `keyword` (optional, searches title/author/description),
`status` (optional), `tag` (optional), `limit` (optional, default 20,
1–100).

**`GET /api/library/items/{item_id}`** — get one item by UUID.

**`PATCH /api/library/items/{item_id}`** — update item metadata.

**`DELETE /api/library/items/{item_id}`** — archive the item by setting
`status` to `archived`. This is a soft archive, not a recycle-bin
workflow.

Stage 10 intentionally does **not** include PDF parsing, DOCX parsing,
LaTeX parsing, internal PDF preview, file upload, drag-and-drop upload,
automatic document ingestion from library items, embeddings for library
items, pgvector search for library items, RAG scoping by selected book,
real LLM answer generation, real embedding providers, LangGraph, MCP,
authentication, user accounts, production packaging, Docker,
Redis/queues, or complex UI redesign.

## Open Local Files (Stage 11)

Stage 11 adds desktop-only local file opening for library items. The
backend still stores `file_path` as metadata only; it does not open,
validate, copy, upload, parse, index, or read files. Opening is
performed by the Tauri frontend using the system default application.

When a library item has a non-empty `file_path`, the Book Library UI
shows an `Open` button in the desktop app. Clicking it asks Tauri to
open that local path externally, for example with the operating
system's default PDF viewer, text editor, or TeX editor.

If you run only the browser dev server with `bun run dev`, local file
opening depends on Tauri APIs and should be tested with:

```bash
cd frontend
bun run tauri dev
```

Stage 11 intentionally does **not** include internal PDF preview,
embedded PDF rendering, `react-pdf`, PDF.js, iframe preview, PDF
parsing, text extraction, document indexing, embedding generation,
pgvector indexing, RAG scoping by selected book, file upload,
drag-and-drop upload, automatic ingestion from library items, VS Code
integration, LaTeX editing automation, LangGraph, MCP, real LLM calls,
real embedding providers, authentication, user accounts, production
packaging, Docker, Redis/queues, or complex UI redesign.

## Frontend Layout (Stage 12)

Stage 12 reorganizes the frontend into a three-page desktop workspace:

- Chat: RAG query, backend status, and long-term memory tools
- Library: Book Library metadata management and Stage 11 local file
  opening
- Notes: placeholder for a later LaTeX notes workflow

The Chat page opens by default. Stage 12 does not add backend routes,
database tables, migrations, notes CRUD, LaTeX compilation, PDF preview,
file upload, automatic book indexing, embeddings, book-scoped RAG,
LangGraph, MCP, authentication, Docker, Redis/queues, or production
packaging.

## Library Detail Panel (Stage 13)

Stage 13 adds a frontend detail panel for selected Library items. The
detail panel displays core metadata, tags, timestamps, local file path,
and existing local file opening controls. It also includes static future
placeholders for summary, indexing, related notes, and book-scoped chat.

Stage 13 does not add backend routes, database tables, migrations,
backend file validation, PDF parsing, PDF preview, file upload,
document ingestion from library items, embeddings, pgvector indexing,
book-scoped RAG, notes CRUD, LangGraph, MCP, authentication, Docker,
Redis/queues, or production packaging.

## Library Indexing (Stage 14)

Stage 14 adds `POST /api/library/items/{item_id}/index`. Indexing is
manual from the Library detail view. It reads the selected local
`file_path` on the backend, originally supported `.txt` and `.md` files,
and Stage 32 extended the same path to `.pdf`. Indexing chunks extracted
content, creates or updates a related `documents` row, replaces that
document's chunks, generates deterministic mock embeddings, stores them
on `document_chunks.embedding`, and marks the library item `indexed`.

`Open File` and `Index File` are separate operations. `Open File` asks
Tauri to open the path with the system default app. `Index File` asks
the backend to read a supported text file and persist chunks plus mock
embeddings.

DOCX parsing, LaTeX parsing, OCR, file upload, drag-and-drop import,
batch/folder import, background queues, Redis, Celery/RQ, real embedding
providers, OpenAI/DeepSeek embedding calls, LLM summaries, automatic
book summaries, notes generation, authentication, Docker, and production
packaging are not implemented in this indexing foundation.

## Backend PDF-to-RAG Pipeline (Stage 34)

Stage 34 keeps the existing architecture and hardens the backend path:

```text
PDF Library item
-> pypdf page extraction
-> page-aware chunking
-> embedding provider
-> document_chunks.embedding storage
-> retrieval
-> LangGraph Agent Chat orchestration
-> answer with structured citations
```

Key implementation details:

- PDF loading still starts from an existing Library item/document path.
  The indexing service validates the source path, requires a supported
  file type, and reports clear `LibraryIndexingError` failures.
- PDF extraction uses `backend/app/ingestion/pdf.py` and returns page
  records with one-based page numbers.
- PDF chunks keep `library_item_id`, `document_id`, source path,
  `chunk_index`, and nullable `page_start` / `page_end` metadata.
- `index_library_item` defaults to deterministic `MockEmbeddingProvider`
  but can receive an explicit embedding provider for deterministic
  integration tests.
- Retrieval and `/api/agent/chat` reuse existing services. LangGraph
  remains orchestration only; extraction, chunking, embeddings, storage,
  retrieval, citations, memory, and learning-event logic stay in
  services.
- No Stage 34 database migration is required; it reuses the Stage 32
  page metadata columns and existing pgvector storage.

Manual smoke path:

1. Register a Library item with `file_type: "pdf"` and a local
   `file_path`.
2. Run `POST /api/library/items/{item_id}/index`.
3. Ask through `POST /api/agent/chat` with `scope_type: "single_book"`
   and that `library_item_id`.
4. Verify the response contains an answer, retrieved chunks, structured
   citations, and page metadata when available.

## Book-Scoped RAG (Stage 15)

Stage 15 adds `POST /api/rag/query/library-item`. It accepts a
`library_item_id`, question, `top_k`, optional `session_id`, and
`include_long_term_memory`. Retrieval is restricted to chunks whose
document is connected through `documents.library_item_id`.

Request:

```json
{
  "library_item_id": "00000000-0000-0000-0000-000000000000",
  "question": "What is this book about?",
  "top_k": 5,
  "include_long_term_memory": false
}
```

Response includes the deterministic answer, selected Library item
metadata, retrieved chunks, session id, and memory metadata. The
existing global endpoint `POST /api/rag/query` is unchanged.

Stage 15 does not add real LLM calls, real embedding providers,
advanced reranking, multi-book RAG, PDF/DOCX/LaTeX parsing, OCR,
notes generation, LangGraph, MCP, authentication, Docker, Redis, or
production packaging.

## Multi-Book RAG (Stage 25)

Stage 25 adds `POST /api/rag/query/library-items`. It accepts multiple
Library item IDs and retrieves only chunks whose document is connected
through `documents.library_item_id IN selected_ids`.

Request:

```json
{
  "library_item_ids": [
    "00000000-0000-0000-0000-000000000000",
    "11111111-1111-1111-1111-111111111111"
  ],
  "question": "Compare the definition of vector spaces in these materials.",
  "top_k": 5,
  "session_id": "optional-session-id",
  "include_long_term_memory": false
}
```

Response shape follows the existing RAG responses and adds selected
Library item metadata:

```json
{
  "answer": "...",
  "selected_library_items": [
    {
      "id": "00000000-0000-0000-0000-000000000000",
      "title": "Linear Algebra",
      "author": "Some Author",
      "file_type": "md",
      "status": "indexed"
    }
  ],
  "retrieved_chunks": [
    {
      "chunk_id": "...",
      "document_id": "...",
      "chunk_index": 0,
      "content": "...",
      "score": 0.123,
      "citation": {
        "citation_id": "S1",
        "chunk_id": "...",
        "document_id": "...",
        "library_item_id": "00000000-0000-0000-0000-000000000000",
        "library_title": "Linear Algebra",
        "library_author": "Some Author",
        "document_title": "linear-algebra.md",
        "document_source_path": "/path/linear-algebra.md",
        "chunk_index": 0,
        "score": 0.123,
        "excerpt": "..."
      }
    }
  ],
  "citations": [],
  "total_retrieved": 1,
  "session_id": "optional-session-id",
  "memory": {
    "used_recent_turns": 0,
    "saved_current_turn": true,
    "used_long_term_memories": 0
  }
}
```

Validation rejects blank questions, invalid `top_k`, empty
`library_item_ids`, nonexistent Library items, and selected items that
have not been indexed or have no embedded chunks. Duplicate IDs are
deduplicated in request order.

Successful multi-book RAG saves the short-term conversation turn with
`query_type: "multi_book_rag"` metadata and records the learning event
`multi_book_rag_question_asked` with selected IDs, titles, retrieved
count, and citation count. Failed queries do not create the success
event.

The existing `POST /api/rag/query` and
`POST /api/rag/query/library-item` endpoints remain unchanged.

Stage 25 does not add LangGraph, graph design, agent planning, tool
calling, MCP, multi-agent systems, streaming responses, reranking,
hybrid search, BM25, full-text search, query expansion, real embedding
providers, embedding dimension changes, chunking/indexing changes,
PDF/DOCX/LaTeX parsing, OCR, knowledge graphs, whole-book synthesis,
automatic cross-book comparison engines, background jobs,
Redis/Celery/RQ, authentication, user accounts, cloud deployment, or a
large UI redesign.

## Chat RAG Graph Boundary (Stage 26)

Stage 26 adds LangGraph as a minimal orchestration boundary for the
existing Chat RAG workflow. The only direct dependency added to
`backend/requirements.txt` is:

```text
langgraph
```

Install backend dependencies with the existing command:

```bash
conda activate pla
cd backend
pip install -r requirements.txt
```

New endpoint:

```http
POST /api/agent/chat
```

Request:

```json
{
  "question": "What is a vector space?",
  "scope_type": "multi_book",
  "library_item_id": null,
  "library_item_ids": [
    "00000000-0000-0000-0000-000000000000",
    "11111111-1111-1111-1111-111111111111"
  ],
  "top_k": 5,
  "session_id": "optional-session-id",
  "include_long_term_memory": false
}
```

Response:

```json
{
  "answer": "...",
  "scope_type": "multi_book",
  "selected_library_items": [
    {
      "id": "00000000-0000-0000-0000-000000000000",
      "title": "Linear Algebra",
      "author": "Some Author",
      "file_type": "md",
      "status": "indexed"
    }
  ],
  "retrieved_chunks": [],
  "citations": [],
  "route": "both",
  "web_sources": [],
  "local_summary": null,
  "web_summary": null,
  "total_retrieved": 0,
  "session_id": "optional-session-id",
  "memory": {
    "used_recent_turns": 0,
    "saved_current_turn": true,
    "used_long_term_memories": 0
  }
}
```

Graph node sequence:

```text
validate_input
-> resolve_scope
-> load_memory
-> retrieve_chunks
-> build_citations
-> build_prompt
-> generate_answer
-> save_memory
-> record_learning_event
-> format_response
```

LangGraph nodes call existing services:

- RAG retrieval: global, single-book, and multi-book retrieval services
- Memory: existing short-term and long-term memory services
- Citations: Stage 22 citation builder
- Prompt/answer: existing RAG prompt helpers and Stage 21 LLM provider
  boundary
- Learning events: Stage 24 event service

The graph saves one short-term memory turn with `query_type:
"agent_chat"` metadata and records one `agent_chat_question_asked`
event after successful responses. It does not call existing RAG
endpoints internally, so it does not duplicate their learning events.

Existing RAG endpoints remain available and unchanged:

- `POST /api/rag/query`
- `POST /api/rag/query/library-item`
- `POST /api/rag/query/library-items`

The frontend Chat page still uses the existing RAG endpoints in Stage
26. Switching the UI to `/api/agent/chat`, adding graph visualization,
or adding frontend graph settings is left for a future stage.

Stage 26 tests remain deterministic. The default LLM provider is still
deterministic and requires no API key; real LLM use remains opt-in
through the existing Stage 21 provider configuration.

Stage 26 does not add an open-ended agent planner, tool calling, MCP,
multi-agent system, autonomous behavior, reflection loop, retry loop,
self-critique, streaming responses, function calling, frontend settings
page, graph-based Notes generation, graph-based study sessions,
graph-based book summaries, real embedding providers, OpenAI/DeepSeek
embedding calls, embedding dimension changes, chunking/indexing
pipeline changes, reranking, hybrid search, BM25, full-text search,
query expansion, PDF/DOCX/LaTeX parsing, OCR, knowledge graphs,
background jobs, Redis/Celery/RQ, authentication, user accounts, cloud
deployment, or a large UI redesign.

## Backend Dual-Agent LangGraph MVP (Stage 35)

Stage 35 keeps `POST /api/agent/chat` as the single Agent Chat API and
adds a fixed dual-agent orchestration path:

```text
validate_input
-> resolve_scope
-> load_memory
-> route_question
-> run_local_library_agent
-> run_web_research_agent
-> synthesize_answer
-> save_memory
-> record_learning_event
-> format_response
```

Router behavior is deterministic and requires no LLM:

- `local_only`: questions mentioning "my books", "my PDFs", "library",
  "imported documents", "我的书", "书库", "我的 PDF", or "根据我的资料".
- `web_only`: questions mentioning "latest", "recent", "current",
  "news", "web", "internet", "最新", "最近", "网络", or "网上".
- `both`: questions matching both local and web keyword groups, and
  uncertain/general learning questions by default.

Fixed agent boundaries:

- Local Library Agent: reuses existing global, single-book, and
  multi-book retrieval services, `pgvector` chunk search, page-aware
  citation builder, and deterministic local evidence summary.
- Web Research Agent: deterministic/mock provider by default. It
  returns placeholder web sources and does not make network requests or
  require API keys. A real web provider should be added only as an
  explicit opt-in configuration path in a later stage.
- Synthesis: combines local and/or web results into one final answer.

Additive response fields:

```json
{
  "route": "local_only | web_only | both",
  "web_sources": [
    {
      "source_id": "W1",
      "title": "Deterministic web research placeholder",
      "url": "mock://web-research/deterministic",
      "excerpt": "...",
      "provider": "deterministic"
    }
  ],
  "local_summary": "...",
  "web_summary": "..."
}
```

Existing response fields remain: `answer`, `scope_type`,
`selected_library_items`, `retrieved_chunks`, `citations`,
`total_retrieved`, `session_id`, and `memory`.

Stage 35 does not add frontend simplification, new frontend pages, PDF
viewer changes, OCR, annotations, citation-to-page navigation,
authentication, settings, autonomous planning, broad tool calling,
open-ended multi-agent behavior, a new RAG algorithm, BM25, hybrid
search, reranking, database migrations, or major backend rewrites.

## Notes MVP (Stage 16)

Stage 16 adds a database-backed LaTeX note manager. Notes are stored in
the new `notes` table and can optionally reference a Library item
through `notes.library_item_id`.

Notes API endpoints:

- `POST /api/notes` creates a note.
- `GET /api/notes` lists notes, returning active notes by default.
- `GET /api/notes/search` performs simple keyword matching over title
  and description.
- `GET /api/notes/{note_id}` returns one note.
- `PATCH /api/notes/{note_id}` updates note metadata or LaTeX source.
- `DELETE /api/notes/{note_id}` archives the note by setting
  `status = "archived"`; it does not physically delete the row.

The Notes page in the frontend provides a plain textarea for LaTeX
source, optional Library item association, comma-separated topic tags,
save, and archive actions.

Stage 16 does not add AI note generation, Save Chat as Note, real LLM
calls, real embedding calls, LaTeX compilation, PDF preview, `.tex`
export, local notes workspace, opening notes in external apps, rich text
editing, full-text search, authentication, background jobs, or
attachments.

## Generate LaTeX Notes from Chat (Stage 17)

Stage 17 adds deterministic Chat-to-Notes draft generation. It converts
the current Chat/RAG response into a simple LaTeX note draft and returns
that draft to the frontend for review. The draft endpoint does not save
to the database; the frontend saves reviewed drafts through the existing
`POST /api/notes` endpoint.

Endpoint:

- `POST /api/notes/from-chat/draft`

Request example:

```json
{
  "question": "What is a vector space?",
  "answer": "A vector space is a set equipped with addition and scalar multiplication.",
  "retrieved_chunks": [
    {
      "id": "chunk-id",
      "document_id": "document-id",
      "chunk_index": 0,
      "content": "A vector space over a field F is...",
      "score": 0.123
    }
  ],
  "library_item": {
    "id": "library-item-id",
    "title": "Linear Algebra",
    "author": "Some Author",
    "file_type": "md",
    "status": "indexed"
  },
  "session_id": "optional-session-id"
}
```

Response example:

```json
{
  "title": "Notes on What is a vector space?",
  "content_latex": "\\section{Notes on What is a vector space?}\\n...",
  "description": "Generated from Chat response.",
  "library_item_id": "library-item-id",
  "source_session_id": "optional-session-id",
  "topic_tags": ["chat-generated"]
}
```

Stage 17 uses a template only. It escapes common LaTeX-sensitive
characters, includes the question, answer, optional book context, and
retrieved chunk excerpts. It does not call a real LLM, perform real
summarization, generate proofs, compile LaTeX, preview PDFs, export
`.tex` files, add editor integrations, or change the Notes CRUD
architecture.

## Local Notes File Export (Stage 18)

Stage 18 adds desktop-side export for existing Notes. From the Notes
page, a selected database-backed note can be exported as a UTF-8 `.tex`
file through the Tauri desktop app.

Export behavior:

- The user clicks `Export as .tex` on a selected note.
- Tauri opens a save-file dialog with a sanitized default filename.
- If the chosen path does not end with `.tex`, the frontend appends
  `.tex`.
- The Tauri desktop layer writes exactly the current editor LaTeX
  content to the selected local file path.
- The database note is not mutated by export.

There is intentionally no backend endpoint such as
`POST /api/notes/{note_id}/export`; the FastAPI backend does not accept
arbitrary absolute local paths and does not write files to the user's
filesystem.

Stage 18 does not add LaTeX compilation, PDF generation, PDF preview,
internal PDF viewing, `.pdf` export, VS Code integration, opening
exported files, local notes workspace management, Git sync, file
watchers, bidirectional sync, `.tex` import, multi-file LaTeX projects,
attachments, folder/batch export, background jobs, real LLM calls, AI
note generation, or changes to the Notes CRUD or Chat-to-Notes
architectures.

## Notes Workspace MVP (Stage 19)

Stage 19 adds a local Notes workspace convenience flow in the Tauri
desktop app. The workspace path is local machine configuration and is
stored in browser `localStorage` under `pla.notesWorkspacePath`, not in
PostgreSQL.

Workspace behavior:

- The Notes page shows the current workspace path or "No workspace selected."
- `Choose Workspace Folder` opens a Tauri folder-selection dialog.
- `Clear Workspace` removes the locally stored workspace path.
- `Export to Workspace` writes the current editor LaTeX content for the
  selected note into the configured workspace folder.
- Filenames are sanitized from the note title and always end with `.tex`.
- Duplicate filenames are handled by creating `name-2.tex`,
  `name-3.tex`, and so on.

The FastAPI backend remains unchanged. It does not store workspace
paths, does not scan local folders, and does not write arbitrary local
filesystem paths.

Stage 19 does not add VS Code integration, opening exported files,
LaTeX compilation, PDF generation, PDF preview, Git sync, file watchers,
automatic synchronization, bidirectional editing, `.tex` import,
workspace scanning, multi-file LaTeX projects, attachments, folder or
batch export, background jobs, real LLM calls, AI note generation, or
changes to the Notes CRUD or Chat-to-Notes architectures.

## Open Exported Notes File (Stage 20)

Stage 20 adds desktop-side opening for the last successfully exported
Notes `.tex` file. After either manual `Export as .tex` or workspace
`Export to Workspace`, the Notes page stores the actual final path
returned by the export helper. `Open Exported File` opens that remembered
`.tex` path with the system default application through Tauri opener.

The opened path is not typed by the user into an opener field; it must
come from a successful export action and must be non-empty with a `.tex`
extension before the frontend opens it.

The FastAPI backend remains unchanged. Stage 20 does not add backend
file-opening endpoints, backend arbitrary-path handling, database
migrations, PostgreSQL export tracking, VS Code-specific integration,
forcing files to open in VS Code, LaTeX compilation, PDF generation, PDF
preview, file sync, file watchers, `.tex` import, or workspace browsing.

## Document Ingestion (MVP)

A minimal ingestion module supporting plain text and Markdown files.

- Character-based text chunking (no LangChain text splitters yet).
- File loading restricted to `.txt` and `.md` files inside `backend/data`.
  Paths that escape `backend/data` (e.g. `../.env`) or use unsupported
  extensions are rejected.

This stage does **not** include RAG, embeddings, vector/database storage,
or LangGraph — only chunking and safe local file loading.

### Endpoints

**`POST /api/ingestion/chunk-text`**

Request:

```json
{
  "text": "...",
  "chunk_size": 800,
  "chunk_overlap": 100
}
```

Response:

```text
{
  "chunks": [ ... ],
  "total_chunks": 3
}
```

**`POST /api/ingestion/load-file`**

Loads a `.txt` or `.md` file by path relative to `backend/data`, then
chunks its contents.

Request:

```json
{
  "file_path": "example.md",
  "chunk_size": 800,
  "chunk_overlap": 100
}
```

Response:

```text
{
  "file_path": "example.md",
  "chunks": [ ... ],
  "total_chunks": 3
}
```

## Roadmap (not yet implemented)

- Document ingestion UI
- Real embedding provider integration and production-quality agent workflows
- Automatic memory extraction and short-term → long-term promotion
- Semantic memory embeddings and long-term memory vector search
- Learning progress tracking
- Study plan generation
- LangGraph-based agent workflows
- MCP integration
- Packaging/distribution
