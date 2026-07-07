# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings, RAG, memory, Library
metadata, Notes, and a Tauri + React desktop frontend.

## Current Stage

Stage 30: PDF-First Library UX.

The frontend now uses Bun + Tauri + React + Vite and opens to a
PDF-centered learning workspace:

```text
Bun + Tauri + React + Vite
PDF Library Explorer | PDF Workspace placeholder | Agent Chat
```

Stage 30 makes the Library UX explicitly PDF-first. The official
user-facing supported Library format is now PDF. `.txt` and `.md`
support may remain in backend services for legacy/internal/test paths,
but the frontend Library picker and user-facing wording are oriented
around PDF books. Embedded PDF viewing, PDF text extraction, and PDF
indexing remain future work.

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

## What Stage 30 Does

- Restricts the frontend file picker to `.pdf` files.
- Defaults new Library file selections to `file_type = "pdf"`.
- Rejects non-PDF paths/types in visible Library create/edit forms.
- Marks legacy non-PDF Library records as unsupported in the PDF
  Library UI.
- Polishes the Workspace Library Explorer with PDF labels, normalized
  indexed/unindexed status, and filename/path metadata.
- Polishes the PDF Workspace placeholder around selected PDF title,
  file, status, and system-reader opening.
- Keeps selected indexed PDFs bound to the Agent Chat single-book scope.
- Keeps the Stage 29A Bun workflow and Stage 29B Workspace layout.

The long-term product direction is:

```text
PDF is the main workspace.
Library is a collapsible PDF file explorer.
Agent Chat is a dockable/collapsible assistant.
Calendar / Today Log will become the learning record.
Settings will stay simple: theme + long-term memory only.
```

## What Stage 30 Does Not Do

No embedded PDF viewer, PDF.js/react-pdf integration, PDF text
extraction, page-aware citations, PDF indexing changes, calendar daily
summary, settings page, theme system, long-term memory settings UI,
login/register, auth/user system, new LangGraph nodes, planner, tool
calling, multi-agent behavior, new RAG algorithm, backend contract
changes, or large backend changes.

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
