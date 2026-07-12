# Personal Learning Agent

Experimental MVP for a LangGraph-based Personal Learning Agent. The app
helps you import born-digital PDFs into a local Repository, select PDFs
as knowledge context, and ask questions through Agent Chat.

The product is a learning agent, not a PDF reader. The MVP UI is:

```text
PDF Repository | Agent Chat
```

Current stage: unified Local/Web/Academic source and citation UX over the
existing adaptive research paths.

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
- Makes `[S#]` and `[W#]` markers keyboard-operable and maps them to grouped,
  expandable source cards under the completed Assistant answer.
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
- Opens local citation cards through the same managed-PDF boundary and opens
  validated HTTP(S), DOI, and arXiv sources in the system browser.
- Managed PDF import/storage.
- PDF extraction and optimized chunking.
- PostgreSQL/pgvector retrieval.
- Deterministic LangGraph router with `local_only`, `web_only`, and
  `both` routes.
- Local Library Agent for selected PDF/book evidence.
- Controlled Web Research Agent with Tavily/Brave search, Secure Fetch, and
  arXiv/OpenAlex/Crossref academic metadata through audited MCP tools.
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
- Web research: reusable MCP clients for Tavily, Brave, Secure Fetch, and the
  local PLA Academic server; legacy Tavily HTTP remains compatible.

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

The legacy Tavily HTTP boundary remains available for compatibility. Stage 55
adds a separate controlled async MCP research path described below.

### Stage 55 controlled MCP research

Set `MCP_ENABLED=true` to route Web Research through the MCP gateway. The
frontend streaming endpoint and compatible JSON endpoint share the same
research service; the sync JSON graph submits MCP work to the FastAPI lifespan
event loop instead of starting per-request subprocesses.

```mermaid
flowchart LR
    Q[Web Research question] --> P[Rule-based Research Planner]
    P --> G[Bounded MCP Tool Gateway]
    G --> T[Tavily MCP]
    G --> B[Brave Search MCP]
    G --> F[PLA Secure Fetch MCP]
    G --> A[PLA Academic MCP]
    T --> N[WebEvidence normalization]
    B --> N
    F --> N
    A --> N
    N --> D[URL and content deduplication]
    D --> W[Ranked W citations]
    W --> S[Synthesis]
```

The planner is deterministic and bounded; it does not expose every discovered
tool to the LLM:

- ordinary web research uses `tavily-search`, with `brave_web_search` only as a
  fallback;
- latest/news/cross-check questions call Tavily and `brave_news_search` in
  parallel;
- paper, arXiv, journal, theorem, or DOI questions use the Academic MCP;
- explicit public URLs and the top one to three ranked search results use the
  Secure Fetch MCP;
- at most `MCP_MAX_CALLS_PER_REQUEST` calls, `MCP_MAX_FETCH_URLS` page reads,
  and `MCP_MAX_EVIDENCE` final sources are accepted.

Static allowlists are intersected with MCP tool discovery. A new server tool is
therefore unavailable until PLA code explicitly approves it. Current approved
tools are:

| Server | Transport | Approved tools |
|---|---|---|
| Tavily | STDIO or Streamable HTTP | `tavily-search`, `tavily-extract` |
| Brave | STDIO or Streamable HTTP | `brave_web_search`, `brave_news_search` |
| PLA Secure Fetch | STDIO or Streamable HTTP | `fetch` |
| PLA Academic | STDIO or Streamable HTTP | `search_arxiv`, `search_openalex`, `lookup_doi`, `get_paper_metadata` |

External server packages are never installed automatically. The default
Tavily/Brave commands use `npx --no-install`; install audited versions yourself
or override the command/arguments. For Tavily Streamable HTTP, set
`MCP_TAVILY_TRANSPORT=streamable_http`; the API key is sent in an Authorization
header rather than placed in the URL. Local PLA Fetch and Academic servers run
from the backend Python environment.

