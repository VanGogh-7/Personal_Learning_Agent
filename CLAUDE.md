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

Current stage: MVP backend foundation.

Do not implement the full product at once.

The default backend development port is `8081`.

---

## Current Development Scope

The current goal is to build a clean backend skeleton only.

Allowed in the current stage:
- FastAPI app setup
- Environment variable configuration
- `.env.example`
- Health/status endpoints
- Minimal DeepSeek client module
- Basic tests
- README setup instructions
- Clean backend directory structure

Do not implement yet:
- RAG
- LangGraph workflows
- Long-term memory
- Short-term memory
- PostgreSQL schema
- pgvector
- Document ingestion
- Frontend
- Tauri
- MCP
- Multi-agent workflows
- Email/calendar reminders
- Automatic local file modification

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