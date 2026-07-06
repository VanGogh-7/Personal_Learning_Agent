# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings, RAG, memory, Library
metadata, Notes, and a Tauri + React desktop frontend.

## Current Stage

Stage 25: Multi-Book RAG MVP.

The Chat page can now scope a RAG question to multiple selected indexed
Library items:

```text
indexed Library item A + indexed Library item B -> selected Chat context -> scoped RAG
```

The backend retrieves only chunks attached to the selected books,
returns structured citations that identify the source book, preserves
session memory behavior, and records a learning event for successful
multi-book questions.

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

## What Stage 25 Does

- Adds `POST /api/rag/query/library-items`.
- Accepts `library_item_ids`, `question`, `top_k`, optional
  `session_id`, and `include_long_term_memory`.
- Filters retrieval in the backend to documents whose
  `documents.library_item_id` is one of the selected IDs.
- Returns `selected_library_items`, retrieved chunks, and structured
  citations with `library_item_id`, title, author, document, chunk, and
  score metadata.
- Updates Chat so users can select zero, one, or many indexed Library
  items. Zero uses global RAG, one uses the existing single-book
  endpoint, and two or more use the new multi-book endpoint.
- Records `multi_book_rag_question_asked` after successful multi-book
  RAG responses.

Example request:

```json
{
  "library_item_ids": ["00000000-0000-0000-0000-000000000000"],
  "question": "Compare the definitions in these selected books.",
  "top_k": 5,
  "include_long_term_memory": false
}
```

## What Stage 25 Does Not Do

No LangGraph, graph design, agent planning, tool calling, MCP,
multi-agent systems, streaming, reranking, hybrid search, BM25,
full-text search, query expansion, real embedding providers, embedding
dimension changes, chunking/indexing changes, PDF/DOCX/LaTeX parsing,
OCR, knowledge graph, whole-book synthesis, automatic cross-book
comparison engine, background jobs, authentication, deployment, or
large UI redesign.

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