Every server session is owned by one long-lived worker task. Calls are
serialized per session, time-bounded, cancellable, health-checkable, and closed
during FastAPI shutdown. Cancellation destroys the affected runtime so an
STDIO child or remote stream cannot continue unnoticed; the next request may
connect a fresh session.

#### Stage 56 MCP reliability and security

FastAPI lifespan owns the process-wide `MCPClientManager`. An enabled server is
started lazily on its first discovery or tool call, then its STDIO child or
Streamable HTTP connection is reused across Agent requests. Each server has a
bounded queue and one serialized session worker; this avoids concurrent use of
an MCP session and limits local subprocess and Provider pressure. Shutdown
cancels the worker, fails its current and queued callers, closes transport
resources, and waits for the child/session cleanup. `local_only` never starts
an MCP runtime.

Internal health snapshots report `disabled`, `starting`, `healthy`, `degraded`,
or `unavailable`, plus discovered/missing allowlisted tools, the latest success
and failure times, consecutive failures, safe error category, and restart
count. A health probe performs tool discovery only—it never consumes search
quota. This state is currently for logs/tests and future Settings work; no
public health or debug endpoint is exposed.

MCP reliability limits are configured in `backend/.env.example`:

- `MCP_CONNECT_TIMEOUT_SECONDS` bounds connection and initial discovery;
- `MCP_TOOL_TIMEOUT_SECONDS` bounds one tool attempt;
- `MCP_TOTAL_TIMEOUT_SECONDS` includes queueing, retries, and backoff;
- `MCP_MAX_RETRIES` is limited to 0–2 and applies only to the current bounded,
  idempotent research reads;
- `MCP_MAX_PENDING_CALLS_PER_SERVER` bounds each server queue;
- `MCP_MAX_CALLS_PER_REQUEST`, `MCP_MAX_FETCH_URLS`, and `MCP_MAX_EVIDENCE`
  prevent unbounded tool loops and evidence growth.

PLA validates every tool argument against an internal Pydantic schema before
transport dispatch. Discovery is still intersected with the static allowlist,
so newly advertised tools and unknown fields remain unavailable. Retry never
recurses: Tavily may fall back once to Brave; failed Fetch retains the snippet;
partial Academic results survive another academic source failure. Cancellation
or client disconnect cancels the research coroutine, destroys the affected MCP
runtime, skips later Fetch/fallback work, and leaves Stage 53 persistence and
Memory cancellation rules unchanged.

Secure Fetch checks every resolved address and requires all answers to be
public, treats IPv4-mapped IPv6 as IPv4, validates each redirect, and checks the
connected peer when the transport exposes it. This reduces DNS rebinding and
IPv6 bypass risk in addition to the scheme, credentials, redirect, content
type, body size, read timeout, and total-time limits. Deployment must preserve
peer-address metadata for the post-connect check; pre-connect DNS policy remains
mandatory either way.

Stage 52 summaries now include MCP retry, timeout, cancellation, restart, and
active STDIO-process counters in addition to MCP startup/connect/discovery/tool
latencies. Structured MCP logs contain only request ID, server, approved tool,
transport, outcome, and error category—never arguments, page bodies, stderr,
raw stack traces, or secrets.

### Stage 57 adaptive corrective research graph

Both JSON and SSE chat now use the same bounded orchestration:

```mermaid
flowchart TD
    C[Load conversation and memory context] --> Q[Structured query analysis]
    Q --> P[Deterministic execution plan]
    P --> L[Local evidence]
    P --> W[Web evidence]
    P --> A[Academic evidence]
    L --> M[Merge and deduplicate]
    W --> M
    A --> M
    M --> G[Deterministic evidence grade]
    G -->|empty or materially irrelevant, retry budget remains| R[One corrective retrieval]
    R --> M
    G --> B[Answer plan]
    B --> S[Only long-form synthesis]
    S --> V[Citation verification]
    V -->|at most once| X[Deterministic citation repair]
    X --> PERSIST[Atomic final persistence]
    V --> PERSIST
```

