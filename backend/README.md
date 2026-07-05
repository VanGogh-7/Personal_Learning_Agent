# Personal Learning Agent — Backend

## Purpose

Backend foundation for a local-first Personal Learning Agent that will
eventually help manage learning materials, notes, books, study progress,
and knowledge retrieval.

## Current Stage

Stage 3: PostgreSQL schema.

- FastAPI app with health/status endpoints (Stage 1)
- Document ingestion MVP: text chunking and safe `.txt`/`.md` loading (Stage 2)
- SQLAlchemy models + Alembic migrations for the initial schema (Stage 3)

RAG, embeddings, pgvector search, LangGraph workflows, short/long-term
memory, and the frontend (Tauri + React) are planned but
**not implemented yet**.

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

4. PostgreSQL: have a local PostgreSQL server running and set
   `DATABASE_URL` in the root `.env` to point at your local development
   database (see [Environment Variables](#environment-variables) below).

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
model metadata; they do not require a live PostgreSQL connection.

## Database (PostgreSQL) — Stage 3

Stage 3 adds the initial database schema only: SQLAlchemy models and an
Alembic migration for `learning_sources`, `documents`,
`document_chunks`, and `agent_runs`. It does **not** add embeddings,
pgvector search, RAG, LangGraph, or memory logic — that is planned for
later stages.

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

- Embeddings + pgvector search
- RAG Q&A over personal learning materials
- Short-term and long-term memory
- Learning progress tracking
- Study plan generation
- LangGraph-based agent workflows
- Tauri + React desktop UI
