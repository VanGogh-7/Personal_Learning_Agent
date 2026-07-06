# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings, RAG, memory, Library
metadata, Notes, and a Tauri + React desktop frontend.

## Current Stage

Stage 21: Real LLM Integration Boundary.

RAG answer generation now goes through a small backend LLM provider
abstraction:

```text
RAG caller -> LLM provider interface -> deterministic provider by default
```

The default provider is deterministic/mock, so local development and
tests do not require real API keys or network calls. A DeepSeek
OpenAI-compatible provider is optional and must be explicitly enabled
with backend environment/config values.

## Configuration

Use the `pla` conda environment for backend work. The backend runs on
`127.0.0.1:8081`, and the frontend connects to
`http://127.0.0.1:8081`.

Example placeholders are tracked in `backend/.env.example` only:

```env
LLM_PROVIDER=deterministic
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

Real DeepSeek mode is opt-in:

```env
LLM_PROVIDER=deepseek
```

Do not commit real `.env` files or expose API keys to the frontend.

## What Stage 21 Does

- Adds a backend LLM provider interface.
- Keeps deterministic RAG answer behavior as the default.
- Adds a DeepSeek/OpenAI-compatible provider behind explicit config.
- Keeps global RAG retrieval and book-scoped RAG retrieval unchanged.
- Keeps Chat-to-Notes deterministic/template-based by default.
- Adds tests that do not require real API calls or real API keys.

## What Stage 21 Does Not Do

No LangGraph, agents, tool calling, MCP, streaming, function calling,
real embedding provider, retrieval rewrite, automatic book summaries,
whole-book summarization, frontend settings page, background jobs,
authentication, Docker changes, or cloud deployment.

## Commands

Backend tests:

```bash
conda activate pla
cd backend
pytest
```

Frontend build:

```bash
cd frontend
npm run build
```

See `backend/README.md` and `frontend/README.md` for detailed setup and
development notes.
