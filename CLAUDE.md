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
Stage 4: Embedding + pgvector MVP — completed.

Current active stage: Stage 5: Minimal RAG Q&A MVP.

Do not implement the full product at once.

The default backend development port is `8081`.

Project stage roadmap:
1. Backend skeleton — completed
2. Document ingestion MVP — completed
3. PostgreSQL schema — completed
4. Embedding + pgvector — completed
5. Minimal RAG Q&A — current
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

Stage 4 (completed): a minimal embedding + pgvector MVP — proving the
pipeline of document chunk text → deterministic mock embedding →
vector stored in PostgreSQL → basic similarity search, via
`backend/app/embeddings/` and `backend/app/db/vector_search.py`.

The current goal (Stage 5) is a minimal RAG Q&A MVP only: proving the
pipeline of user question → deterministic mock embedding → pgvector
similarity search over `document_chunks` → simple deterministic
(extractive, non-LLM) answer → answer plus retrieved chunks and source
metadata.

Allowed in the current stage:
- Request/response schemas for a RAG query (`backend/app/rag/schemas.py`)
- A retrieval service (`backend/app/rag/retrieval.py`) that reuses the
  existing Stage 4 mock embedding provider and `search_similar_chunks` —
  no new tables, no new migration
- A QA service (`backend/app/rag/qa.py`) that builds a deterministic,
  non-LLM extractive answer from retrieved chunks, with a clear
  fallback message when nothing relevant is found
- `POST /api/rag/query` returning `answer`, `retrieved_chunks`, and
  `total_retrieved`
- Tests for schemas, the QA service, the retrieval service (mocking
  vector search), and the API endpoint (mocking retrieval/DB session)
  that do not require a live database connection
- README/CLAUDE.md updates documenting Stage 5 status

Do not implement yet (Stage 5 must not include):
- LangGraph workflows
- Long-term memory
- Short-term memory
- Real embedding provider integration (DeepSeek, OpenAI, or otherwise)
- Production LLM answer generation
- Frontend
- Tauri
- MCP
- PDF parsing
- LaTeX parsing
- DOCX parsing
- Recursive directory scanning
- Repository analysis
- Multi-agent workflows
- Multi-turn conversation
- Agent planning or tool calling
- Email/calendar reminders
- Automatic local file modification outside `backend/data`
- Automatic embedding during ingestion, background jobs, reranking,
  hybrid search, or chunk metadata enrichment
- New database tables or migrations (Stage 5 reuses existing schema)
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
- Minimal RAG Q&A (`backend/app/rag/`): deterministic mock embeddings +
  pgvector search + simple extractive answer generation; no real LLM or
  embedding provider

Planned later:
- LangGraph
- Real embedding provider integration and production-quality RAG Q&A
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