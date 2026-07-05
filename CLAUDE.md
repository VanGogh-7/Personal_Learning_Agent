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

Current active stage: Stage 2: Document ingestion MVP.

Do not implement the full product at once.

The default backend development port is `8081`.

---

## Current Development Scope

Stage 1 (completed): a clean backend skeleton — FastAPI app setup,
environment variable configuration, `.env.example`, health/status
endpoints, minimal DeepSeek client module, basic tests, README setup
instructions, clean backend directory structure.

The current goal (Stage 2) is a minimal document ingestion module for
plain text and Markdown content only.

Allowed in the current stage:
- Ingestion module (`backend/app/ingestion/`)
- Character-based text chunking
- Loading `.txt` and `.md` files from `backend/data` only
- Minimal FastAPI routes under `/api/ingestion`
- Tests for chunking, file loading, and the ingestion routes
- README updates documenting the ingestion endpoints

Do not implement yet:
- RAG
- Embeddings
- LangGraph workflows
- Long-term memory
- Short-term memory
- PostgreSQL schema
- pgvector
- Frontend
- Tauri
- MCP
- PDF/LaTeX parsing
- Recursive directory scanning
- Repository analysis
- Multi-agent workflows
- Email/calendar reminders
- Automatic local file modification outside `backend/data`

---

## Tech Stack

Backend:
- Python
- FastAPI
- pytest

Planned later:
- LangGraph
- PostgreSQL
- pgvector
- SQLAlchemy or SQLModel
- Alembic
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