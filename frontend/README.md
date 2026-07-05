# Personal Learning Agent Frontend

Stage 18 adds local `.tex` export from the Tauri desktop Notes page.
Existing database-backed LaTeX notes can be saved to user-selected local
files. The FastAPI backend must be started separately on
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

- Sidebar navigation for Chat, Library, and Notes
- Chat page, opened by default, with global RAG, book-scoped RAG,
  backend status, and long-term memory tools
- Chat page `Create LaTeX Note` action for the latest RAG response
- Inline note draft review/edit/save panel in Chat
- Library page with Book Library metadata create/list/search/edit/archive
- Library item selection and detail metadata panel
- Library `Choose File` button in Tauri to fill `file_path` metadata
- Library `Open` button in Tauri for local `file_path` values
- Library `Index File` button for `.txt` and `.md` files
- Notes page with LaTeX note create/list/view/edit/archive workflow
- Optional Notes association with an existing Library item
- Notes page `Export as .tex` action in the Tauri desktop app

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
- Library detail summary, related notes, and book chat sections are placeholders only
- Notes are stored in PostgreSQL through the backend API
- Chat-to-Notes generation is deterministic and template-based; it does
  not call a real LLM or create mathematical proofs
- Notes export writes the current editor content as UTF-8 `.tex`; if the
  selected path does not end with `.tex`, the app appends `.tex`
- Notes use a plain textarea; there is no rich editor, compiler, PDF preview, or PDF export
- Notes export requires the Tauri runtime and should be tested with `npm run tauri dev`
- No internal PDF preview or file upload
- No automatic indexing, real embedding provider, automatic book summary, or multi-book RAG
- Book-scoped RAG supports one selected indexed Library item at a time;
  no multi-book RAG, reranking, or real LLM answer generation
- No MCP
- No LangGraph
- No real embedding provider integration
- No document ingestion UI or file parsing UI
- No repository analysis
- No production packaging workflow

The app opens files with the operating system default application. It
does not preview, parse, index, upload, copy, or read file contents.
