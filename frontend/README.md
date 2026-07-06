# Personal Learning Agent Frontend

Stage 25 adds multi-book RAG in Chat. Users can select multiple indexed
Library items, ask one question, and receive an answer with citations
that identify which selected book each source chunk came from. The
FastAPI backend must be started separately on `http://127.0.0.1:8081`.

This project uses the `pla` conda environment for backend work. Do not
create a project `.venv`, and do not commit `.env` files.

## Backend

```bash
conda activate pla
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8081
```

```bash
conda activate pla
cd backend
pytest
```

```bash
conda activate pla
cd backend
alembic upgrade head
```

## Frontend Commands

```bash
cd frontend
npm install
```

```bash
cd frontend
npm run dev
```

```bash
cd frontend
npm run build
```

```bash
cd frontend
npm run typecheck
```

```bash
cd frontend
npm run tauri dev
```

The frontend expects the backend at `http://127.0.0.1:8081` by default.
For local experiments only, set `VITE_BACKEND_URL` before starting Vite.
Do not put secrets in frontend environment files.

If `npm run dev` or `npm run tauri dev` reports that port `1420` is in
use, stop the existing local Vite/Tauri dev server and rerun the command.

## Current Features

- Sidebar navigation for Chat, Library, Notes, and Progress
- Chat page, opened by default, with global RAG, one-book RAG,
  multi-book RAG, backend status, and long-term memory tools
- Chat context selector supports zero, one, or many indexed Library
  items. Zero calls `POST /api/rag/query`, one calls
  `POST /api/rag/query/library-item`, and two or more call
  `POST /api/rag/query/library-items`
- Chat page Sources section for structured RAG citations
- Multi-book citations show source Library item metadata for each chunk
- Chat page `Create LaTeX Note` action for the latest RAG response
- Inline note draft review/edit/save panel in Chat
- Library page with Book Library metadata create/list/search/edit/archive
- Library item selection and detail metadata panel
- Library `Choose File` button in Tauri to fill `file_path` metadata
- Library `Open` button in Tauri for local `file_path` values
- Library `Index File` button for `.txt` and `.md` files
- Library detail `Generate Summary & Tags` action for indexed items
- Editable generated summary/topic tag draft with save-through-metadata update
- Notes page with LaTeX note create/list/view/edit/archive workflow
- Optional Notes association with an existing Library item
- Notes page `Export as .tex` action in the Tauri desktop app
- Notes Workspace section with local folder selection and `Export to Workspace`
- Notes page `Open Exported File` action for the latest successfully exported `.tex`
- Progress page with recent learning events and simple event/source filters

## Current Limitations

- Does not auto-start the FastAPI backend
- Library `file_path` is still metadata stored in the backend
- Choosing a file only records its local path; it does not read, upload,
  copy, parse, or ingest the file
- Opening local files is performed by Tauri, not the backend
- Local file picking and opening should be tested with `npm run tauri dev`
- `Open File` opens the file with the system default app; `Index File`
  asks the backend to read supported text files and create chunks plus
  deterministic mock embeddings
- Library indexing currently supports `.txt` and `.md` only
- PDF parsing and indexing are not supported yet
- Generated Library metadata works only after indexing and does not
  auto-save; reviewed summaries are stored in `description`, and
  reviewed tags are stored in `topic_tags`
- Related notes and book chat sections are still placeholders in the
  Library detail panel
- Notes are stored in PostgreSQL through the backend API
- Chat-to-Notes generation is deterministic and template-based; it does
  not call a real LLM or create mathematical proofs
- Notes export writes the current editor content as UTF-8 `.tex`; if the
  selected path does not end with `.tex`, the app appends `.tex`
- Notes workspace path is stored locally in `localStorage` as
  `pla.notesWorkspacePath`; it is not stored in PostgreSQL
- Workspace export writes a sanitized `.tex` filename inside the
  workspace and creates `name-2.tex`, `name-3.tex`, etc. for duplicates
- `Open Exported File` works after either `Export as .tex` or
  `Export to Workspace`; it opens only the last successful exported
  `.tex` path with the system default application through Tauri opener
- Notes use a plain textarea; there is no rich editor, compiler, PDF preview, or PDF export
- Notes export requires the Tauri runtime and should be tested with `npm run tauri dev`
- No VS Code-specific integration, forced VS Code opening, LaTeX
  compilation, PDF generation, workspace scanning, file sync, file
  watcher, `.tex` import, recent exports list, workspace browser, or Git sync
- No internal PDF preview or file upload
- Progress is an event timeline only; there are no charts, analytics
  dashboard, calendar, goals, spaced repetition, reminders, or AI
  progress evaluation
- No automatic indexing, real embedding provider, automatic book summary
  jobs, whole-book deep summarization, or automatic cross-book
  comparison engine
- No real LLM summary/tag generation by default; metadata drafts are
  deterministic unless the backend adds an explicit provider path later
- Multi-book RAG is a retrieval-scope extension only; there is no
  reranking, hybrid search, BM25, query expansion, streaming, agent
  planner, or real LLM answer generation by default
- RAG citations show chunk/document/library metadata only; there is no
  PDF page navigation, source highlighting, internal document preview,
  CSL/BibTeX/Zotero integration, or citation formatting engine
- No MCP
- No LangGraph
- No real embedding provider integration
- No document ingestion UI or file parsing UI
- No repository analysis
- No production packaging workflow

The app opens files with the operating system default application. It
does not preview, parse, index, upload, copy, or read file contents.
