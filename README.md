# Personal Learning Agent

Experimental MVP for a LangGraph-based Personal Learning Agent. The app
helps you import born-digital PDFs into a local Repository, select PDFs
as knowledge context, and ask questions through Agent Chat.

The product is a learning agent, not a PDF reader. The MVP UI is:

```text
PDF Repository | Agent Chat
```

Current stage: real-Provider SSE reliability and deployment validation.

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
- POST-based SSE streaming with real Agent activity, final-answer token deltas,
  cancellation, and atomic Assistant-turn persistence.
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

`POST /api/agent/chat/stream` runs this bounded memory and evidence flow.
`POST /api/agent/chat` remains as the compatible complete-JSON endpoint:

```mermaid
flowchart TD
    A[Frontend Request] --> B[Conversation and Memory Load]
    B --> C[Router]
    C --> D[Query Embedding]
    D --> E[Local Retrieval]
    C --> F[Web Research]
    E --> G[Synthesis LLM]
    F --> G
    G --> H[Stream Final Answer Tokens]
    H --> I[Persist Complete Turn and Citations]
    I --> J[Final and Done Events]
    J --> K[Background Memory Processing]
```

For `both`, Local Retrieval and Web Research are LangGraph parallel branches.
The answer turn is persisted before the response is returned. Rolling summary,
memory extraction, and consolidation run afterward as managed FastAPI
background work with a separate database session.

### SSE streaming

The frontend sends the normal `AgentChatRequest` JSON with `fetch`, then reads
`text/event-stream` from `Response.body`. SSE is the only stream protocol; the
app does not also maintain NDJSON, WebSocket, or `EventSource` paths. Public
events are `run_started`, `status`, `route_selected`, `retrieval_completed`,
`token`, `citations`, `warning`, `final`, `done`, `cancelled`, and `error`.
Every event has a request/conversation/run ID, UTC timestamp, and monotonically
increasing sequence. Heartbeats are SSE comments and are not Activity steps.

Public Activity stages are `loading_context`, `retrieving_memory`, `routing`,
`retrieving_local`, `searching_web`, `processing_sources`, `synthesizing`,
`streaming`, and `persisting`. They are emitted by the backend at the real
execution boundary. Skipped route branches emit no fake status. Only the
Synthesis node can publish `synthesis_token`; the SSE mapper ignores every
other custom payload, so Router, Memory, tool payloads, prompts, and private
reasoning cannot become public token events.

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant A as FastAPI
    participant G as LangGraph
    participant D as DeepSeek
    participant P as PostgreSQL

    U->>F: Submit question
    F->>A: POST /api/agent/chat/stream
    A-->>F: run_started + real status events
    A->>G: astream(custom + values)
    G-->>A: routing and retrieval status
    A-->>F: Activity events
    G->>D: Stream final Synthesis
    D-->>G: Normalized token deltas
    G-->>A: synthesis_token only
    A-->>F: token events
    F-->>U: Incremental plain-text preview
    G->>P: Short transaction: complete turn + citation payload
    P-->>G: Commit
    G-->>A: Final state after checkpoint
    A-->>F: citations + final + done
