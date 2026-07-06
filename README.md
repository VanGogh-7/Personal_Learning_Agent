# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings, RAG, memory, Library
metadata, Notes, and a Tauri + React desktop frontend.

## Current Stage

Stage 22: Better Retrieval / Citations / Chunk Metadata.

RAG responses now include structured citation/source metadata for each
retrieved chunk:

```text
RAG retrieval -> retrieved chunks -> citations -> Chat page Sources
```

The retrieval algorithm is unchanged. Global RAG and book-scoped RAG
still use the existing pgvector/mock-embedding retrieval path, but each
response now exposes a top-level `citations` list and maps each
`retrieved_chunks` item to a citation.

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

## What Stage 22 Does

- Adds structured RAG citation metadata: `citation_id`, `chunk_id`,
  `document_id`, optional Library metadata, document title/source path,
  chunk index, score, excerpt, and content.
- Keeps existing `retrieved_chunks` fields for compatibility.
- Displays a compact Sources section on the Chat page.
- Keeps Chat-to-Notes deterministic/template-based by default.
- Keeps the Stage 21 deterministic/mock LLM provider default.
- Adds tests that do not require real API calls or network access.

## What Stage 22 Does Not Do

No reranking, hybrid search, BM25, query expansion, multi-book
reasoning, LangGraph, agents, tool calling, MCP, streaming, real
embedding provider, parser changes, PDF/DOCX/LaTeX/OCR extraction,
citation formatting engines, BibTeX/Zotero integration, authentication,
cloud deployment, or large UI redesign.

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
