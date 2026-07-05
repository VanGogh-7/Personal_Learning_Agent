# Personal Learning Agent — Backend

## Purpose

Backend foundation for a local-first Personal Learning Agent that will
eventually help manage learning materials, notes, books, study progress,
and knowledge retrieval.

## Current Stage

MVP backend skeleton only:

- FastAPI app with health/status endpoints
- Environment-based configuration
- Minimal DeepSeek client shell (no API calls yet)
- Basic tests

RAG, LangGraph workflows, short/long-term memory, PostgreSQL + pgvector,
document ingestion, and the frontend (Tauri + React) are planned but
**not implemented yet**.

## Setup

1. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy the example environment file and fill in real values locally:

   ```bash
   cp .env.example .env
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

`.env` is never committed. Only `.env.example` (placeholders) is tracked.

## Running the API

```bash
uvicorn app.main:app --reload
```

- `GET /health` → `{"status": "ok"}`
- `GET /api/status` → app name, environment, and version

## Running Tests

```bash
pytest
```

Tests do not require a real DeepSeek API key and do not call any
external API.

## Roadmap (not yet implemented)

- Document ingestion
- RAG over personal learning materials
- Short-term and long-term memory
- Learning progress tracking
- Study plan generation
- LangGraph-based agent workflows
- PostgreSQL + pgvector storage
- Tauri + React desktop UI
