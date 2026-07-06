# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings, RAG, memory, Library
metadata, Notes, and a Tauri + React desktop frontend.

## Current Stage

Stage 23: Book Summary + Topic Extraction.

Indexed Library items can now generate a deterministic summary draft
and topic tag draft from their indexed chunks:

```text
indexed Library item -> representative chunks -> summary/tag draft -> review/edit -> PATCH metadata
```

The draft endpoint does not save automatically. The user reviews or
edits the generated summary and tags in the Library detail panel, then
saves them through the existing Library item update flow. Summary drafts
use `library_items.description`; topic tag drafts use
`library_items.topic_tags`.

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

## What Stage 23 Does

- Adds `POST /api/library/items/{item_id}/metadata-draft`.
- Works only for indexed Library items with associated document chunks.
- Selects representative chunks deterministically from indexed chunks.
- Generates a deterministic template-based summary draft.
- Extracts deterministic topic tag drafts with simple token frequency.
- Adds Library detail UI to generate, review, edit, cancel, and save
  summary/tags.
- Saves reviewed metadata through existing `PATCH /api/library/items/{item_id}`.
- Adds tests that do not require real API calls or network access.

## What Stage 23 Does Not Do

No LangGraph, agents, tool calling, MCP, streaming, background jobs,
automatic indexing-triggered summary jobs, queues, real embedding
providers, OpenAI/DeepSeek embedding calls, embedding dimension changes,
retrieval replacement, parser changes, PDF/DOCX/LaTeX/OCR extraction,
whole-book deep summarization, multi-book synthesis, knowledge graph,
prompt template database, citation formatting engines, authentication,
cloud deployment, or large UI redesign. Real LLM summary/tag generation
is not required and is not the default.

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
