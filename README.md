# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings, RAG, memory, Library
metadata, Notes, and a Tauri + React desktop frontend.

## Current Stage

Stage 26: Chat RAG Graph Boundary MVP.

The backend now exposes a minimal LangGraph orchestration boundary for
the existing Chat RAG workflow:

```text
POST /api/agent/chat -> ChatRAGGraph -> existing RAG/memory/citation/LLM/event services
```

LangGraph orchestrates the current services; it does not replace
retrieval, indexing, citation building, memory, learning events, or the
LLM provider boundary.

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

## What Stage 26 Does

- Adds the `langgraph` backend dependency.
- Adds `backend/app/graphs/chat_rag_graph.py` with a small linear graph:
  validate input -> resolve scope -> load memory -> retrieve chunks ->
  build citations -> build prompt -> generate answer -> save memory ->
  record learning event -> format response.
- Adds `POST /api/agent/chat`.
- Supports `scope_type` values `global`, `single_book`, and
  `multi_book` while reusing existing retrieval services.
- Returns an existing-RAG-compatible response with `answer`,
  `selected_library_items`, retrieved chunks, citations, session id,
  memory metadata, and `scope_type`.
- Records one `agent_chat_question_asked` learning event per successful
  graph response.
- Keeps existing RAG endpoints available.

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

## What Stage 26 Does Not Do

No open-ended agent planner, tool calling, MCP, multi-agent system,
autonomous behavior, reflection loop, retry loop, self-critique,
streaming, function calling, frontend settings page, replacing existing
RAG endpoints, graph-based Notes/study/book-summary workflows, real
embedding provider, embedding dimension changes, chunking/indexing
changes, reranking, hybrid search, BM25, full-text search, query
expansion, PDF/DOCX/LaTeX parsing, OCR, knowledge graph, background
jobs, authentication, deployment, or large UI redesign.

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
