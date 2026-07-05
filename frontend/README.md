# Personal Learning Agent Frontend

Stage 12 organizes the frontend into a three-page desktop workspace:
Chat, Library, and Notes. The FastAPI backend must be started separately on
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
- Chat page, opened by default, with RAG query, backend status, and long-term memory tools
- Library page with Book Library metadata create/list/search/edit/archive
- Library `Open` button in Tauri for local `file_path` values
- Notes page placeholder for a future LaTeX notes workflow

## Current Limitations

- Does not auto-start the FastAPI backend
- Library `file_path` is still metadata stored in the backend
- Opening local files is performed by Tauri, not the backend
- Local file opening should be tested with `npm run tauri dev`
- Notes page is a placeholder only; it does not create, save, compile, or export notes
- No internal PDF preview or file upload
- No automatic document ingestion from library items
- No MCP
- No LangGraph
- No real embedding provider integration
- No document ingestion UI or file parsing UI
- No repository analysis
- No production packaging workflow

The app opens files with the operating system default application. It
does not preview, parse, index, upload, copy, or read file contents.
