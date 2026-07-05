# CLAUDE.md

## Project Overview

This repository is for a Personal Learning Agent.

The long-term goal is to build a local-first agent that helps the user manage learning materials, notes, books, study progress, and knowledge retrieval.

The project will later support:
- Document ingestion
- RAG over personal learning materials
- Short-term and long-term memory
- Learning progress tracking
- Study plan generation
- LangGraph-based agent workflows
- PostgreSQL + pgvector storage
- Optional Tauri + React desktop UI

Stage 1: Backend skeleton — completed.
Stage 2: Document ingestion MVP — completed.
Stage 3: PostgreSQL schema — completed.

Current active stage: Stage 4: Embedding + pgvector MVP.

Do not implement the full product at once.

The default backend development port is `8081`.

Project stage roadmap:
1. Backend skeleton — completed
2. Document ingestion MVP — completed
3. PostgreSQL schema — completed
4. Embedding + pgvector — current
5. RAG Q&A
6. Short-term memory
7. Long-term memory
8. Tauri + React frontend

---

## Current Development Scope

Stage 1 (completed): a clean backend skeleton — FastAPI app setup,
environment variable configuration, `.env.example`, health/status
endpoints, minimal DeepSeek client module, basic tests, README setup
instructions, clean backend directory structure.

Stage 2 (completed): a minimal document ingestion module for plain text
and Markdown content — character-based chunking, safe `.txt`/`.md`
loading from `backend/data`, `/api/ingestion` routes, and tests.

Stage 3 (completed): PostgreSQL schema support — `DATABASE_URL` config,
SQLAlchemy 2.x models, and Alembic migrations for `learning_sources`,
`documents`, `document_chunks`, and `agent_runs`.

The current goal (Stage 4) is a minimal embedding + pgvector MVP only:
proving the pipeline of document chunk text → deterministic mock
embedding → vector stored in PostgreSQL → basic similarity search.

Allowed in the current stage:
- `CREATE EXTENSION IF NOT EXISTS vector` and a nullable `embedding`
  vector column added to `document_chunks` via an Alembic migration
- A deterministic mock embedding provider (`backend/app/embeddings/`)
  that does not call any external API
- Minimal vector persistence/search functions
  (`backend/app/db/vector_search.py`): storing an embedding for a chunk
  and a basic pgvector similarity search
- Tests for embedding determinism/dimension, model metadata, and safe
  query construction that do not require a live database connection
- README/CLAUDE.md updates documenting Stage 4 status

Do not implement yet (Stage 4 must not include):
- Full RAG Q&A
- Real embedding provider integration (DeepSeek, OpenAI, or otherwise)
- LangGraph workflows
- Long-term memory
- Short-term memory
- Frontend
- Tauri
- MCP
- PDF parsing
- LaTeX parsing
- DOCX parsing
- Recursive directory scanning
- Repository analysis
- Multi-agent workflows
- Email/calendar reminders
- Automatic local file modification outside `backend/data`
- Automatic embedding during ingestion, background jobs, reranking,
  hybrid search, or chunk metadata enrichment
- Running migrations automatically from application startup
- Destructive SQL or database create/drop/reset operations

---

## Tech Stack

Backend:
- Python
- FastAPI
- pytest
- PostgreSQL (schema layer only, via SQLAlchemy 2.x + Alembic)
- SQLAlchemy 2.x
- Alembic
- psycopg (v3)
- pgvector (nullable embedding column + basic similarity search only;
  embeddings are deterministic mocks, not a real provider)

Planned later:
- LangGraph
- Real embedding provider integration (RAG Q&A)
- Tauri + React
- Rust local backend
- MCP integration

LLM provider:
- DeepSeek API
- API key is stored in `.env`
- Use environment variables only

---

## Security Rules

Never print, log, commit, expose, or hard-code secrets.

Never read or modify `.env` unless explicitly asked.

`.env` must be ignored by Git.

Use `.env.example` for placeholder environment variables only.

Allowed example:

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat