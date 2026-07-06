# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings, RAG, memory, Library
metadata, Notes, and a Tauri + React desktop frontend.

## Current Stage

Stage 28: Agent Chat Stabilization / Regression Polish.

The Chat page uses the LangGraph-backed agent chat endpoint and now has
small reliability and clarity polish around scope display, citations,
empty states, errors, and Chat-to-Notes compatibility:

```text
Chat page -> POST /api/agent/chat -> ChatRAGGraph -> existing RAG services
```

Global, single-book, and multi-book contexts still work, citations and
retrieved chunks still display, and Chat-to-Notes remains compatible.
LangGraph remains orchestration-only.

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

## What Stage 28 Does

- Makes the active Chat scope explicit: Global RAG, Single Book, or
  Multi-Book with selected titles.
- Improves citation/source readability for book title, author, document
  path, chunk index, excerpt, and score.
- Shows a clear empty retrieval message when no chunks or citations are
  returned.
- Normalizes common user-facing agent chat errors without exposing
  internals.
- Keeps submit/context controls stable while an agent chat request is
  running.
- Preserves Chat-to-Notes behavior for global, single-book, and
  multi-book responses.
- Keeps LangGraph orchestration-only and existing backend RAG endpoints
  available.

Example request:

```json
{
  "question": "Compare the definitions in these selected books.",
  "scope_type": "multi_book",
  "library_item_id": null,
  "library_item_ids": ["00000000-0000-0000-0000-000000000000"],
  "top_k": 5,
  "session_id": "optional-session-id",
  "include_long_term_memory": false
}
```

## What Stage 28 Does Not Do

No open-ended agent planner, tool calling, MCP, multi-agent system,
autonomous behavior, reflection loop, retry loop, self-critique,
streaming, function calling, settings page, login/user system, theme
system, graph visualization, new graph nodes, new RAG algorithm,
reranking, hybrid search, real embeddings, PDF parsing, or large UI
redesign.

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
npm run build
```

See `backend/README.md` and `frontend/README.md` for detailed setup and
development notes.
