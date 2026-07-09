# Personal Learning Agent

Experimental MVP for a LangGraph-based Personal Learning Agent. The app
helps you import born-digital PDFs into a local Repository, select PDFs
as knowledge context, and ask questions through Agent Chat.

The product is a learning agent, not a PDF reader. The MVP UI is:

```text
PDF Repository | Agent Chat
```

Current stage: Stage 50, Code Cleanup and Documentation Consolidation.

## What It Does

- Adds PDFs from the desktop file picker.
- Copies imported PDFs into backend-managed storage.
- Extracts text from born-digital PDFs.
- Chunks PDF text for mathematical/learning material.
- Embeds chunks through an API-based embedding provider.
- Stores and searches vectors with PostgreSQL + pgvector.
- Answers through a LangGraph dual-agent backend.
- Shows local Library citations as `[S1]`, `[S2]`, etc.
- Shows web research sources as `[W1]`, `[W2]`, etc. when configured.

## MVP Features

- PDF Repository for adding and selecting PDFs.
- Agent Chat as the main interaction surface.
- Managed PDF import/storage.
- PDF extraction and optimized chunking.
- PostgreSQL/pgvector retrieval.
- Deterministic LangGraph router with `local_only`, `web_only`, and
  `both` routes.
- Local Library Agent for selected PDF/book evidence.
- Web Research Agent provider boundary with unavailable, mock, and
  optional Tavily modes.
- Synthesis that separates local evidence from external context.

## Tech Stack

- Frontend: Tauri, React, Bun, Vite, TypeScript.
- Backend: FastAPI, LangGraph, SQLAlchemy, Alembic.
- Database: PostgreSQL with pgvector.
- PDF extraction: `pypdf`.
- Embeddings: API-based provider, with mock provider for tests.
- LLM: API-based provider, with deterministic provider for tests.
- Web research: provider boundary, optional Tavily provider.

## Architecture

PDF import and chat follow this path:

```text
Add PDF
  -> backend-managed storage
  -> PDF text extraction
  -> chunking
  -> API embeddings
  -> pgvector retrieval
  -> LangGraph agent graph
  -> answer with local citations and web sources
```

`POST /api/agent/chat` runs:

```text
Router Node
  -> Local Library Agent Node
  -> Web Research Agent Node
  -> Synthesis Node
```

Routes:

- `local_only`: selected books/PDFs/local Library questions.
- `web_only`: latest/current/news/API/version/external questions.
- `both`: learning explanations where local and web context may both
  help.

Local citations and web sources are separate in the response:

- local citations: `[S#]`, title/document/library item, page range,
  chunk metadata, chapter/section metadata when available.
- web sources: `[W#]`, title, URL, snippet, provider, optional
  published date.

## Setup

Create and activate the backend environment:

```bash
conda create -n pla python=3.12
conda activate pla
cd backend
pip install -r requirements.txt
```

Create a PostgreSQL database, for example
`personal_learning_agent`, and ensure pgvector is installed. Migrations
enable the `vector` extension for the project schema.

Create local backend configuration:

```bash
cp backend/.env.example backend/.env
```

`backend/.env` is local-only. Do not commit real API keys. Typical
placeholder configuration:

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/personal_learning_agent
LLM_PROVIDER=deterministic
DEEPSEEK_API_KEY=your_deepseek_api_key_here
EMBEDDING_PROVIDER=mock
ZHIPU_API_KEY=your_zhipu_api_key_here
WEB_RESEARCH_PROVIDER=none
TAVILY_API_KEY=your_tavily_api_key_here
LIBRARY_STORAGE_DIR=storage/library
```

Use deterministic/mock providers for tests. Real Zhipu, DeepSeek, and
Tavily use local backend `.env` values only.

Run migrations:

```bash
conda activate pla
cd backend
alembic upgrade head
```

Install frontend dependencies:

```bash
cd frontend
bun install
```

## How To Run

Start the backend:

```bash
conda activate pla
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8081
```

Start the desktop frontend:

```bash
cd frontend
bun run tauri dev
```

Build the frontend:

```bash
cd frontend
bun run build
```

Run backend tests:

```bash
conda activate pla
cd backend
pytest
```

## Demo Workflow

1. Start PostgreSQL.
2. Start the backend.
3. Start the frontend.
4. Add a born-digital PDF in the Repository.
5. Select the indexed Repository item.
6. Ask questions in Agent Chat.

Local-only example:

```bash
curl -X POST http://127.0.0.1:8081/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What does this book say about complete metric spaces?",
    "selected_library_item_id": "<library_item_id>"
  }'
```

Expected: route `local_only`, local citations as `[S#]`, and no web
sources.

Web-only example:

```bash
curl -X POST http://127.0.0.1:8081/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are the latest updates about DeepSeek API?"
  }'
```

Expected: route `web_only`. With `WEB_RESEARCH_PROVIDER=mock` or a real
provider, the response includes `[W#]` web sources. With
`WEB_RESEARCH_PROVIDER=none`, it returns a clear unavailable/skipped
message.

Both-mode example:

```bash
curl -X POST http://127.0.0.1:8081/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain the mean value theorem using my book if relevant.",
    "selected_library_item_id": "<library_item_id>"
  }'
```

Expected: route `both`, local evidence with `[S#]`, web context with
`[W#]` when available, and a final answer that distinguishes library
evidence from external context.

## Developer Scripts

These are developer/debug tools, not the main product UI:

- `backend/scripts/index_pdf.py`
- `backend/scripts/search_book.py`
- `backend/scripts/eval_retrieval.py`
- `backend/scripts/ask_book.py`

Do not commit generated baseline outputs or real PDFs used with these
scripts.

## Current Limitations

- Born-digital PDFs with a text layer are the primary supported input.
- Scanned PDFs and OCR are not part of the MVP.
- Local embedding model deployment is postponed.
- The MVP UI has no embedded PDF preview/reader.
- Citation click-to-page behavior is not included.
- Rerankers, hybrid search, BM25, and query expansion are not included.
- Settings UI is not included.
- Calendar and Notes UI are not part of the MVP.
- Web research depends on provider configuration.
- The Web Research Agent is not a crawler or deep-research system.

## Development Status

MVP / experimental personal learning agent. The codebase is intentionally
scoped around Repository + Agent Chat so future work can build on a
stable LangGraph dual-agent core.

For contributor and future-agent guidance, see `AGENT.md`.