```

Tokens are accumulated in memory and are never written one by one. The final
answer, full local citations, web sources, and learning event are committed in
one short SQL transaction. The production LangGraph checkpoint is written with
`durability="exit"`; `done` is emitted only after graph completion. If that
separate checkpoint step fails after the SQL commit, the service attempts a
targeted compensation delete and emits `error`, never successful `done`.
Post-response extraction, consolidation, and rolling-summary work starts only
after success and uses independent database sessions.

The frontend creates one stable Assistant placeholder, batches token rendering
at the server-advertised 30–80 ms interval, and updates only that turn.
Incomplete Markdown/LaTeX is shown as safe plain text. After `done`, the full
answer is rendered once with GFM, remark-math, and KaTeX; no raw HTML is used.
An `AbortController` powers Stop Generation. Cancellation or disconnect closes
the upstream async Provider iterator where possible, retains visible partial
text as cancelled/failed, skips completed persistence and Memory post-work,
and leaves the conversation and selected books usable for the next request.
The frontend submission lock and a per-process backend conversation registry
allow one active run per conversation while leaving other conversations free.

Streaming controls are backend-only:

```env
AGENT_STREAMING_ENABLED=true
AGENT_ACTIVITY_EVENTS_ENABLED=true
AGENT_STREAM_UI_FLUSH_INTERVAL_MS=50
AGENT_STREAM_HEARTBEAT_SECONDS=15
```

Set `AGENT_STREAMING_ENABLED=false` to make the frontend receive `409` and use
the compatible JSON endpoint. The flush interval is validated to 30–80 ms and
the heartbeat interval to 10–20 seconds.

### Stage 54 reliability validation

Real network tests are excluded from ordinary `pytest` through registered
`real_provider`, `network`, `soak`, and `manual_tauri` markers. They additionally
require `PLA_REAL_PROVIDER_TESTS=true`; missing Provider keys produce a clear
skip rather than a mock result. Run them explicitly only when quota use is
approved:

```bash
cd backend
PLA_REAL_PROVIDER_TESTS=true pytest -m real_provider
```

The dedicated Provider benchmark also requires an explicit cost confirmation:

```bash
PLA_REAL_PROVIDER_TESTS=true python scripts/benchmark_real_providers.py \
  --confirm-costs --runs 10 --warmups 1
```

With all Providers selected, this performs three DeepSeek scenarios, Zhipu
embedding requests, Tavily searches, and one DeepSeek cancellation probe. For
`runs=10` and `warmups=1`, that is 33 completed DeepSeek requests plus the
cancellation request, 11 Zhipu calls, and 11 Tavily calls. Use repeated results,
not one request, to interpret p50/p95. Provider latency depends on test time,
network/VPN route, geography, and current DeepSeek/Zhipu/Tavily load.

Provider-only measurements are separate from application orchestration. The
former report DeepSeek TTFT/generation/tokens-per-second, Zhipu request latency
and actual vector length, and Tavily search latency/result counts. The Stage 53
route benchmark reports Router, retrieval, Provider, persistence, citation-ready,
event/count, and total application measurements:

```bash
PLA_REAL_PROVIDER_TESTS=true python scripts/benchmark_agent_streaming.py \
  --real-providers --runs 10 --warmups 1
```

The real embedding benchmark compares actual response length, configured
dimension, and schema dimension before any write. A mismatch aborts the
validation and requires a separate schema decision; Stage 54 never migrates or
truncates vectors automatically.

Verify HTTP delivery against the backend or any proxy target:

```bash
python scripts/verify_sse_delivery.py \
  --base-url http://127.0.0.1:8081 --route local_only --runs 3

python scripts/verify_sse_delivery.py \
  --base-url http://127.0.0.1:9000 --route both --runs 3 --json

python scripts/verify_sse_delivery.py \
  --base-url http://127.0.0.1:8081 --route web_only \
  --cancel-after-first-token
```

The verifier records network chunk boundaries and event arrival times without
recording token text, questions, prompts, citations, or keys. It checks sequence
monotonicity, first status/token before `done`, and the final
`citations -> final -> done` order. If first token and `done` arrive in the same
network chunk it flags probable buffering. The repository has no deployed
reverse proxy; [the optional Nginx location](backend/deployment/nginx-sse.example.conf)
disables proxy/compression buffering and raises the read timeout for manual
deployment validation. It is an example, not a claim that Nginx was tested.

Run a controlled live-backend soak explicitly:

```bash
python scripts/soak_agent_sse.py --confirm --runs 20 --route both \
  --library-item-id <uuid>