Query understanding is a strict Pydantic object containing intent,
complexity, required Local/Web/Academic sources, freshness, selected-book
relevance, clarification state, answer mode, bounded subqueries, and
confidence. Real LLM configurations may produce this semantic JSON; invalid
or unavailable analysis falls back to conservative deterministic rules. The
model never chooses node names. Rule code maps the analysis to exactly one of
`direct_answer`, `local_only`, `web_only`, `academic_only`, `local_web`,
`local_academic`, `web_academic`, or `all_sources`.

Local, Web, and Academic branches fan out independently and return evidence,
not complete answers. Web uses Tavily/Brave/Secure Fetch; Academic uses the
existing arXiv/OpenAlex/Crossref MCP boundary. They share one request-scoped
`MCPToolGateway`, so initial and corrective calls consume the same call budget.
Different MCP servers may progress in parallel, while the Stage 56 manager
continues serializing calls within one server session. The existing Local RAG
remains pgvector-based; Stage 57 supplies bounded query rewrite and expanded
`top_k` on correction but does not invent an unmeasured hybrid index, reranker,
or parent-document store.

The evidence grader records relevance, required-source coverage, source
quality, freshness, citation readiness, missing aspects, conflicts, and one of
`sufficient`, `insufficient`, `conflicting`, or `empty`. Correction is code
bounded to one attempt by default and two as a hard model limit. It cannot
reset the gateway budget, and successful evidence is retained when another
source fails. When correction is not useful or the cap is reached, Synthesis
answers with an explicit evidence limitation.

Synthesis remains the only long-form generation node. A deterministic verifier
then checks `[S#]`/`[W#]` existence and uniqueness, Local source metadata, Web
URLs, and Academic publication metadata. Unknown or missing markers may be
repaired once, followed by one final verification; the final SSE event replaces
the streamed draft with the verified text before the already-existing atomic
persistence and `done` boundary.

Public Activity now includes understanding the question, planning research,
evaluating sources, bounded correction, organizing the answer, and verifying
citations. It still never exposes node names, prompts, MCP arguments, raw
payloads, or chain-of-thought. Stage 52 traces add `query_analysis`, `planning`,
`local_subgraph`, `web_subgraph`, `academic_subgraph`, `evidence_merge`,
`evidence_grade`, `answer_plan`, and `citation_verify`, plus corrective-retry
and answer-repair counters.

Run focused adaptive tests with:

```bash
cd backend
pytest -q tests/test_adaptive_research_graph.py \
  tests/test_agent_chat_graph.py tests/test_agent_streaming.py
```

### Stage 58 adaptive graph evaluation

The versioned golden set at `backend/evals/adaptive_graph.jsonl` contains 55
human-labelled cases spanning Local, Web, Academic, multi-source, clarification,
empty/insufficient/conflicting evidence, partial Provider failure, corrective
recovery, and citation faults. Each record is schema-validated before a run.

Run the deterministic, network-free benchmark:

```bash
cd backend
python scripts/evaluate_adaptive_graph.py \
  --dataset evals/adaptive_graph.jsonl \
  --variant adaptive --runs 3 \
  --json-report evals/reports/adaptive.json \
  --markdown-report evals/reports/adaptive.md
```

The runner supports fixed direct/Local/Web/Academic baselines, single- and
multi-source adaptive paths, and correction disabled/retry-one/retry-two
comparisons. A failed case is retained in failure counts but excluded from
successful percentiles. Reports contain deterministic request IDs, case IDs,
routes, aggregate metrics, token usage when available, and no questions,
prompts, raw evidence, endpoints, credentials, or keys.

