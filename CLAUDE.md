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
Stage 5: Minimal RAG Q&A MVP — completed.
Stage 6: Short-term Memory MVP — completed.

Current active stage: Stage 7: Long-term Memory MVP.

Do not implement the full product at once.

The default backend development port is `8081`.

Project stage roadmap:
1. Backend skeleton — completed
2. Document ingestion MVP — completed
3. PostgreSQL schema — completed
4. Embedding + pgvector — completed
5. Minimal RAG Q&A — completed
6. Short-term memory — completed
7. Long-term memory — current
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

Stage 5 (completed): a minimal RAG Q&A MVP — proving the pipeline of
user question → deterministic mock embedding → pgvector similarity
search over `document_chunks` → simple deterministic (extractive,
non-LLM) answer → answer plus retrieved chunks and source metadata, via
`backend/app/rag/` and `POST /api/rag/query`.

Stage 6 (completed): a minimal short-term memory MVP — a user question
(with an optional `session_id`) loads recent conversation turns for
that session, the deterministic answer generator notes when recent
context was considered, the current turn is saved afterward, and the
response includes `session_id` plus memory metadata, via
`backend/app/memory/short_term.py`.

The current goal (Stage 7) is a minimal long-term memory MVP only:
memories are created **manually** through a small service/API, stored
in PostgreSQL, listable/searchable by type, importance, and keyword, and
optionally usable as a small bounded deterministic context in RAG
answers.

Allowed in the current stage:
- A `long_term_memories` table and Alembic migration (`memory_type`,
  `content`, `importance` 1–5, `source`, `tags`, `metadata_json`,
  `last_accessed_at`, `created_at`, `updated_at`; indexed on
  `memory_type`, `importance`, `created_at`) — no vector columns
- A long-term memory service (`backend/app/memory/long_term.py`):
  `create_memory`, `get_memory`, `list_memories`, `search_memories`
  (simple case-insensitive `ILIKE` keyword match, not vector search),
  `build_long_term_memory_context` (deterministic, bounded to a few
  memories, no LLM summarization, no external API calls)
- `POST /api/memory/long-term`, `GET /api/memory/long-term`,
  `GET /api/memory/long-term/search` — create/list/search only, no
  update/delete endpoints
- Optional `include_long_term_memory` (default `false`) on
  `RagQueryRequest`; when `true`, a small bounded keyword search against
  long-term memory content feeds into the deterministic answer;
  `MemoryMetadata` extended with `used_long_term_memories`
- Tests for schemas, the memory service, the API endpoints, and the
  optional RAG integration (mocking vector search, using a throwaway
  in-memory SQLite database instead of the real PostgreSQL database)
- README/CLAUDE.md updates documenting Stage 7 status

Do not implement yet (Stage 7 must not include):
- Automatic memory extraction
- Automatic promotion from short-term memory to long-term memory
- Semantic memory embeddings
- Long-term memory vector search
- Memory decay or memory reflection
- User profile memory
- Complex memory graph tables
- LangGraph workflows
- Agent planning or tool calling
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
- Email/calendar reminders
- Automatic local file modification outside `backend/data`
- Background jobs, reranking, hybrid search, or complex prompt management
- Redis or a message queue
- Running migrations automatically from application startup
- Destructive SQL, or dropping existing tables manually

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
- Short-term memory (`backend/app/memory/short_term.py`): bounded,
  per-session `conversation_turns` in PostgreSQL; deterministic context
  only, no LLM summarization
- Long-term memory MVP (`backend/app/memory/long_term.py`): manually
  created `long_term_memories` in PostgreSQL, keyword (`ILIKE`) search
  only, deterministic bounded context only; no embeddings/vector search,
  no automatic extraction or promotion

Planned later:
- LangGraph
- Real embedding provider integration and production-quality RAG Q&A
- Semantic memory embeddings and long-term memory vector search
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