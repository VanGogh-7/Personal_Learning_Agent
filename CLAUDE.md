# CLAUDE.md

## Project Overview

This repository is for a Personal Learning Agent.

The long-term goal is to build a local-first agent that helps the user manage learning materials, notes, books, study progress, and knowledge retrieval.

The project will later support:
- Document ingestion
- RAG over personal learning materials
- Short-term and long-term memory
- Learning progress tracking
- Study plan generation
- LangGraph-based agent workflows
- PostgreSQL + pgvector storage
- Optional Tauri + React desktop UI

Stage 1: Backend skeleton — completed.
Stage 2: Document ingestion MVP — completed.
Stage 3: PostgreSQL schema — completed.
Stage 4: Embedding + pgvector MVP — completed.
Stage 5: Minimal RAG Q&A MVP — completed.
Stage 6: Short-term Memory MVP — completed.
Stage 7: Long-term Memory MVP — completed.
Stage 8: Tauri + React Frontend MVP — completed.
Stage 9: Backend/Frontend Integration Polish — completed.
Stage 10: Book Library MVP — completed.
Stage 11: Open Local Files from Desktop App — completed.
Stage 12: Frontend Layout Redesign MVP — completed.
Stage 13: Library Detail Page / Panel MVP — completed.
Stage 14: Library Indexing MVP — completed.
Stage 15: Book-Scoped RAG MVP — completed.
Stage 16: Notes MVP — completed.

Current active stage: Stage 17: Generate LaTeX Notes from Chat.

Do not implement the full product at once.

The default backend development port is `8081`.

Project stage roadmap:
1. Backend skeleton — completed
2. Document ingestion MVP — completed
3. PostgreSQL schema — completed
4. Embedding + pgvector — completed
5. Minimal RAG Q&A — completed
6. Short-term memory — completed
7. Long-term memory — completed
8. Tauri + React frontend — completed
9. Backend/frontend integration polish — completed
10. Book Library MVP — completed
11. Open local files from desktop app — completed
12. Frontend layout redesign — completed
13. Library detail page/panel — completed
14. Library indexing MVP — completed
15. Book-scoped RAG MVP — completed
16. Notes MVP — completed
17. Generate LaTeX Notes from Chat — current

---

## Current Development Scope

Stage 1 (completed): a clean backend skeleton — FastAPI app setup,
environment variable configuration, `.env.example`, health/status
endpoints, minimal DeepSeek client module, basic tests, README setup
instructions, clean backend directory structure.

Stage 2 (completed): a minimal document ingestion module for plain text
and Markdown content — character-based chunking, safe `.txt`/`.md`
loading from `backend/data`, `/api/ingestion` routes, and tests.

Stage 3 (completed): PostgreSQL schema support — `DATABASE_URL` config,
SQLAlchemy 2.x models, and Alembic migrations for `learning_sources`,
`documents`, `document_chunks`, and `agent_runs`.

Stage 4 (completed): a minimal embedding + pgvector MVP — proving the
pipeline of document chunk text → deterministic mock embedding →
vector stored in PostgreSQL → basic similarity search, via
`backend/app/embeddings/` and `backend/app/db/vector_search.py`.

Stage 5 (completed): a minimal RAG Q&A MVP — proving the pipeline of
user question → deterministic mock embedding → pgvector similarity
search over `document_chunks` → simple deterministic (extractive,
non-LLM) answer → answer plus retrieved chunks and source metadata, via
`backend/app/rag/` and `POST /api/rag/query`.

Stage 6 (completed): a minimal short-term memory MVP — a user question
(with an optional `session_id`) loads recent conversation turns for
that session, the deterministic answer generator notes when recent
context was considered, the current turn is saved afterward, and the
response includes `session_id` plus memory metadata, via
`backend/app/memory/short_term.py`.

Stage 7 (completed): a minimal long-term memory MVP — memories are
created **manually** through a small service/API, stored in PostgreSQL,
listable/searchable by type, importance, and keyword, and optionally
usable as small bounded deterministic context in RAG answers.

Stage 8 (completed): a minimal Tauri + React frontend MVP — a small
TypeScript/Vite UI under `frontend/` that calls the existing FastAPI
backend on `127.0.0.1:8081` for health/status, RAG query, and long-term
memory create/list/search. The backend remains independently started on
port `8081`.

Stage 9 (completed): backend/frontend integration polish — frontend API
types aligned with backend schemas, centralized backend URL handling,
safer fetch errors, clearer UI empty states, explicit local-development
CORS, and local development docs cleanup.

Stage 10 (completed): a Book Library MVP — manual registration,
listing, updating, archiving, and search/filtering of book or
learning-material metadata. Library items may store title, author,
description, `file_path`, `file_type`, topic tags, and status.

Stage 11 (completed): local file opening from the Tauri desktop app
only. `file_path` remains metadata stored by the backend. The desktop
frontend may ask Tauri to open that path externally with the system
default application.

Stage 12 (completed): frontend layout redesign MVP. The single long
page was refactored into a calm three-page desktop workspace with
sidebar navigation for Chat, Library, and Notes.

Stage 13 (completed): Library detail page/panel MVP. The Library page
can select a library item, view all key metadata in a structured detail
area, edit metadata, choose local files, and open local files externally.

Stage 14 (completed): Library Indexing MVP. The user can manually index
a registered Library item that points to a `.txt` or `.md` local file.
The backend reads that selected local file path, chunks text, generates
deterministic mock embeddings, persists document chunks with pgvector
embeddings, associates the document to the Library item, and marks the
item indexed.

