# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings, RAG, memory, Library
metadata, Notes, and a Tauri + React desktop frontend.

## Current Stage

Stage 29B: Workspace Layout Refactor MVP.

The frontend now uses Bun + Tauri + React + Vite and opens to a
PDF-centered learning workspace:

```text
Bun + Tauri + React + Vite
PDF Library Explorer | PDF Workspace placeholder | Agent Chat
```

The Library is a collapsible PDF/book explorer, the center pane is a
future PDF viewer placeholder, and Agent Chat is a docked/collapsible
assistant. Agent Chat still uses `POST /api/agent/chat`, global/
single-book/multi-book behavior, citations, retrieved chunks, and
Chat-to-Notes compatibility. Selecting an indexed Library item in the
Workspace prefers that item as the current single-PDF chat scope.
Notes/LaTeX features remain in the codebase but are no longer the
primary product direction.

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

## What Stage 29B Does

- Makes Workspace the default frontend entry.
- Adds an IDE-like layout with a left PDF Library Explorer, center PDF
  Workspace placeholder, and right Agent Chat dock.
- Lets the Library and Agent Chat panels be hidden, shown, and resized.
- Persists panel visibility and widths in `localStorage` under
  `pla.workspace.layout`.
- Shows compact Library items with title, file type, status, and
  selected-item highlighting.
- Shows selected PDF metadata in the center placeholder and keeps the
  existing Tauri local-file opener available as "Open in system PDF
  reader".
- Updates navigation and wording toward Workspace, PDF Library, Agent
  Chat, and Learning Progress.
- Keeps Calendar/Today Log as the future learning-record direction.
- Keeps the Stage 29A Bun frontend workflow.

The long-term product direction is:

```text
PDF is the main workspace.
Library is a collapsible PDF file explorer.
Agent Chat is a dockable/collapsible assistant.
Calendar / Today Log will become the learning record.
Settings will stay simple: theme + long-term memory only.
```

## What Stage 29B Does Not Do

No embedded PDF viewer, PDF.js/react-pdf integration, PDF parsing, PDF
extraction, page-aware citations, calendar daily summaries, settings
page, theme system, long-term memory settings UI, auth/user system, new
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
