# Personal Learning Agent Frontend

Stage 31 adds a minimal embedded PDF viewer to the Workspace. The stack
remains Bun + Tauri + React + Vite. The default page is the
IDE-like Workspace with a collapsible/resizable PDF Library Explorer, a
center embedded PDF Workspace, and a collapsible/resizable Agent Chat
dock. The FastAPI backend must be started separately on
`http://127.0.0.1:8081`.

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
bun install
```

```bash
cd frontend
bun run dev
```

```bash
cd frontend
bun run build
```

```bash
cd frontend
bun run typecheck
```

```bash
cd frontend
bun run tauri dev
```

The frontend expects the backend at `http://127.0.0.1:8081` by default.
For local experiments only, set `VITE_BACKEND_URL` before starting Vite.
Do not put secrets in frontend environment files.

`bun.lock` is the frontend dependency lockfile. Do not keep
`package-lock.json` alongside it after the Bun migration.

If `bun run dev` or `bun run tauri dev` reports that port `1420` is in
use, stop the existing local Vite/Tauri dev server and rerun the command.

## Current Features

- Bun is used for frontend dependency management and scripts
- Sidebar navigation emphasizes Workspace and Learning Progress
- Workspace page, opened by default, with PDF Library Explorer, PDF
  Workspace viewer, and Agent Chat dock
- Left PDF Library panel lists existing Library items compactly with
  title, PDF/unsupported label, indexed/unindexed status, filename/path,
  and selected-item highlighting
- Center PDF Workspace shows "No PDF selected" until an item is
  selected, then shows selected title, file, status, PDF support, and
  an embedded PDF viewer
- Embedded PDF viewer renders selected local PDFs with loading/error
  states, current page, total pages, previous/next controls, and zoom
  controls
- Center workspace exposes "Open in system PDF reader" for selected
  items that have a local `file_path`
- Library file picker is restricted to `.pdf` files
- New file-picker selections infer `file_type: "pdf"`
- Visible Library create/edit forms reject non-PDF paths and non-PDF
  file types
- Legacy non-PDF records are marked unsupported in the PDF Library UI
- Left Library and right Agent Chat panels can be hidden, shown, and
  resized by dragging their panel borders
- Workspace panel visibility and widths persist in `localStorage` as
  `pla.workspace.layout`
- Agent Chat dock preserves `POST /api/agent/chat`, global RAG,
  one-book RAG, multi-book RAG, loading/error/empty states, citations,
  and Chat-to-Notes compatibility
- Selecting an indexed Library item in the Workspace prefers that item
  as the current single-PDF Agent Chat scope
- Agent Chat context selector supports zero, one, or many indexed
  Library items. Zero sends `scope_type: "global"` to
  `POST /api/agent/chat`, one sends `scope_type: "single_book"`, and
  two or more send `scope_type: "multi_book"`
- Agent Chat Sources section for structured RAG citations
- Multi-book citations show source Library item metadata for each chunk
- Empty citation/retrieval results show a clear no relevant chunks message
- Agent Chat `Create LaTeX Note` action for the latest RAG response
- Inline note draft review/edit/save panel in Agent Chat
- Legacy Library page with PDF Library metadata create/list/search/edit/archive
- Library item selection and detail metadata panel
- Library `Choose PDF` button in Tauri to fill `file_path` metadata
- Library `Open PDF` button in Tauri for local PDF `file_path` values
- PDF indexing is not exposed yet; legacy text indexing support may
  remain in backend services
- Library detail `Generate Summary & Tags` action for indexed items
- Editable generated summary/topic tag draft with save-through-metadata update
- Legacy Notes page with LaTeX note create/list/view/edit/archive workflow
- Optional Notes association with an existing Library item
- Notes page `Export as .tex` action in the Tauri desktop app
- Notes Workspace section with local folder selection and `Export to Workspace`
- Notes page `Open Exported File` action for the latest successfully exported `.tex`
- Learning Progress page with recent learning events and simple event/source filters

## Current Limitations

- Does not auto-start the FastAPI backend
- Library `file_path` is still metadata stored in the backend
- Choosing a file records its local path for Library metadata; selected
  PDFs are read locally by a Tauri command for embedded viewing only
- The embedded viewer renders local PDFs but does not parse, extract,
  upload, copy, ingest, annotate, or index them
- Opening local files is performed by Tauri, not the backend
- Local file picking and opening should be tested with `bun run tauri dev`
- `Open PDF` opens the file with the system default app
- User-facing Library format is PDF; existing `.txt` and `.md` support
  may remain in backend services for legacy/internal/test paths
- PDF parsing, text extraction, indexing, page-aware citations, and
  source highlighting are not supported yet
- Generated Library metadata works only for already indexed legacy
  items and does not auto-save; reviewed summaries are stored in
  `description`, and reviewed tags are stored in `topic_tags`
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
- Notes export requires the Tauri runtime and should be tested with `bun run tauri dev`
- No VS Code-specific integration, forced VS Code opening, LaTeX
  compilation, PDF generation, workspace scanning, file sync, file
  watcher, `.tex` import, recent exports list, workspace browser, or Git sync
- No PDF upload
- Progress is an event timeline only; there are no charts, analytics
  dashboard, calendar, goals, spaced repetition, reminders, or AI
  progress evaluation
- Calendar / Today Log is the planned learning-record direction but is
  not implemented in Stage 31
- Settings are planned to stay simple around theme and long-term memory,
  but no settings, theme, or long-term memory management UI was added in
  Stage 31
- Notes/LaTeX remains available as legacy functionality but is no
  longer the primary product direction
- No automatic indexing, real embedding provider, automatic book summary
  jobs, whole-book deep summarization, or automatic cross-book
  comparison engine
- No real LLM summary/tag generation by default; metadata drafts are
  deterministic unless the backend adds an explicit provider path later
- Multi-book RAG is a retrieval-scope extension only; there is no
  reranking, hybrid search, BM25, query expansion, streaming, agent
  planner, or real LLM answer generation by default
- Agent Chat uses the backend LangGraph boundary as orchestration only;
  there is no tool calling, planner, graph visualization, streaming, or
  frontend settings UI
- RAG citations show chunk/document/library metadata only; there is no
  citation-to-PDF-page navigation, source highlighting,
  CSL/BibTeX/Zotero integration, or citation formatting engine
- No MCP
- No real embedding provider integration
- No document ingestion UI or file parsing UI
- No repository analysis
- No production packaging workflow

The app opens files with the operating system default application. It
does not preview, parse, index, upload, copy, or read file contents.
