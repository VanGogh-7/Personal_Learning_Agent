# AGENT.md

## Project Identity

This repository is a LangGraph-based Personal Learning Agent. It is not
a PDF reader. The first MVP is scoped to a PDF Repository for knowledge
source management and Agent Chat as the main interaction surface.

## MVP Scope

- Repository + Agent Chat frontend.
- Add PDFs through the Tauri file picker.
- Copy imported PDFs into backend-managed storage.
- Extract text from born-digital PDFs.
- Chunk, embed, retrieve, and cite local Library evidence.
- Run `/api/agent/chat` through an explicit LangGraph dual-agent graph.
- Preserve local citations as `[S1]`, `[S2]`, etc.
- Preserve web sources as `[W1]`, `[W2]`, etc.

## MVP Non-Goals

Do not add or reintroduce these unless the user explicitly requests a
new stage for them:

- embedded PDF preview/reader
- citation click-to-page behavior
- local embedding model deployment
- OCR/scanned PDF support
- reranker, hybrid search, BM25, or query expansion
- Settings UI
- Calendar UI
- Notes UI
- broad tool calling or autonomous planning

## Architecture

- Frontend: Tauri + React + Bun + Vite.
- Backend: FastAPI + LangGraph.
- Database: PostgreSQL + pgvector.
- Embeddings: API-based provider with mock provider for tests.
- LLM: API-based provider with deterministic provider for tests.
- Web Research Agent: provider boundary with unavailable, mock, and
  optional Tavily modes.

## LangGraph Design

`POST /api/agent/chat` runs the MVP graph:

```text
Router Node
  -> Local Library Agent Node
  -> Web Research Agent Node
  -> Synthesis Node
```

- Router Node: deterministic route selection.
- Local Library Agent Node: pgvector retrieval over selected/local
  Library content and normalized `[S#]` citations.
- Web Research Agent Node: provider-backed structured web results and
  `[W#]` sources; unavailable providers return warnings, not crashes.
- Synthesis Node: combines local and web outputs while keeping local
  citations and web sources structurally separate.

Routes:

- `local_only`: questions about selected books/PDFs/library material,
  including phrases like "this book", "in the PDF", and "in my
  library".
- `web_only`: latest/current/news/API/version/external factual
  questions.
- `both`: general learning explanations where local material may help
  and external context may also help, including "use my book if
  relevant".

## Data Flow

```text
Add PDF
  -> managed backend storage
  -> PDF extraction
  -> optimized chunking
  -> API embedding
  -> PostgreSQL/pgvector
  -> retrieval
  -> LangGraph agent graph
  -> synthesized answer with [S#] and [W#] sources
```

## Key Files

- `frontend/src/pages/WorkspacePage.tsx`: Repository + Chat page.
- `frontend/src/components/RagQueryPanel.tsx`: Agent Chat UI.
- `frontend/src/tauri/filePicker.ts`: PDF-only desktop file picker.
- `backend/app/api/agent_routes.py`: `/api/agent/chat` endpoint.
- `backend/app/graphs/chat_rag_graph.py`: LangGraph state and nodes.
- `backend/app/agents/router.py`: deterministic route heuristics.
- `backend/app/agents/local_library.py`: local retrieval agent.
- `backend/app/agents/web_research.py`: web provider boundary.
- `backend/app/agents/synthesis.py`: final answer synthesis.
- `backend/app/library/importing.py`: managed PDF import flow.
- `backend/app/library/indexing.py`: PDF indexing flow.
- `backend/app/rag/retrieval.py`: pgvector retrieval.
- `backend/app/rag/citations.py`: normalized local citation IDs.
- `backend/scripts/index_pdf.py`: developer PDF indexing script.
- `backend/scripts/search_book.py`: retrieval inspection script.
- `backend/scripts/eval_retrieval.py`: retrieval eval script.
- `backend/scripts/ask_book.py`: single-book ask script.

## Commands

Backend:

```bash
conda activate pla
cd backend
pytest
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8081
```

Frontend:

```bash
cd frontend
bun install
bun run build
bun run dev
bun run tauri dev
```

## Environment

- Local backend configuration lives in `backend/.env`.
- Do not read, print, modify, or commit real `.env` files unless the
  user explicitly asks.
- Use `backend/.env.example` for placeholders only.
- PostgreSQL must be running and the `pgvector` extension must be
  available.
- Real provider keys stay backend-only:
  - `DEEPSEEK_API_KEY`
  - `ZHIPU_API_KEY`
  - `TAVILY_API_KEY`

Tests should use deterministic/mock providers and must not require real
Zhipu, DeepSeek, Tavily, Brave, Serper, or other network API access.

## Repository Hygiene

Do not commit:

- real API keys
- `.env` files
- real PDFs
- `backend/storage/` managed copies
- generated retrieval baseline output files
- frontend/backend build artifacts

The root `.gitignore` covers local secrets, managed storage, PDFs, and
baseline text outputs. Existing tracked historical PDFs/baselines should
not be deleted or untracked without an explicit cleanup request.

## Future Codex Guidance

- Keep changes scoped to the requested stage.
- Preserve existing tests and add deterministic tests for behavior
  changes.
- Do not reintroduce PDF preview or debug UI unless explicitly
  requested.
- Do not change embedding providers, chunking, retrieval ranking, graph
  topology, or storage behavior as incidental cleanup.
- Prefer existing services and schemas over new abstractions.
- Update `README.md` and this file when the MVP shape or operational
  commands change.
