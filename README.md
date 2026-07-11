# Personal Learning Agent

Experimental MVP for a LangGraph-based Personal Learning Agent. The app
helps you import born-digital PDFs into a local Repository, select PDFs
as knowledge context, and ask questions through Agent Chat.

The product is a learning agent, not a PDF reader. The MVP UI is:

```text
PDF Repository | Agent Chat
```

Current stage: Agent latency observability and measured low-risk optimization.

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
- Renders Assistant Markdown, including GFM tables and locally bundled KaTeX
  for inline and display mathematics.

## MVP Features

- PDF Repository for adding and selecting PDFs.
- Agent Chat as the main interaction surface.
- Safe Markdown and LaTeX rendering for Assistant messages without raw HTML.
- Conversation-scoped multi-book selection: Repository clicks toggle context
  without replacing the active conversation or clearing messages.
- Double-click a Repository PDF to open its managed copy in the system PDF
  reader through the Tauri opener plugin.
- Managed PDF import/storage.
- PDF extraction and optimized chunking.
- PostgreSQL/pgvector retrieval.
- Deterministic LangGraph router with `local_only`, `web_only`, and
  `both` routes.
- Local Library Agent for selected PDF/book evidence.
- Web Research Agent provider boundary with unavailable, mock, and
  optional Tavily modes.
- Synthesis that separates local evidence from external context.
- Conversation-scoped recent turns and rolling summaries.
- PostgreSQL LangGraph checkpoints with an in-memory test backend.
- Auditable semantic, episodic, and procedural long-term memory.

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

`POST /api/agent/chat` runs this bounded memory and evidence flow:

```mermaid
flowchart TD
    A[Frontend Request] --> B[Conversation and Memory Load]
    B --> C[Router]
    C --> D[Query Embedding]
    D --> E[Local Retrieval]
    C --> F[Web Research]
    E --> G[Synthesis LLM]
    F --> G
    G --> H[Persist Conversation]
    H --> I[Complete JSON Response]
    I --> J[Background Memory Processing]
```

For `both`, Local Retrieval and Web Research are LangGraph parallel branches.
The answer turn is persisted before the response is returned. Rolling summary,
memory extraction, and consolidation run afterward as managed FastAPI
background work with a separate database session.

## Agent latency diagnostics

Set these backend options in local development:

```env
AGENT_LATENCY_LOGGING_ENABLED=true
AGENT_DEBUG_TIMINGS_IN_RESPONSE=false
LLM_CONNECT_TIMEOUT_SECONDS=10
LLM_READ_TIMEOUT_SECONDS=60
EMBEDDING_CONNECT_TIMEOUT_SECONDS=10
EMBEDDING_READ_TIMEOUT_SECONDS=60
```

Every completed or failed Agent request emits one JSON summary with a random
`request_id`, route, safe counters, and `timings_ms`. It never includes the
full question, prompt, answer, chunk text, API key, or embedding vector.
Post-response Memory work emits a second JSON event with the same `request_id`.

`synthesis_ttft` is the time from sending the DeepSeek request until its first
content token. `synthesis_generation` is first token to last token, while
`synthesis_total` includes the complete streamed provider exchange. Embedding
API latency is `query_embedding`; pgvector/database distance search is
`document_vector_search`. Route-specific `local_agent_total` and
`web_agent_total` show branch cost, and `both` should be close to the slower
branch rather than their sum.

Development-only response diagnostics can be enabled with
`AGENT_DEBUG_TIMINGS_IN_RESPONSE=true`. They are included only when `APP_ENV`
is not `production`; production never exposes internal timing data.

Run the deterministic benchmark without network calls:

```bash
conda activate pla
cd backend
python scripts/benchmark_agent_latency.py --runs 10
```

It reports count, min, max, mean, p50, p90, p95, and failures separately. One
warm-up is used by default. A real benchmark is opt-in and consumes API quota:

```bash
python scripts/benchmark_agent_latency.py \
  --runs 3 \
  --real-providers \
  --scenario local_only \
  --scenario web_only \
  --scenario both
```

Use `backend/scripts/explain_vector_search.sql` with `psql` to inspect the
actual L2 (`<->`) retrieval plan. An eventual ANN index must use an L2-matched
operator class such as `vector_l2_ops`; do not add one solely because a small
table uses a faster sequential scan.

