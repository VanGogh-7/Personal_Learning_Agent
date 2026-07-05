# Personal Learning Agent — Backend

## Purpose

Backend foundation for a local-first Personal Learning Agent that will
eventually help manage learning materials, notes, books, study progress,
and knowledge retrieval.

## Current Stage

Stage 5: Minimal RAG Q&A MVP.

- FastAPI app with health/status endpoints (Stage 1, completed)
- Document ingestion MVP: text chunking and safe `.txt`/`.md` loading (Stage 2, completed)
- SQLAlchemy models + Alembic migrations for the initial schema (Stage 3, completed)
- pgvector/vector extension support via migration, a nullable `embedding`
  column on `document_chunks`, deterministic mock embeddings, and minimal
  vector persistence/search functions (Stage 4, completed)
- Minimal RAG Q&A: question → mock embedding → pgvector similarity search
  → simple deterministic extractive answer (Stage 5, current)

Real embedding provider integration (DeepSeek, OpenAI, or otherwise),
production LLM answer generation, LangGraph workflows, short/long-term
memory, and the frontend (Tauri + React) are planned but **not
implemented yet**. See [Minimal RAG Q&A (Stage 5)](#minimal-rag-qa-stage-5)
below for what Stage 5 actually adds.

## Setup

1. Create and activate the conda environment:

   ```bash
   conda create -n pla python=3.12
   conda activate pla
   ```

2. Install dependencies:

   ```bash
   cd backend
   pip install -r requirements.txt
   ```

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

- `GET /health` → `{"status": "ok"}`
- `GET /api/status` → app name, environment, and version

## Running Tests

```bash
pytest
```

Tests do not require a real DeepSeek API key and do not call any
external API. The database-related tests validate configuration and
model metadata; they do not require a live PostgreSQL connection. The
RAG tests (`test_rag_schemas.py`, `test_qa.py`, `test_retrieval.py`,
`test_rag_api.py`) monkeypatch the vector search and database session,
so they also run without a live PostgreSQL connection.

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

### Endpoint

**`POST /api/rag/query`**

Request:

```json
{
  "question": "What is gradient descent?",
  "top_k": 5
}
```

Response:

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
  "total_retrieved": 1
}
```

`score` is the raw pgvector L2 distance between the question embedding
and the chunk embedding (lower means more similar).

Stage 5 uses **deterministic mock embeddings and a simple deterministic
extractive answer generator only** — no real embedding provider
(DeepSeek, OpenAI, or otherwise), no production LLM answer generation,
and no LangGraph, memory, frontend, Tauri, MCP, PDF/LaTeX/DOCX parsing,
or repository analysis. Those remain planned for later stages.

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

- Real embedding provider integration and full RAG Q&A quality
- Short-term and long-term memory
- Learning progress tracking
- Study plan generation
- LangGraph-based agent workflows
- Tauri + React desktop UI
