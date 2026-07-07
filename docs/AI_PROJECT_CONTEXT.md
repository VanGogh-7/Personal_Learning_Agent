# AI Project Context

This file is for ChatGPT and future AI assistants so they do not give
incorrect project guidance. Keep it updated when the product direction or
stack changes materially.

---

## Product Direction

The app is an **IDE-like PDF Learning Workspace**:

```text
PDF Library Explorer | Embedded PDF Workspace | Agent Chat
```

- **PDF is the main workspace.** The center panel shows the selected
  PDF with an embedded viewer.
- **Library** is a collapsible PDF file-system-like explorer on the left.
- **Agent Chat** is a docked/collapsible assistant on the right.
- **Today Log** is the learning-record page. Calendar-style expansion is
  planned later.
- **Settings** will stay simple: theme + long-term memory only.
- **Notes/LaTeX** is **legacy/secondary** — do not emphasize it as the
  primary product direction and do not delete it unless the user
  explicitly asks.

---

## Current Stage Status

- **Stages 1–32 are completed** (backend skeleton through PDF text extraction / page-aware indexing).
- **Stage 33 (Today Log / Calendar MVP)** is handled separately from
  the current backend pipeline work.
- **Stage 34 (Backend PDF-to-RAG Pipeline MVP)** is completed.
- **Stage 35 (Backend Dual-Agent LangGraph MVP)** is completed.
- **Stage 36 (Real LLM Provider Integration) is completed.**
- **Stage 36A (Zhipu Real Embedding + DeepSeek Single-Book RAG Smoke
  Test) is current.**
- **Stage 29A** migrated the frontend workflow from npm to Bun.
- **Stage 29B** refactored the frontend into the IDE-like Workspace
  layout with resizable/collapsible panels and localStorage persistence.
- **Stage 30** made the Library and Workspace PDF-first (file picker
  restricts `.pdf`, non-PDF items marked unsupported).

Stage 36 wires the backend LLM provider boundary into Agent Chat
synthesis. Stage 36A adds a real Zhipu embedding provider and
backend-only scripts for one-book PDF RAG smoke testing. The existing
`/api/agent/chat` endpoint remains the Agent Chat API:

```text
User question -> Router -> Local/Web evidence -> Synthesis prompt -> configured LLM provider
```

`LLM_PROVIDER=deterministic` and `EMBEDDING_PROVIDER=mock` remain the
test/default providers and require no API keys or network access.
`LLM_PROVIDER=deepseek` enables the real OpenAI-compatible DeepSeek
provider using `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and
`DEEPSEEK_MODEL` from `backend/.env`. `EMBEDDING_PROVIDER=zhipu`
enables Zhipu embeddings using `ZHIPU_API_KEY`,
`ZHIPU_EMBEDDING_MODEL=embedding-3`, and
`ZHIPU_EMBEDDING_DIMENSION=1024`. Secrets must stay backend-only and
must not be logged or exposed to the frontend. Tests should use
deterministic providers or mocked HTTP clients only.

---

## Stack and Commands

### Backend

```bash
conda activate pla
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8081
pytest
alembic upgrade head
```

- Python 3, FastAPI, PostgreSQL + pgvector, SQLAlchemy 2.x, Alembic,
  LangGraph, pytest, pypdf.
- Backend runs on `127.0.0.1:8081`.
- `LLM_PROVIDER=deterministic` is the default; `deepseek` is opt-in.
- `EMBEDDING_PROVIDER=mock` is the default; `zhipu` is opt-in for real
  embeddings.
- API keys must never be committed, logged, or exposed to the frontend.

Stage 36A backend smoke commands:

```bash
cd backend
alembic upgrade head
python scripts/index_pdf.py "../Analysis I (Herbert Amann etc.).pdf"
python scripts/ask_book.py --library-item-id <library_item_id> \
  "What does this book say about completeness, Banach spaces, or metric spaces? Answer with citations."
```

Stage 36A sets `document_chunks.embedding` to `vector(1024)`. Its
Alembic migration clears existing stored embeddings; re-index affected
Library items after applying it. Do not commit real PDF books.

### Frontend

```bash
cd frontend
bun install
bun run build
bun run dev
bun run tauri dev
```

- **Bun** is the package manager and script runner (not npm).
- `bun.lock` is the lockfile; `package-lock.json` was removed in 29A.
- Tauri v2, React 18, Vite 8, TypeScript.
- Vite dev server on `127.0.0.1:1420`.
- `bun run tauri dev` requires a Rust toolchain.

---

## Architecture Principles

- **LangGraph is the orchestration layer only.** Existing services own
  business logic (RAG, memory, citations, learning events). Do NOT move
  RAG, citation, memory, or learning-event logic into graph nodes
  unnecessarily.
- **Avoid large backend refactors for frontend-only stages.** The
  backend API contracts should remain stable across frontend work.
- **Preserve legacy Notes/LaTeX** code unless explicitly asked to
  remove it. Notes are no longer the primary product direction but
  remain in the codebase.
- **Tauri commands** in `main.rs` follow existing patterns (`write_tex_note_file`,
  `export_tex_note_to_workspace`, `read_pdf_file`). New commands should
  include path/extension/size validations.
- **CSP** is in `tauri.conf.json`. The embedded PDF viewer required
  adding `img-src 'self' data: blob:; worker-src 'self' blob:;`.

---

## Product Scope Boundaries

Do **NOT** casually add or suggest:

- Login / register / auth / multi-user accounts
- Large settings system beyond theme + long-term memory
- Planner / multi-agent behavior / open-ended agents
- OCR, PDF annotation, highlighting
- Major RAG algorithm rewrites (reranking, hybrid search, BM25)
- Real embedding providers (deterministic mocks are the default)

These require an explicit stage decision from the developer.

---

## Near-Term Roadmap (Expected)

| Stage | Name | Status |
|-------|------|--------|
| 29A   | Frontend Bun Migration | completed |
| 29B   | Workspace Layout Refactor MVP | completed |
| 30    | PDF-First Library UX | completed |
| 31    | Embedded PDF Viewer MVP | completed |
| 32    | PDF Text Extraction / Page-Aware Indexing | completed |
| 33    | Today Log / Calendar MVP | separate/integration work |
| 34    | Backend PDF-to-RAG Pipeline MVP | completed |
| 35    | Backend Dual-Agent LangGraph MVP | completed |
| **36** | **Real LLM Provider Integration** | **current** |
| 37    | Agent-generated Daily Summary | planned |
| 38    | Simple Settings MVP | planned |

---

## Guidance for Future AI Assistants

1. **Keep implementation prompts concise.** Respect the stage boundary
   and do not implement features from future stages.
2. **Do not suggest deleting Notes/LaTeX** unless the user explicitly
   asks to retire it.
3. **Do not suggest user/auth/login features** unless explicitly
   requested by the developer.
4. **Prefer incremental, testable changes.** Each stage should be
   buildable and reviewable independently.
5. **Use Bun commands for frontend** (`bun install`, `bun run build`,
   `bun run tauri dev`), never npm.
6. **Use backend port 8081** and the `pla` conda environment.
7. **Run `bun run build` and `bun run typecheck`** after any frontend
   change. If Rust code changes, also run `cargo check` in
   `frontend/src-tauri/`.
8. **Check the CSP** in `frontend/src-tauri/tauri.conf.json` when
   adding new resource types (workers, images, etc.).