Stage 15 (completed): Book-Scoped RAG MVP. The Chat page can select one
indexed Library item and send RAG queries to
`POST /api/rag/query/library-item`, retrieving only chunks connected to
that item's `documents.library_item_id`. Global `POST /api/rag/query`
continues to work unchanged.

Stage 16 (completed): Notes MVP. The Notes page is a minimal
database-backed LaTeX note manager. Users can create, list, view, edit,
and archive notes. Notes may optionally reference a Library item through
`notes.library_item_id`.

The current goal (Stage 17) is Generate LaTeX Notes from Chat. The user
can take the latest global or book-scoped Chat/RAG response, generate a
deterministic LaTeX note draft from the question, answer, retrieved
chunks, optional Library item metadata, and optional session id, review
or edit that draft, and save it through the existing Notes API.

Allowed in the current stage:
- Add deterministic/template-based note draft generation
- Add `POST /api/notes/from-chat/draft`
- Escape LaTeX-sensitive characters in generated content
- Include question, answer, optional book context, and retrieved chunk excerpts
- Add a Chat page `Create LaTeX Note` action after a RAG response
- Let the user review/edit title and LaTeX content before saving
- Save reviewed drafts through the existing `POST /api/notes` endpoint
- Add focused backend tests and update README/CLAUDE.md

Do not implement in Stage 17:
- Real LLM calls
- OpenAI/DeepSeek calls
- Real AI note generation
- Real summarization
- Real mathematical proof generation
- Real embedding calls
- LaTeX compilation
- PDF preview
- `.tex` file export
- Local notes workspace
- Opening notes in VS Code
- Opening notes with system default app
- Git sync
- Markdown editor
- Rich text editor
- WYSIWYG editor
- CodeMirror
- Monaco editor
- Collaborative editing
- Multi-note generation
- Whole-book summary generation
- Automatic note generation on every chat response
- Complex note templates
- Complex citation system
- Changing the existing Notes CRUD architecture
- Complex tagging UI
- Full-text search
- Multi-file notes
- Attachments
- PDF parsing
- PDF preview
- Internal PDF viewer
- react-pdf
- PDF.js
- DOCX parsing
- LaTeX parsing
- File upload
- Drag-and-drop upload
- Batch import
- Folder import
- Automatic background indexing
- Automatic metadata extraction
- Automatic book summary generation
- Advanced ranking or reranking
- Multi-book RAG
- Queue system
- Redis
- Celery/RQ
- Real embedding provider
- OpenAI/DeepSeek embedding calls
- Chat with this Book actual functionality
- Related notes actual functionality
- Real LLM summary generation
- Notes generation
- LaTeX generation
- VS Code integration
- Real LLM answer generation
- MCP
- LangGraph
- Real embedding providers
- Backend auto-start from Tauri
- Complex Rust local backend logic
- Repository analysis
- Production packaging
- Authentication or user accounts
- Docker setup
- Redis or queues
- Major CSS framework migration

---

## Tech Stack

Backend:
- Python
- FastAPI
- pytest
- PostgreSQL (schema layer only, via SQLAlchemy 2.x + Alembic)
- SQLAlchemy 2.x
- Alembic
- psycopg (v3)
- pgvector (nullable embedding column + basic similarity search only;
  embeddings are deterministic mocks, not a real provider)
- Minimal RAG Q&A (`backend/app/rag/`): deterministic mock embeddings +
  pgvector search + simple extractive answer generation; no real LLM or
  embedding provider
- Short-term memory (`backend/app/memory/short_term.py`): bounded,
  per-session `conversation_turns` in PostgreSQL; deterministic context
  only, no LLM summarization
- Long-term memory MVP (`backend/app/memory/long_term.py`): manually
  created `long_term_memories` in PostgreSQL, keyword (`ILIKE`) search
  only, deterministic bounded context only; no embeddings/vector search,
  no automatic extraction or promotion

Frontend:
- Tauri + React + TypeScript + Vite frontend shell (`frontend/`)
- Fetch-based local API client for `http://127.0.0.1:8081`
- No backend auto-start, no Rust backend API
- Stage 12 layout uses local React state for Chat/Library/Notes page
  switching; do not add routing dependencies without a concrete need
- Book Library UI stores `file_path` as backend metadata and can open it
  externally through Tauri in the desktop app; it does not preview,
  parse, upload, copy, or read file contents
- Library file picker may populate `file_path` and infer `file_type`,
  but must not read, upload, copy, parse, ingest, or validate files
- Stage 14 indexing reads `.txt` and `.md` library item paths on the
  backend only after the user clicks `Index File`
- Stage 14 uses deterministic mock embeddings only; no real embedding
  provider or LLM API calls
- Stage 15 book-scoped RAG retrieves from one selected indexed Library
  item only; Library summaries remain unimplemented
- Stage 16 Notes MVP stores LaTeX notes in PostgreSQL, optionally
  associates notes with Library items, and archives notes through soft
  status updates; it does not compile, preview, export, or generate
  notes
- Stage 17 Chat-to-Notes creates deterministic template-based LaTeX
  drafts from Chat/RAG responses and saves reviewed drafts through the
  existing Notes API; it does not call LLMs, summarize with AI, compile
  LaTeX, preview PDFs, or export files

Planned later:
- LangGraph
- Real embedding provider integration and production-quality RAG Q&A
- Semantic memory embeddings and long-term memory vector search
- Rust local backend
- MCP integration

LLM provider:
- DeepSeek API
- API key is stored in `.env`
- Use environment variables only

---

## Security Rules

Never print, log, commit, expose, or hard-code secrets.

Never read or modify `.env` unless explicitly asked.

`.env` must be ignored by Git.

Use `.env.example` for placeholder environment variables only.

Allowed example:

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
