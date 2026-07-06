# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings, RAG, memory, Library
metadata, Notes, and a Tauri + React desktop frontend.

## Current Stage

Stage 27: Agent Chat Frontend Integration MVP.

The Chat page now sends RAG questions through the LangGraph-backed
agent chat endpoint while preserving the existing Chat experience:

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

## What Stage 27 Does

- Adds frontend API types and client support for `POST /api/agent/chat`.
- Updates Chat query submission to map selected books to
  `scope_type`: zero selected books -> `global`, one -> `single_book`,
  two or more -> `multi_book`.
- Preserves the existing Chat UI, Sources/citations display, retrieved
  chunk display, loading/error states, long-term memory option, and
  Chat-to-Notes workflow.
- Keeps the existing backend RAG endpoints available:
  `POST /api/rag/query`, `POST /api/rag/query/library-item`, and
  `POST /api/rag/query/library-items`.

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

## What Stage 27 Does Not Do

No open-ended agent planner, tool calling, MCP, multi-agent system,
autonomous behavior, reflection loop, retry loop, self-critique,
streaming, function calling, settings page, login/user system, theme
system, graph visualization, new graph nodes, replacing existing RAG
endpoints, new RAG algorithm, reranking, hybrid search, real
embeddings, PDF parsing, or large UI redesign.

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