The 55-case deterministic run with three repeats measured 100% schema validity,
intent/source/route accuracy and repeated-run stability on this labelled set.
Evidence status, missing-aspect, and conflict fixtures were classified at 100%.
Five corrective scenarios per three repeats recovered 80%, with mean relevance
gain 0.8, coverage gain 0.4, and labelled extra latency of 163 ms; the no-gain
case remained visible instead of being counted as recovery. Structural citation
classification was 100%; repair succeeded for two of three triggered invalid
cases, while the unrepairable missing-URL object correctly remained invalid.
These are deterministic fixture results, not estimates of public-network answer
quality, and the dataset is not yet a held-out benchmark.

The first golden run exposed systematic summarize/follow-up/current-information
and mixed-source rule errors. Small deterministic rule changes raised intent
accuracy from 90.2% to 100%, source and route accuracy from 96.1% to 100%, and
clarification precision from 75% to 100% on the same set. No Graph topology,
grader threshold, MCP policy, or retry limit was changed.

Real DeepSeek evaluation is refused unless both
`PLA_REAL_PROVIDER_TESTS=true` and `--real-providers --confirm-costs` are used.
It requests JSON at temperature zero and records usage when available. Optional
`llm-experimental` grader and semantic-verifier adapters exist only in the
evaluation package and are never enabled in production. See
`backend/evals/README.md` for commands and interpretation.

### Stage 59 held-out research-quality evaluation

Stage 59 keeps model inputs, golden labels, and claim-to-source annotations in
three separate files under `backend/evals/heldout/`. The 50 input cases do not
contain expected intent, route, evidence status, or citation-support labels and
their IDs do not overlap the Stage 58 tuning fixtures. The companion claim set
contains 30 human annotations across supported, partially supported,
unsupported, contradicted, common-knowledge, and reasoning-only claims.

Run the reproducible network-free evaluation with:

```bash
cd backend
python scripts/evaluate_heldout_research.py --runs 3 \
  --json-report evals/reports/heldout.json \
  --markdown-report evals/reports/heldout.md
```

Real DeepSeek QueryAnalysis, semantic-verifier, and MCP collection remain
independent opt-in experiments. They are refused unless
`PLA_REAL_PROVIDER_TESTS=true` and `--confirm-costs` are both present:

```bash
PLA_REAL_PROVIDER_TESTS=true python scripts/evaluate_heldout_research.py \
  --real-query --semantic-verifier --confirm-costs --runs 3 \
  --real-query-max-cases 12 \
  --input-cost-per-million <current-price> \
  --output-cost-per-million <current-price>
```

Add `--real-mcp` only when `MCP_ENABLED=true` and `MCP_REAL_TESTS=true` are
also configured. Real MCP output stores bounded normalized evidence metadata
for later human annotation; it never stores keys or complete fetched pages.
Prices are deliberately supplied per run because Provider pricing changes.

The 2026-07-12 offline held-out run exposes generalization errors instead of
tuning them away: deterministic intent accuracy was 64%, source/route accuracy
56%, clarification recall 0%, and noisy evidence-grade accuracy 50%. The
structural citation verifier had 100% precision but only 13.3% recall for
partially supported, unsupported, or contradicted claims. No production Graph
rule, grader threshold, or verifier path was changed from these labels.

A controlled real DeepSeek run used the configured `deepseek-v4-pro` model on
12 category-balanced cases, twice at temperature zero and twice at the current
production temperature (also zero). Both groups had 100% schema validity but
only 66.7% repeated-run stability; route accuracy was 58.3% and 62.5%, with
p50 latency 9.02 s and 7.77 s respectively. A real evaluation-only semantic
run over all 30 annotated claims reached 83.3% precision and 100% recall, but
its 20% false-positive rate and 2.82 s p50 / 5.30 s p95 added latency do not
justify production enablement. Token usage was recorded; dollar cost remains
unset because no current per-million prices were supplied. The decision is
`keep deterministic only`. Real MCP collection was not run because the MCP and
MCP-real-test switches remained disabled.

### Stage 60 Settings and Provider profiles

