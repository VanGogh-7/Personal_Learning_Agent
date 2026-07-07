# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings, RAG, memory, Library
metadata, Notes, and a Tauri + React desktop frontend.

## Current Stage

Stage 32: PDF Text Extraction / Page-Aware Indexing.

The frontend now uses Bun + Tauri + React + Vite and opens to a
PDF-centered learning workspace:

```text
Bun + Tauri + React + Vite
PDF Library Explorer | Embedded PDF Workspace | Agent Chat
```

Stage 32 adds backend PDF text extraction and page-aware indexing.
Local PDF Library items can be indexed page by page using `pypdf`;
indexed chunks store nullable `page_start` and `page_end` metadata, and
RAG citations now include additive page fields when page metadata is
available. The embedded Workspace viewer and `Open in system PDF
reader` action remain available.

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

## What Stage 32 Does

- Adds `pypdf` as the backend PDF extraction dependency.
- Extracts local PDF text page by page during Library indexing.
- Stores PDF chunk page metadata in `document_chunks.page_start` and
  `document_chunks.page_end`.
- Keeps `.txt` and `.md` legacy/internal indexing paths working.
- Adds page metadata to RAG citations and retrieved chunks without
  removing existing response fields.
- Shows citation page metadata in the frontend Agent Chat Sources UI.
- Preserves existing RAG retrieval behavior, LangGraph orchestration,
  Agent Chat scope behavior, embedded PDF viewing, and system-reader
  opening.

The long-term product direction is:

```text
PDF is the main workspace.
Library is a collapsible PDF file explorer.
Agent Chat is a dockable/collapsible assistant.
Calendar / Today Log will become the learning record.
Settings will stay simple: theme + long-term memory only.
```

## What Stage 32 Does Not Do

No OCR, PDF annotation, highlighting, selected text to chat, jump from
citation to PDF page, calendar daily summary, settings page, theme
system, long-term memory settings UI, login/register, auth/user system,
new LangGraph nodes, planner, tool calling, multi-agent behavior, major
RAG algorithm rewrite, reranking, hybrid search, BM25, or large backend
architecture refactor.

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
