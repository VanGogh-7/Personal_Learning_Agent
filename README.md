# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings, RAG, memory, Library
metadata, Notes, and a Tauri + React desktop frontend.

## Current Stage

Stage 35: Backend Dual-Agent LangGraph MVP.

The frontend now uses Bun + Tauri + React + Vite and opens to a
PDF-centered learning workspace:

```text
Bun + Tauri + React + Vite
PDF Library Explorer | Embedded PDF Workspace | Agent Chat
```

Stage 35 adds a fixed dual-agent orchestration path behind the existing
Agent Chat API:

```text
User question -> Router -> Local Library Agent and/or Web Research Agent
-> Synthesis -> Final answer
```

Frontend simplification is not part of this stage. The Local Library
Agent reuses the existing PDF/RAG retrieval and citation services. The
Web Research Agent is deterministic/mock by default and does not require
network access or API keys.

## Configuration

Use the `pla` conda environment for backend work. The backend runs on
`127.0.0.1:8081`, and the frontend connects to
`http://127.0.0.1:8081`.

Backend local configuration lives in `backend/.env`, which is
automatically loaded for local FastAPI startup and Alembic migrations.
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

## What Stage 35 Does

- Adds a deterministic router with `local_only`, `web_only`, and `both`
  routes.
- Adds fixed Local Library Agent and Web Research Agent service
  boundaries.
- Reuses existing pgvector retrieval, PDF chunk metadata, structured
  citations, memory, and learning-event behavior.
- Adds deterministic synthesis that combines local and/or web results.
- Extends `POST /api/agent/chat` responses additively with route,
  summaries, and web sources.
- Adds no new database schema or Alembic migration.

The long-term product direction is:

```text
PDF is the main workspace.
Library is a collapsible PDF file explorer.
Agent Chat is a dockable/collapsible assistant.
Today Log is the learning record; Calendar remains future expansion.
Settings will stay simple: theme + long-term memory only.
```

## What Stage 35 Does Not Do

No frontend simplification, new frontend pages, embedded PDF viewer
changes, OCR, PDF annotation/highlighting, citation jump-to-page,
auth/user accounts, large settings system, autonomous planner, broad
tool-calling framework, open-ended multi-agent behavior, new RAG
algorithm, BM25/hybrid search/reranking, or major backend rewrite.

## Commands

Install/update backend dependencies:

```bash
conda activate pla
cd backend
pip install -r requirements.txt
```

Backend tests:

```bash
conda activate pla
cd backend
pytest
```

Frontend build:

```bash
cd frontend
bun install
bun run build
```

See `backend/README.md` and `frontend/README.md` for detailed setup and
development notes.