The current HTTP API still returns one complete JSON response. DeepSeek is
consumed as a stream inside the provider so TTFT and generation can be measured,
but partial tokens are not sent to the frontend yet. The frontend records
request-to-response and final Markdown/KaTeX render time; for the current
non-streaming protocol, first and last response chunk are the same event.

### Memory boundaries

- Short-term conversation memory is isolated by `conversation_id`. The
  backend maps it to an internal LangGraph `thread_id`; the frontend never
  sends or receives that internal identifier.
- Only the configured recent-turn window is injected verbatim. When a
  conversation exceeds the summary threshold, older uncovered turns are
  incrementally compressed into one rolling summary.
- Long-term memory is namespace-isolated and typed as `semantic`, `episodic`,
  or `procedural`, with controlled subtypes. It supports active, superseded,
  deleted, and expired lifecycle states.
- Learning events remain an append-only progress/audit stream. They are not
  conversation messages or user preferences.
- Document chunks remain the authoritative local knowledge store. Book facts
  and mathematical source evidence are retrieved through document RAG and
  cited as `[S#]`; they are never promoted into user memory.

Long-term writes are explicit or conservatively extracted from stable,
high-confidence user instructions. Temporary state, sensitive information,
ordinary chat, web results, and retrievable PDF content are rejected by
default. Consolidation combines namespace/type metadata, structured
predicate and scope matching, and semantic similarity to choose CREATE,
UPDATE, SUPERSEDE, or IGNORE. Retrieval combines metadata filters, pgvector
similarity, bounded keyword matching, importance, and recency, returning only
a few active records. Memory is injected as untrusted personalization context,
never as a citation or factual authority.

The production checkpointer uses the official
`langgraph-checkpoint-postgres` saver. Its pool is created once in the FastAPI
lifespan, and official checkpoint schema setup is idempotently applied at
startup. Tests use `MEMORY_CHECKPOINTER_BACKEND=memory`.

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
MEMORY_CHECKPOINTER_BACKEND=postgres
MEMORY_RECENT_TURN_LIMIT=16
MEMORY_SUMMARY_TRIGGER_TURNS=24
MEMORY_RETRIEVAL_LIMIT=5
MEMORY_AUTO_WRITE_ENABLED=true
MEMORY_AUTO_WRITE_MIN_IMPORTANCE=0.75
MEMORY_AUTO_WRITE_MIN_CONFIDENCE=0.80
MEMORY_AUTO_WRITE_MIN_DURABILITY=0.75
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

The backend suite includes deterministic unit and SQLite integration tests.
With the configured local PostgreSQL database, validate migrations with:

```bash
alembic upgrade head
alembic downgrade e8b7c6d5a4f3
alembic upgrade head
```

`GET/POST/PATCH/DELETE /api/memory/long-term` provide the minimal auditable
management API. DELETE is a soft delete. The chat request accepts an optional
product-level `conversation_id`; a new conversation is created when omitted,
and the response returns the identifier for the next turn.

The current conversation state (`conversation_id`, visible messages, and
selected Repository item IDs) is stored locally for refresh recovery. Book
selection is cumulative and deduplicated; selecting or deselecting books never
changes the conversation. Only **New Chat** clears current messages and the
selected-book working context. The Chat composer stays at the bottom while
messages and source details scroll independently.

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
- `backend/scripts/benchmark_agent_latency.py`
- `backend/scripts/explain_vector_search.sql`

Do not commit generated baseline outputs or real PDFs used with these
scripts.

## Current Limitations

- Born-digital PDFs with a text layer are the primary supported input.
- Scanned PDFs and OCR are not part of the MVP.
- Local embedding model deployment is postponed.
- The MVP UI has no embedded PDF preview/reader.
- Citation click-to-page behavior is not included.
- Document-RAG rerankers, hybrid/BM25 search, and query expansion are not included.
- Settings UI is not included.
- Calendar and Notes UI are not part of the MVP.
- Web research depends on provider configuration.
- The Web Research Agent is not a crawler or deep-research system.
- Agent Chat does not yet expose partial tokens over SSE; the current JSON
  response preserves atomic persistence, citations, and final Markdown/KaTeX.

## Development Status

MVP / experimental personal learning agent. The codebase is intentionally
scoped around Repository + Agent Chat so future work can build on a
stable LangGraph dual-agent core.

For contributor and future-agent guidance, see `AGENT.md`.