The desktop sidebar now exposes Settings with independent Appearance, Agent
Model, and Embedding Model sections. Appearance defaults to the operating-system
theme, persists only the `system`/`light`/`dark` preference, and reacts to system
appearance changes without changing the Markdown or KaTeX renderer.

Provider metadata is stored in PostgreSQL `provider_profiles`; API keys are not.
In the Tauri build, keys live in an encrypted Stronghold vault and the user
unlocks that vault with a passphrase once per application session. The frontend
passes a selected key to the local backend only for connection testing,
activation, or re-indexing. The backend retains it in process memory inside the
active Provider client and returns only a mask plus `secret_ref`. Browser-only
development has an explicit session-memory fallback and never puts keys in
`localStorage`.

Provider clients are process-local because the Backend never reads Stronghold
secrets. After a Backend restart, a profile may remain the persisted selection
while `runtime_active=false`; unlock the vault and activate it again before the
next request. The Settings page exposes this state instead of silently showing
the disconnected profile as active. Until reconnection, the documented `.env`
Provider fallback remains in effect.

Available runtime adapters are:

- OpenAI-compatible: DeepSeek, OpenAI, Zhipu, Ollama, generic, and custom
  endpoints;
- native Anthropic Messages for chat and streaming;
- native Gemini `generateContent`, streaming, structured JSON, and embeddings.

Each catalog entry declares chat, streaming, tool-calling, structured-output,
embedding, and multimodal capabilities. A profile is rejected when it cannot
satisfy its requested role. Connection tests use bounded minimal requests and
do not create Conversations, Memory, citations, or learning events.

Chat profile activation affects only new Agent requests. A request captures an
immutable Chat/Embedding client snapshot before Graph execution, so switching a
profile cannot change an in-flight stream. Without an unlocked desktop profile,
the existing `.env` DeepSeek/Zhipu/deterministic configuration remains the
fallback.

Embedding changes are staged rather than immediately activated. Creating an
Embedding profile creates a `pending` `embedding_index_versions` row;
re-indexing writes new vectors to `chunk_embeddings` without overwriting the
legacy `document_chunks.embedding` column or another profile's vector space.
Only a fully `ready` version can become `active`, and retrieval filters by that
exact version. Existing Repository indexes therefore remain usable until the
new version is explicitly activated.

Apply or roll back the Stage 60 migration with:

```bash
cd backend
alembic upgrade head
alembic downgrade a1c4e7f9b2d6
alembic upgrade head
```

### Stage 61 legacy PDF ingestion and dual-index evaluation

PDF ingestion now persists a versioned classification before activating new
chunks. Per-page extractability, image coverage, font presence, and extraction
errors classify a document as `born_digital`, `scanned`, `mixed`, or failed.
The stored detection evidence contains counts and ratios, never page text.
Successful processing stores page number, extraction method, source type,
language, OCR confidence, bounded text boxes, page checksum, and dimensions.

The production layout path uses PyMuPDF text blocks plus deterministic
math-aware rules. This keeps the existing page-aware mathematical chunker and
adds theorem, lemma, definition, proof, formula, figure-caption, table,
footnote, heading, bibliography, contents, and index metadata without loading a
large parser model. Repeated first-line headers and last-line footers are
removed only when repeated across pages. Docling/MinerU/PP-Structure are not
simultaneously wired into production.

For scanned or mixed pages, PLA renders only the pages lacking usable text and
invokes Tesseract. OCRmyPDF is optional: when installed it produces a derived,
versioned searchable PDF with rotation correction, deskew, and cleanup; the
source PDF is never modified. A missing/failing OCR executable leaves a
retryable failed processing version and does not replace the currently active
index. Install the system tools separately when OCR is required:

```bash
# Distribution-specific examples; PLA does not auto-install system OCR tools.
tesseract --version
ocrmypdf --version
```

