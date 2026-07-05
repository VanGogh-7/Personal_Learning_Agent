# Personal Learning Agent — Backend

## Purpose

Backend foundation for a local-first Personal Learning Agent that will
eventually help manage learning materials, notes, books, study progress,
and knowledge retrieval.

## Current Stage

Stage 12: Frontend Layout Redesign MVP.

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
  current)

Real embedding provider integration (DeepSeek, OpenAI, or otherwise),
production LLM answer generation, semantic/vector search over long-term
memory, LangGraph workflows, MCP, backend auto-start from Tauri,
complex Rust backend logic, document parsing UI, repository analysis,
and production packaging are planned but **not implemented yet**. Stage
12 is frontend layout-only and does not change backend behavior.

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
   migration, and test dependencies. Frontend dependencies are managed
   separately by `frontend/package.json`.

3. Copy the example environment file and fill in real values locally.
   The real `.env` lives at the **project root** (one level above
   `backend/`), not inside `backend/`:

   ```bash
   cp backend/.env.example .env
   ```

4. PostgreSQL + pgvector: have a local PostgreSQL server running with the
   `pgvector` extension installed, and set `DATABASE_URL` in the root
   `.env` to point at your local development database (see
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
| `DEEPSEEK_API_KEY`  | DeepSeek API key                          | *(none — set in `.env`)*        |
| `DEEPSEEK_BASE_URL` | DeepSeek API base URL                     | `https://api.deepseek.com`      |
| `DEEPSEEK_MODEL`    | DeepSeek model name                       | `deepseek-chat`                 |
| `DATABASE_URL`      | PostgreSQL connection string (SQLAlchemy) | *(none — set in `.env`)*        |

`DATABASE_URL` uses the SQLAlchemy + psycopg (v3) format, e.g.
`postgresql+psycopg://user:password@localhost:5432/personal_learning_agent`.

`.env` lives at the project root and is never committed. Only
`backend/.env.example` (placeholders) is tracked.

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
npm install
npm run dev
npm run tauri dev
```

Build the React frontend with:

```bash
npm run build
```

If `npm run dev` or `npm run tauri dev` reports a port conflict, stop
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
external API. The database-related tests validate configuration and
model metadata; they do not require a live PostgreSQL connection. The
RAG tests (`test_rag_schemas.py`, `test_qa.py`, `test_retrieval.py`,
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
- `DATABASE_URL` is read from the root `.env` via `app.core.config.get_settings()`.
  No connection string or credential is hard-coded, and migrations are
  never run automatically from application startup.

### Running migrations manually

From `backend/`, with the `pla` environment active and `DATABASE_URL` set
in the root `.env`:

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

Stage 4 uses **deterministic mock embeddings only** — there is no real
embedding provider integration (DeepSeek, OpenAI, or otherwise). Stage 5
(below) builds a minimal Q&A layer on top of this; full RAG Q&A with a
real embedding provider remains planned for later stages.

## Minimal RAG Q&A (Stage 5)

Stage 5 proves a minimal end-to-end pipeline: user question →
deterministic mock embedding → pgvector similarity search over
`document_chunks` → simple deterministic (extractive) answer → answer
plus retrieved chunks and source metadata.

- Retrieval service (`backend/app/rag/retrieval.py`): embeds the
  question with the Stage 4 mock embedding provider and reuses the
  Stage 4 `search_similar_chunks` pgvector search — no new tables, no
  new migration
- QA service (`backend/app/rag/qa.py`): builds a deterministic,
  non-LLM answer from the top retrieved chunk, or a clear fallback
  message when nothing relevant is found
- Schemas (`backend/app/rag/schemas.py`): validates `question`
  (required, non-empty after stripping) and `top_k` (default 5, must be
  between 1 and 20)

Stage 5 uses **deterministic mock embeddings and a simple deterministic
extractive answer generator only** — no real embedding provider
(DeepSeek, OpenAI, or otherwise) and no production LLM answer
generation. See [Short-term Memory (Stage 6)](#short-term-memory-stage-6)
below for the current endpoint contract, which extends this with
`session_id` and memory metadata.

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
npm install
npm run dev
npm run tauri dev
npm run build
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

If you run only the browser dev server with `npm run dev`, local file
opening depends on Tauri APIs and should be tested with:

```bash
cd frontend
npm run tauri dev
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
- Real embedding provider integration and full RAG Q&A quality
- Automatic memory extraction and short-term → long-term promotion
- Semantic memory embeddings and long-term memory vector search
- Learning progress tracking
- Study plan generation
- LangGraph-based agent workflows
- MCP integration
- Packaging/distribution
