# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings, RAG, memory, Library
metadata, Notes, and a Tauri + React desktop frontend.

## Current Stage

Stage 31: Embedded PDF Viewer MVP.

The frontend now uses Bun + Tauri + React + Vite and opens to a
PDF-centered learning workspace:

```text
Bun + Tauri + React + Vite
PDF Library Explorer | Embedded PDF Workspace | Agent Chat
```

Stage 31 adds a minimal embedded PDF viewer to the center Workspace
panel. Selected local PDFs render in-app with loading/error states,
previous/next page controls, total page count, and zoom controls. The
existing `Open in system PDF reader` action remains available. PDF text
extraction, PDF indexing changes, page-aware citations, annotation,
highlighting, and selected-text workflows remain future work.

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

## What Stage 31 Does

- Adds `react-pdf` and `pdfjs-dist` to the Bun-managed frontend.
- Renders the selected local PDF inside the center Workspace panel.
- Shows selected PDF title, file metadata, indexed/unindexed status,
  current page, total pages, and zoom percentage.
- Supports previous page, next page, zoom in, and zoom out controls.
- Uses a minimal Tauri command to read selected local `.pdf` files as
  bytes for the embedded viewer.
- Preserves `Open in system PDF reader`.
- Preserves the Stage 29B Workspace layout, Stage 30 PDF-first Library
  UX, and Agent Chat behavior.

The long-term product direction is:

```text
PDF is the main workspace.
Library is a collapsible PDF file explorer.
Agent Chat is a dockable/collapsible assistant.
Calendar / Today Log will become the learning record.
Settings will stay simple: theme + long-term memory only.
```

## What Stage 31 Does Not Do

No PDF text extraction, PDF indexing changes, page-aware citations,
jump from citation to PDF page, selected text to chat, PDF annotation,
highlighting, OCR, calendar daily summary, settings page, theme system,
long-term memory settings UI, login/register, auth/user system, new
LangGraph nodes, planner, tool calling, multi-agent behavior, new RAG
algorithm, backend contract changes, or large backend changes.

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