Local PDF retrieval now uses dense vectors plus PostgreSQL `simple` full-text
search, Reciprocal Rank Fusion, bounded deterministic reranking, metadata
filters, OCR-confidence weighting, and parent-section expansion. This improves
exact theorem/section numbers and named terminology while preserving the same
`LocalEvidence` and `[S#]` citation contract. Non-PDF and legacy documents keep
their prior dense behavior. A GIN expression index supports the matching
full-text expression; no speculative ANN vector index was added.

The visual page path is an isolated experiment. `PDF_VISUAL_RETRIEVAL_ENABLED`
defaults to false, no visual model is downloaded, and no GPU is assumed. An
explicitly registered ColPali/ColQwen-style adapter may render selected pages,
store late-interaction multi-vectors in `visual_page_embeddings`, and fuse page
ranks with text ranks. Its model, dimension, processing version, page checksum,
storage, and activation state are separate from text embeddings. The included
deterministic visual encoder is test-only.

Run the versioned offline retrieval evaluation:

```bash
cd backend
python scripts/evaluate_pdf_rag.py \
  --dataset evals/legacy_pdf_retrieval.jsonl \
  --json-report /tmp/pdf-rag.json \
  --markdown-report /tmp/pdf-rag.md
```

The checked-in cases cover born-digital, scanned, mixed, theorem/proof,
formula, figure, table, OCR-error, and exact-section scenarios. They are
fixture measurements, not real Tesseract or ColPali benchmarks. External OCR
and GPU tests use the opt-in `external_ocr` and `visual_gpu` markers. In the
current fixture run, Recall@5 was 0.400 for dense and 1.000 for hybrid, while
visual query p50 was 485 ms versus 64.5 ms for hybrid and used roughly 6.5x the
stored bytes. Because dual retrieval did not improve Recall@5 over hybrid and
no real visual model/GPU run was executed, production remains text-hybrid only.

Stage 61 processing/index activation is versioned: a new processing version,
OCR pages, text chunks, Stage 60 embedding-index reference, and optional visual
version are written separately; `documents.active_processing_version_id`
switches only after text extraction and embedding succeed. Old versions are
retained for rollback and different vector spaces are never queried together.

Apply or roll back the Stage 61 migration with:

```bash
cd backend
alembic upgrade head
alembic downgrade f3a9c1d7e5b2
alembic upgrade head
```

All raw server results become the internal `WebEvidence` shape before
Synthesis: evidence ID, source type, provider, title, canonical URL, excerpt,
optional bounded page content, authors, publication/retrieval time, DOI, and
arXiv ID. URL tracking parameters and fragments are removed, duplicate URLs
and highly similar text are collapsed, and final evidence is numbered `[W1]`,
`[W2]`, and so on. Academic evidence still uses `[W]`, with
`source_type=academic` in the structured citation.

The PLA Academic MCP calls arXiv, OpenAlex, and Crossref metadata APIs with a
shared async client, bounded result counts, rate spacing, timeout, and a
configured User-Agent. It never downloads PDFs, imports papers into Repository,
or traverses citation graphs.

The PLA Secure Fetch MCP permits only public HTTP(S) pages. It rejects URL
credentials, localhost, private/link-local/loopback/reserved addresses and cloud
metadata targets; validates every redirect and the connected peer; limits
redirects, decoded bytes, content types, total time, and returned characters;
and strips scripts/styles from HTML. A failed Fetch retains the original search
snippet instead of failing the answer.

Public SSE Activity is limited to product stages such as planning research,
searching pages/papers, reading pages, and filtering sources. Server names,
tool names, arguments, raw payloads, and chain-of-thought are not emitted.
Stage 52 traces add `mcp_connect`, `mcp_tool_discovery`, `mcp_tool_call`,
`mcp_normalize`, `mcp_fetch`, call/fallback/error counts, evidence count, and
deduplication count without logging page bodies or keys.

Default tests use mock sessions/transports and a local STDIO discovery test:

