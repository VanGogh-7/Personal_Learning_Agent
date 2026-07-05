# Personal Learning Agent Frontend

Stage 10 adds a minimal Book Library MVP to the Tauri + React +
TypeScript frontend shell. The FastAPI backend must be started
separately on `http://127.0.0.1:8081`.

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

- Backend health/status check
- Book Library metadata create/list/search/edit/archive
- RAG query form
- Long-term memory create form
- Long-term memory list/search

## Current Limitations

- Does not auto-start the FastAPI backend
- Library `file_path` is metadata only
- No local file opening through Tauri
- No PDF preview or file upload
- No automatic document ingestion from library items
- No MCP
- No LangGraph
- No real embedding provider integration
- No document ingestion UI or file parsing UI
- No repository analysis
- No production packaging workflow
