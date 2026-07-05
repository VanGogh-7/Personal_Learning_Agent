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
Stage 7: Long-term Memory MVP — completed.
Stage 8: Tauri + React Frontend MVP — completed.
Stage 9: Backend/Frontend Integration Polish — completed.
Stage 10: Book Library MVP — completed.
Stage 11: Open Local Files from Desktop App — completed.

Current active stage: Stage 12: Frontend Layout Redesign MVP.

Do not implement the full product at once.

The default backend development port is `8081`.

Project stage roadmap:
1. Backend skeleton — completed
2. Document ingestion MVP — completed
3. PostgreSQL schema — completed
4. Embedding + pgvector — completed
5. Minimal RAG Q&A — completed
6. Short-term memory — completed
7. Long-term memory — completed
8. Tauri + React frontend — completed
9. Backend/frontend integration polish — completed
10. Book Library MVP — completed
11. Open local files from desktop app — completed
12. Frontend layout redesign — current

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

Stage 7 (completed): a minimal long-term memory MVP — memories are
created **manually** through a small service/API, stored in PostgreSQL,
listable/searchable by type, importance, and keyword, and optionally
usable as small bounded deterministic context in RAG answers.

Stage 8 (completed): a minimal Tauri + React frontend MVP — a small
TypeScript/Vite UI under `frontend/` that calls the existing FastAPI
backend on `127.0.0.1:8081` for health/status, RAG query, and long-term
memory create/list/search. The backend remains independently started on
port `8081`.

Stage 9 (completed): backend/frontend integration polish — frontend API
types aligned with backend schemas, centralized backend URL handling,
safer fetch errors, clearer UI empty states, explicit local-development
CORS, and local development docs cleanup.

Stage 10 (completed): a Book Library MVP — manual registration,
listing, updating, archiving, and search/filtering of book or
learning-material metadata. Library items may store title, author,
description, `file_path`, `file_type`, topic tags, and status.

Stage 11 (completed): local file opening from the Tauri desktop app
only. `file_path` remains metadata stored by the backend. The desktop
frontend may ask Tauri to open that path externally with the system
default application.

The current goal (Stage 12) is a frontend layout redesign MVP. Refactor
the single long page into a calm three-page desktop workspace with
sidebar navigation:
- Chat
- Library
- Notes

Allowed in the current stage:
- Simple React state for page switching
- App shell with left sidebar navigation and main content area
- Chat page containing existing RAG query, backend status, and memory tools
- Library page containing existing Book Library and local file open UI
- Notes page placeholder for later LaTeX notes functionality
- Minimal CSS polish using the existing CSS approach
- README/CLAUDE.md updates documenting Stage 12

Do not implement in Stage 12:
- New backend API endpoints
- Database migrations
- Notes CRUD
- LaTeX compilation
- LaTeX PDF preview
- Internal PDF preview
- PDF parsing
- DOCX parsing
- LaTeX parsing
- File upload
- Drag-and-drop upload
- Automatic book indexing
- Embedding generation
- Book-scoped RAG
- Real LLM answer generation
- MCP
- LangGraph
- Real embedding providers
- Backend auto-start from Tauri
- Complex Rust local backend logic
- Repository analysis
- Production packaging
- Authentication or user accounts
- Docker setup
- Redis or queues
- Major CSS framework migration
- VS Code integration
- LaTeX editing automation

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

Frontend:
- Tauri + React + TypeScript + Vite frontend shell (`frontend/`)
- Fetch-based local API client for `http://127.0.0.1:8081`
- No backend auto-start, no Rust backend API
- Stage 12 layout uses local React state for Chat/Library/Notes page
  switching; do not add routing dependencies without a concrete need
- Book Library UI stores `file_path` as backend metadata and can open it
  externally through Tauri in the desktop app; it does not preview,
  parse, upload, copy, or read file contents

Planned later:
- LangGraph
- Real embedding provider integration and production-quality RAG Q&A
- Semantic memory embeddings and long-term memory vector search
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