```bash
cd backend
pytest tests/test_mcp_foundation.py tests/test_mcp_research.py \
  tests/test_mcp_evidence.py tests/test_secure_fetch_mcp.py \
  tests/test_academic_mcp.py
```

Stage 56 reliability coverage can be run directly with:

```bash
pytest -q tests/test_mcp_foundation.py tests/test_mcp_hardening.py \
  tests/test_mcp_gateway_hardening.py tests/test_mcp_research.py \
  tests/test_secure_fetch_mcp.py
```

Real MCP checks are opt-in and may consume search quota:

```bash
MCP_ENABLED=true MCP_REAL_TESTS=true pytest -m real_mcp
```

Missing keys/configuration produce a skip. The execution environment must also
resolve target hosts to public addresses; Secure Fetch deliberately refuses
corporate/sandbox DNS mappings into private or benchmarking ranges.

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

### Stage 63 citation UX and Stage 64 stabilization

Completed Assistant turns render one compact Sources area with local `[S#]`
and Web/Academic `[W#]` aliases. Local sources open only through a loaded
Repository item and the managed-PDF opener; external source cards accept only
validated HTTP(S), canonical DOI, or canonical arXiv URLs. Absolute local paths
are never rendered in the Sources UI.

Stage 64 restored the runtime contract for adaptive SSE stages and Academic
retrieval events, made disconnect handling drain the bounded internal queue
while final persistence reaches a commit-or-compensate boundary, and added a
partial unique index for legacy chunks whose `processing_version_id` is null.
The migration refuses to guess which row to delete if an existing database
already contains duplicate legacy `(document_id, chunk_index)` values.

Apply and roll back the Stage 64 migration with:

```bash
cd backend
alembic upgrade head
alembic downgrade c8e4f2a6b9d1
alembic upgrade head
```

Before desktop packaging, run the deterministic gates from the repository
root. Real Provider, network, OCR, visual-GPU, soak, and manual Tauri checks
remain explicit opt-ins and must report a skip when their prerequisites are
missing.

```bash
cd backend
pytest
ruff check app tests scripts

cd ../frontend
bun run test
bun run typecheck
bun run format:check
bun run build

cd src-tauri
cargo check
cargo fmt --check
cargo clippy -- -D warnings

cd ../..
git diff --check
```

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
alembic downgrade c8e4f2a6b9d1
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
- `backend/scripts/evaluate_adaptive_graph.py`
- `backend/scripts/evaluate_heldout_research.py`
- `backend/scripts/evaluate_pdf_rag.py`
- `backend/scripts/explain_vector_search.sql`

Do not commit generated baseline outputs or real PDFs used with these
scripts.

## Current Limitations

- Born-digital, scanned, and mixed PDFs have versioned ingestion, but OCR still
  requires separately installed Tesseract; OCRmyPDF searchable output is optional.
- PLA does not bundle a local embedding model; an existing Ollama or compatible
  local endpoint can be configured from Settings.
- The MVP UI has no embedded PDF preview/reader.
- Citation click-to-page behavior is not included.
- Visual page retrieval remains disabled and requires an explicitly configured
  encoder plus real hardware/quality validation before production use.
- Provider profiles are local desktop settings; there is no account sync or
  multi-user secret sharing.
- Calendar and Notes UI are not part of the MVP.
- Web research depends on provider configuration.
- Tavily and Brave server packages must be installed and audited explicitly;
  PLA does not auto-install MCP servers.
- The Web Research Agent is bounded evidence retrieval, not an unlimited crawler
  or autonomous tool loop.
- Secure Fetch intentionally fails in networks whose DNS maps public names to
  private, link-local, reserved, or benchmarking ranges.
- Exact token resume, distributed MCP session coordination, and multi-worker
  active-run coordination are not supported.

## Development Status

MVP / experimental personal learning agent. The codebase is intentionally
scoped around Repository + Agent Chat so future work can build on a
stable LangGraph dual-agent core.

For contributor and future-agent guidance, see `AGENT.md`.