python scripts/soak_agent_sse.py --confirm --runs 20 --cancel-every 3
pytest -m soak
```

The HTTP soak reuses one client, reports failures separately from percentiles,
and verifies that a normal request can follow cancellation. The in-process soak
checks pending asyncio tasks, completed turns, and active-run registry cleanup.
These commands may consume real quota if the target backend uses real Providers.

Fault injection remains test-only and deterministic. Provider timeout and
interruption use mock transports/providers; SSE, citation persistence, SQL
persistence, checkpoint, disconnect, and compensation failures use dependency
injection. `PLA_FAULT_INJECTION_ENABLED` defaults to false and Settings rejects
it in production. There is no public fault-injection endpoint and no random
failure branch in application code.

The Tavily boundary now reuses the shared synchronous `httpx.Client`, applies
configured connect/read timeouts, normalizes HTTP/429/network failures, and
deduplicates normalized URLs. Because the current Web node is intentionally a
synchronous executor task, cancellation cannot interrupt an already-running
Tavily socket read; its timeout bounds that work. Converting the Web Agent to an
async transport is intentionally deferred rather than hidden inside Stage 54.

#### Tauri WebView manual checklist

Browser tests do not prove desktop WebView behavior. Run both `bun run tauri dev`
and a production Tauri build against a reachable backend, then record date, OS,
WebView version, backend target, Provider modes, and whether each item passed:

1. Submit creates Activity before the first answer token.
2. Activity changes while the request is still pending.
3. First visible token appears before `done`/final citations.
4. A long answer updates continuously without freezing input or scrolling.
5. Completed Markdown, inline LaTeX, display LaTeX, and code blocks render.
6. Local `[S]` and Web `[W]` citations match the completed answer.
7. Stop Generation preserves partial text and marks the turn cancelled.
8. A new request succeeds immediately after cancellation.
9. Selected Library items and conversation ID remain unchanged.
10. The composer stays fixed; manual upward scrolling is not overridden.
11. DevTools Network shows multiple response chunks before completion.
12. Development console records first chunk, Activity, token render, `done`, and
    final render milestones without exposing them in production UI.
13. Repeat the same checks in the production WebView build.
14. If `VITE_BACKEND_URL` changes, update the Tauri `connect-src` allowlist; the
    repository currently permits local ports 8081 and optional proxy port 9000.
15. Capture cancellation and long-answer UI responsiveness with the same test
    prompt so later runs are comparable.

The active-run registry remains process-local. It protects one Conversation
inside the current single-process desktop backend, releases on success/error/
cancellation, and does not block other Conversations. It is not multi-worker
safe and Stage 54 does not add Redis or database locks. SQL answer/citation/
learning-event persistence is one short transaction; LangGraph checkpointing
is outside that transaction. Checkpoint failure triggers best-effort
compensation and a critical structured log if compensation itself fails.

Exact token resume is unsupported because SSE runs are not stored as replayable
token logs. The UI retains partial text and permits a fresh request instead.
No ANN index was added: current data still does not demonstrate that HNSW or
IVFFlat improves the existing L2 query plan.

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

Streaming summaries add `stream_open`, `first_event`, `first_status`,
`first_token`, `stream_generation`, `final_persist`, and `done_event`, plus
event/token/character counts and completion/cancellation flags. This separates
total runtime from perceived waiting: first status measures when useful UI
feedback appears, while first token measures when answer text begins. The
frontend likewise distinguishes first visible status, first answer token,
stream duration, and final Markdown/KaTeX render.

Run the mock streaming benchmark:

```bash
python scripts/benchmark_agent_streaming.py --runs 10
```

It reports route-specific first-status, first-token, generation, final-persist,
total, event counts, token counts, failures, and synthetic cancellation p50/p95.
Add `--real-providers` only when API quota use is intentional. Mock results do
not represent DeepSeek, Zhipu, or Tavily public-network p50/p95, and one real
run is not a stable performance conclusion.

Run streaming-focused tests with:

```bash
pytest -q tests/test_agent_streaming.py tests/test_llm_providers.py
cd ../frontend && bun run test
```

Malformed 422 requests now receive an `X-Request-ID` and safe `request_id` JSON
field. The correlated log includes method/path/error type but never the request
body. No ANN index was added: current data still does not demonstrate that an
L2-matched ANN plan beats the existing plan, and streaming does not change that
Stage 52 database finding.

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
