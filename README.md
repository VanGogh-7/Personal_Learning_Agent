# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings, RAG, memory, Library
metadata, Notes, and a Tauri + React desktop frontend.

## Current Stage

Stage 34: Backend PDF-to-RAG Pipeline MVP.

The frontend now uses Bun + Tauri + React + Vite and opens to a
PDF-centered learning workspace:

```text
Bun + Tauri + React + Vite
PDF Library Explorer | Embedded PDF Workspace | Agent Chat
```

Stage 34 hardens and tests the backend PDF-to-RAG path end to end:

```text
PDF Library item -> pypdf extraction -> page-aware chunks -> embeddings
-> pgvector storage -> retrieval -> LangGraph Agent Chat -> citations
```

Frontend feature expansion is paused for this stage. The existing
workspace, embedded PDF viewer, Agent Chat UI, and Today Log work remain
separate from the Stage 34 backend integration work.

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

## What Stage 34 Does

- Reuses the existing Library item indexing flow for local PDF files.
- Validates PDF source paths and keeps clear failures for missing,
  unsupported, unreadable, or invalid files.
- Preserves Stage 32 page-aware metadata on indexed PDF chunks.
- Keeps deterministic mock embeddings as the default while allowing the
  indexing service to receive an explicit embedding provider for tests.
- Verifies the backend pipeline through `/api/agent/chat`, including
  retrieval, LangGraph orchestration, answer generation, learning events,
  and structured page-aware citations.
- Adds no new database schema or Alembic migration.

The long-term product direction is:

```text
PDF is the main workspace.
Library is a collapsible PDF file explorer.
Agent Chat is a dockable/collapsible assistant.
Today Log is the learning record; Calendar remains future expansion.
Settings will stay simple: theme + long-term memory only.
```

## What Stage 34 Does Not Do

No new frontend pages, Today Log expansion, embedded PDF viewer changes,
PDF annotation/highlighting, selected text to chat, jump-to-page from
citations, OCR, planner/tool calling, multi-agent behavior, auth,
settings, reranking, hybrid search, BM25, new RAG algorithm, or major
backend/frontend redesign.

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
