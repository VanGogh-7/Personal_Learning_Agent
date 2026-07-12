# AGENT.md

## Project Identity

This repository is a LangGraph-based Personal Learning Agent. It is not
a PDF reader. The first MVP is scoped to a PDF Repository for knowledge
source management and Agent Chat as the main interaction surface.

## MVP Scope

- Repository + Agent Chat frontend.
- Add PDFs through the Tauri file picker.
- Copy imported PDFs into backend-managed storage.
- Classify born-digital/scanned/mixed PDFs and retain retryable OCR processing
  versions without modifying the source PDF.
- Chunk, embed, retrieve, and cite local Library evidence.
- Run `/api/agent/chat` through an explicit LangGraph dual-agent graph.
- Stream `/api/agent/chat/stream` as POST SSE while retaining `/api/agent/chat`
  as the compatible complete-JSON route.
- Keep conversation/thread mapping internal and persist production checkpoints in PostgreSQL.
- Use bounded recent turns, rolling summaries, and typed long-term memory.
- Keep `conversationId`, messages, and selected Library item IDs in one
  conversation state; Repository selection must not remount or reset Chat.
- Repository single-click toggles temporary Agent context, while double-click
  sends only the Library item ID to the Backend managed-file resolver.
- Preserve local citations as `[S1]`, `[S2]`, etc.
- Preserve web sources as `[W1]`, `[W2]`, etc.
- Emit request-scoped structured latency summaries without sensitive content.
- Keep real Provider, network, soak, and manual Tauri validation explicitly
  opt-in; ordinary pytest must never consume external quota.
- Expose only real product-level Activity and final Synthesis token deltas;
  never expose prompts, raw node state, tool payloads, or private reasoning.
- Persist one complete Assistant answer and its citation payload atomically
  before emitting successful `done`.
- Run Local and Web branches concurrently for `both` and defer non-critical
  Memory post-processing until after the HTTP response.
- Render Assistant messages as safe Markdown with GFM and locally bundled
  KaTeX for `$...$` inline math and `$$...$$` display math.

## MVP Non-Goals

Do not add or reintroduce these unless the user explicitly requests a
new stage for them:

- embedded PDF preview/reader
- local embedding model deployment
- automatic OCR/visual-model installation
- production visual-page retrieval without measured real-model evidence
- Calendar UI
- Notes UI
- broad tool calling or autonomous planning

## Architecture

- Frontend: Tauri + React + Bun + Vite.
- Backend: FastAPI + LangGraph.
- Database: PostgreSQL + pgvector.
- Embeddings: API-based provider with mock provider for tests.
- LLM: API-based provider with deterministic provider for tests.
- Web Research Agent: deterministic planner over an allowlisted MCP gateway for
  Tavily, Brave, Secure Fetch, and academic metadata, with legacy provider
  compatibility.

## LangGraph Design

`POST /api/agent/chat` runs the MVP graph:

```text
Router Node
  -> Local Library Agent Node --\
                                -> Synthesis Node
  -> Web Research Agent Node --/
```

Before routing, the graph resolves `conversation_id`, loads the rolling
summary plus at most `MEMORY_RECENT_TURN_LIMIT` effective turns, and retrieves
a bounded namespace-isolated long-term memory context. After synthesis it
persists the turn before returning the HTTP response. Summary, extraction, and
consolidation then run as managed background work with an independent database
session. Summary/extraction/retrieval failures are logged and must not fail an
otherwise successful chat response.

The product may expose `conversation_id`; it must not expose LangGraph
`thread_id`, checkpoint namespaces, retrieval scores, or memory thresholds.
Long-term memory is untrusted personalization context and cannot replace local
`[S#]` evidence or web `[W#]` evidence.

- Router Node: deterministic route selection.
- Local Library Agent Node: pgvector retrieval over selected/local
  Library content and normalized `[S#]` citations.
- Web Research Agent Node: provider-backed structured web results and
  `[W#]` sources; unavailable providers return warnings, not crashes.
- Synthesis Node: combines local and web outputs while keeping local
  citations and web sources structurally separate.

The streaming route uses the same nodes and services through LangGraph
`astream` with `custom` plus final `values`. Product statuses are written only
at real node boundaries. Final-answer deltas use the private custom kind
`synthesis_token`; the API whitelist maps only that kind to public `token`
events. Local and Web branches remain parallel. The bounded event queue applies
backpressure so disconnect checks and client delivery stay interleaved.

During generation no token is persisted. The final transaction creates a
provisional conversation if needed, writes one complete turn with full
citations/web sources in turn metadata, and writes the learning event. Memory
post-processing is deferred. Checkpoint durability is `exit`; the API emits
`citations`, `final`, then `done` only after graph/checkpoint completion.
Cancellation, Provider failure, or persistence failure must never emit `done`
or leave a completed partial turn.
One in-process run registry rejects a second active stream for the same
conversation with `409`; it never serializes unrelated conversations.

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
- `frontend/src/streaming/`: SSE protocol types, parser, and run state machine.
- `frontend/src/components/AgentActivity.tsx`: real backend-driven Activity.
- `frontend/src/components/SourcesPanel.tsx`: grouped local/web/academic source cards.
- `frontend/src/sources/sourceUtils.ts`: source normalization, safe URLs, and display-only deduplication.
- `frontend/src/tauri/filePicker.ts`: PDF-only desktop file picker.
- `frontend/src/tauri/pdfOpener.ts`: ID-only managed-PDF API boundary.
- `backend/app/library/managed_files.py`: database lookup, canonical managed-root
  enforcement, PDF validation, and system opener boundary.
- `frontend/src/chat/conversationState.ts`: current conversation, messages,
  selected-book IDs, and refresh persistence.
- `backend/app/api/agent_routes.py`: JSON and SSE Agent endpoints.
- `backend/app/streaming/`: public event schemas, SSE encoder, and execution service.
- `backend/app/graphs/chat_rag_graph.py`: LangGraph state and nodes.
- `backend/app/memory/`: checkpoint, conversation, summary, extraction,
  consolidation, retrieval, context, and repository boundaries.
- `backend/app/agents/router.py`: deterministic route heuristics.
- `backend/app/agents/local_library.py`: local retrieval agent.
- `backend/app/agents/web_research.py`: web provider boundary.
- `backend/app/mcp/config.py`: audited server configuration and tool allowlists.
- `backend/app/mcp/client.py`: reusable STDIO/Streamable HTTP lifecycle manager.
- `backend/app/mcp/gateway.py`: per-request MCP call budget.
- `backend/app/mcp/research.py`: deterministic planner, provider selection, and fallback.
- `backend/app/mcp/evidence.py`: evidence normalization, ranking, and deduplication.
- `backend/app/mcp/servers/fetch.py`: SSRF-protected public-page Fetch MCP.
- `backend/app/mcp/servers/academic.py`: local arXiv/OpenAlex/Crossref MCP server.
- `backend/app/agents/synthesis.py`: final answer synthesis.
- `backend/app/library/importing.py`: managed PDF import flow.
- `backend/app/library/indexing.py`: PDF indexing flow.
- `backend/app/rag/retrieval.py`: pgvector retrieval.
- `backend/app/rag/citations.py`: normalized local citation IDs.
- `backend/scripts/index_pdf.py`: developer PDF indexing script.
- `backend/scripts/search_book.py`: retrieval inspection script.
- `backend/scripts/eval_retrieval.py`: retrieval eval script.
- `backend/scripts/ask_book.py`: single-book ask script.
- `backend/scripts/benchmark_agent_latency.py`: mock-by-default latency benchmark.
- `backend/scripts/benchmark_agent_streaming.py`: perceived-latency SSE benchmark.
- `backend/scripts/benchmark_real_providers.py`: opt-in DeepSeek/Zhipu/Tavily benchmark.
- `backend/scripts/verify_sse_delivery.py`: direct/proxy arrival-time verifier.
- `backend/scripts/soak_agent_sse.py`: explicit repeated/cancellation HTTP soak.
- `backend/app/reliability/`: safe reports, dimension checks, and SSE probe parser.
- `backend/deployment/nginx-sse.example.conf`: optional non-buffering proxy location.
- `backend/scripts/explain_vector_search.sql`: executable L2 query-plan template.

## Commands

Backend:

```bash
conda activate pla
cd backend
pytest
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8081
python scripts/benchmark_agent_latency.py --runs 10
python scripts/benchmark_agent_streaming.py --runs 10
python scripts/verify_sse_delivery.py --base-url http://127.0.0.1:8081 --route local_only
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
  - `BRAVE_API_KEY`

Tests should use deterministic/mock providers and must not require real
Zhipu, DeepSeek, Tavily, Brave, Serper, or other network API access.

Latency logging is controlled by `AGENT_LATENCY_LOGGING_ENABLED`. Internal
response timings require both non-production `APP_ENV` and
`AGENT_DEBUG_TIMINGS_IN_RESPONSE=true`. Never add prompts, messages, answers,
chunk bodies, keys, or vectors to latency logs. Real Provider benchmarks must
be explicitly enabled with `--real-providers` because they consume quota.
Streaming is controlled by `AGENT_STREAMING_ENABLED`; Activity can be disabled
independently with `AGENT_ACTIVITY_EVENTS_ENABLED`. UI flush and heartbeat
settings are validated backend configuration, not user-facing request fields.
SSE logs/events must follow the same sensitive-data exclusions as Stage 52.
Real Provider work additionally requires `PLA_REAL_PROVIDER_TESTS=true` and an
explicit marker/CLI confirmation. Reports may include Provider/model names,
hostnames, timestamps, counts, and aggregate latency, but never keys, prompts,
full questions, token text, or raw Provider responses.

Stage 54 reliability rules:

- Keep `real_provider`, `network`, `soak`, and `manual_tauri` excluded from
  default pytest.
- Validate actual embedding response length before any real write; never infer
  it only from Settings or documentation.
- Keep Tavily behavior unchanged above the transport boundary; client reuse,
  timeout/error normalization, and URL deduplication are allowed.
- Treat reverse-proxy and Tauri WebView checks as manual until actually run.
- The active-run registry is process-local and must not be described as
  multi-worker safe.
- Assistant/citation/learning-event SQL writes are atomic with each other;
  checkpointing remains outside that transaction and compensation is best effort.
- Fault injection stays deterministic, test-only, default-off, and forbidden in
  production. Do not add public debug failure endpoints.

Stage 55 MCP rules:

- Keep `MCP_ENABLED=false` and `MCP_REAL_TESTS=false` by default. Ordinary
  pytest must never start external Tavily/Brave servers or consume API quota.
- Never auto-install an MCP server. Default external commands use
  `npx --no-install`; operators install and pin audited packages separately.
- The model never receives unrestricted MCP discovery. A tool must be present
  in both the server discovery response and PLA's static per-server allowlist.
- Reuse manager-owned sessions across requests and close them in FastAPI
  lifespan. Cancellation must stop the affected runtime before later Fetch work.
- `local_only` never calls MCP. In `both`, the independent Local and Web graph
  branches remain parallel.
- Synthesis receives only normalized Web evidence, never raw MCP JSON. Academic
  sources remain `[W]` with `source_type=academic` metadata.
- Fetch only preselected public HTTP(S) URLs. Keep DNS, redirect, peer-address,
  content-type, response-size, redirect-count, and timeout checks intact.
- Never log keys, raw tool arguments, full web pages, prompts, or MCP subprocess
  stderr. Public SSE Activity must use stable product stages, not server/tool names.
- The local Academic MCP is metadata-only: no PDF downloads, automatic
  Repository imports, or citation-graph traversal.

Stage 56 MCP reliability rules:

- FastAPI lifespan is the only owner of the shared `MCPClientManager`. Keep
  servers lazy and reusable; never start one subprocess or HTTP session per
  Agent request.
- Preserve the explicit server states `disabled`, `starting`, `healthy`,
  `degraded`, and `unavailable`. Health checks may repeat discovery but must not
  execute a search or consume Provider quota.
- Keep one serialized worker and a bounded pending queue per MCP session.
  `MCP_TOTAL_TIMEOUT_SECONDS` must include queueing, bounded retries, and
  backoff; never add an unbounded retry or recursive fallback.
- Every gateway tool needs both a static allowlist entry and an internal
  Pydantic argument schema. Discovery alone never authorizes a new tool or
  parameter.
- Cancellation and shutdown must fail current/queued callers, close the
  transport, and release `pla-mcp-*` worker tasks. Do not continue Fetch,
  fallback, final persistence, or Memory post-processing after cancellation.
- Secure Fetch requires public HTTP(S) targets before connection, on every
  redirect, and at the connected peer when available. Preserve mixed-DNS,
  IPv4-mapped IPv6, private/link-local/metadata, content-type, size, redirect,
  read-timeout, and total-time defenses.
- MCP structured logs may contain request ID, server, approved tool, transport,
  outcome, and safe error category only. Never add arguments, response bodies,
  subprocess stderr, raw exception stacks, or secrets.
- The manager is process-local. Do not claim cross-worker coordination or add
  Redis/database locks as incidental reliability work.

Stage 57 adaptive graph rules:

- Query semantics must validate against `QueryAnalysis`. Real LLM JSON is
  advisory semantic input; deterministic code alone selects from the fixed
  execution modes and graph paths.
- Local, Web, and Academic research return structured evidence only. Final
  Synthesis is the sole long-form answer generator.
- One request shares one `MCPToolGateway` across Web, Academic, and correction,
  so graph loops never reset `MCP_MAX_CALLS_PER_REQUEST`.
- Independent research branches may run concurrently. Never bypass the Stage
  56 per-session serialized worker to force concurrency inside one MCP server.
- Corrective retrieval defaults to one attempt and has a hard limit of two.
  Keep successful prior evidence and never introduce an open-ended graph loop.
- Citation verification is deterministic first. Permit at most one repair and
  one re-verification; persisted text and the final SSE response must be the
  verified version.
- Public Activity uses stable product stages only. Never expose analysis JSON,
  internal node names, prompts, tool arguments, raw evidence payloads, or
  chain-of-thought.
- Keep the current dense Local retrieval implementation unless a separate
  measured RAG stage explicitly adds keyword retrieval, reranking, or parent
  context expansion.

Stage 58 evaluation rules:

- Keep `backend/evals/adaptive_graph.jsonl` human-labelled and schema-valid.
  Golden labels are primary; LLM judges are experiments, never ground truth.
- Default evaluation must remain deterministic and network-free. Real DeepSeek
  runs require `PLA_REAL_PROVIDER_TESTS=true`, `--real-providers`, and
  `--confirm-costs` together.
- Never write questions, prompts, raw evidence, keys, Authorization headers, or
  full Provider payloads to evaluation reports. Safe case IDs, request IDs,
  routes, aggregates, token counts, and error types are allowed.
- Do not hard-code Provider prices. Cost is null unless explicit per-million
  input and output rates are supplied for that run.
- Keep experimental LLM grader and semantic verifier adapters under
  `app.evaluation`; do not import them into the production Graph or enable them
  by default.
- Treat offline path latency and call counts as proxies. Use Stage 52/54 real
  traces for Provider TTFT, generation, MCP latency, persistence, and perceived
  frontend latency.
- Apply production rule changes only for repeated labelled failures. Document
  before/after metrics and do not tune thresholds from one anecdotal case.

Stage 59 held-out evaluation rules:

- Keep `evals/heldout/cases.jsonl`, `labels.jsonl`, and `claims.jsonl`
  separate. Model and MCP calls receive case inputs or source excerpts only;
  expected intent, route, grade, and claim labels belong exclusively to scoring.
- Never use the held-out labels to tune production QueryAnalysis rules, grader
  thresholds, or citation triggers. Create a new sealed validation subset if a
  later measured defect justifies a production change.
- Real QueryAnalysis, MCP sampling, and semantic verification require
  `PLA_REAL_PROVIDER_TESTS=true`, explicit CLI flags, and `--confirm-costs`.
  They remain excluded from ordinary pytest and must skip clearly without keys.
- Semantic verification stays in `app.evaluation`; production Graph modules
  must not import it. A recommendation requires human claim labels plus measured
  precision, recall, false-positive rate, latency, failures, and token cost.
- Generated reports may contain case IDs, routes, aggregate metrics, safe error
  categories, and bounded normalized public-source samples. Do not include full
  questions, prompts, claim text, complete pages, Authorization data, or keys.
- Do not describe offline deterministic latency as Provider latency. Real
  DeepSeek and MCP results must record the run count and environment and must
  not be generalized from a single run.

Stage 60 Settings and Provider rules:

- Store Provider profile metadata and secret references only. API keys belong
  in Tauri Stronghold, never PostgreSQL, localStorage, ordinary JSON, logs,
  traces, exception text, or API responses.
- The Stronghold passphrase is session-only. Browser development may keep a key
  in memory for testing but must clearly state that persistent secure storage
  requires the Tauri desktop runtime.
- Preserve `.env` DeepSeek/Zhipu/deterministic configuration as the fallback
  whenever no unlocked runtime profile exists.
- Capture Chat and Embedding Provider snapshots before each Agent run. Profile
  activation affects new requests only and must not mutate an in-flight stream.
- Keep Provider-specific payloads inside adapters. Graph, RAG, evaluation, and
  UI code consume normalized chat chunks, structured results, embeddings, and
  capability metadata.
- Never activate an Embedding profile until its index version is `ready`.
  Versioned vectors live in `chunk_embeddings` and every query filters one exact
  `embedding_index_version`; do not overwrite or mix the legacy vector column.
- Long-term Memory retains its existing configured embedding space until a
  separate measured Memory migration explicitly versions that schema.
- Connection tests are minimal and bounded. They must not create Conversation,
  Memory, citation, or learning-event records and must return safe errors only.

Stage 61 legacy-PDF and retrieval rules:

- Keep the source PDF immutable. OCRmyPDF output, page OCR data, chunks, and
  visual vectors belong to a new processing/index version; activate it only
  after successful text extraction and embedding.
- Persist only bounded classification evidence, page/bbox metadata, confidence,
  extraction method, parser/OCR versions, and checksums. Never log full page
  text or rendered page images.
- PyMuPDF plus deterministic math/layout rules is the sole production parser in
  this stage. Do not add Docling, MinerU, or PP-Structure as parallel main paths.
- PDF Local Research uses dense plus PostgreSQL full-text candidates, RRF,
  bounded reranking, and parent context. Preserve non-PDF dense compatibility,
  selected-book filtering, `LocalEvidence`, and `[S#]` page citations.
- Text, OCR-text, Stage 60 embedding, and visual page versions are isolated.
  Queries must use `documents.active_processing_version_id`, an exact active
  embedding-index version, and matching visual model/dimension/page checksum.
- Visual retrieval is opt-in and default-off. Never auto-download a model,
  assume a GPU, or describe the deterministic fixture encoder as production.
- Use `scripts/evaluate_pdf_rag.py` for offline comparison. Treat checked-in
  latency/storage values as fixture proxies; real OCR/GPU claims require an
  explicitly marked run and recorded environment.
- Do not add an ANN vector index without measured production-scale evidence.

Stage 63 source and citation UX rules:

- Preserve `[S#]` for local Library evidence and `[W#]` for Web/Academic evidence.
  Citation interaction may enhance these markers but must never introduce a new
  marker family or rewrite answer HTML.
- Render one compact Sources area inside each completed Assistant turn. Group
  Local, Web, and Academic cards while retaining every original citation ID as
  an alias when adjacent pages or duplicate external records share one card.
- Open local citations only by matching `library_item_id` to a loaded Repository
  item and reusing the ID-only managed-PDF endpoint. Never render or return an
  absolute local path and never add an arbitrary-path backend endpoint.
- External source opening must use the Tauri opener after frontend validation of
  `http` or `https`; reject `javascript`, `file`, and malformed URLs. Prefer a
  canonical DOI URL, then canonical arXiv URL, when those identifiers exist.
- Treat OCR excerpts as fallible extraction. Label OCR sources and show the
  lightweight confidence warning only below the UI threshold; keep page and
  bounded bbox metadata in the response contract.
- Sources remain an additive response/UX change. Do not change Graph routing,
  retrieval scoring, MCP execution, Memory, Provider Settings, or model setup.

Stage 64 stabilization rules:

- Keep Backend `AgentActivityStage`, retrieval sources, frontend streaming
  types, and the runtime SSE parser whitelist synchronized. TypeScript types
  alone do not validate incoming network events.
- On disconnect during final persistence, let the transaction reach its
  commit-or-compensate boundary while draining discarded internal events so a
  bounded queue cannot deadlock the producer or retain the active-run lock.
- Preserve legacy chunk uniqueness when `processing_version_id IS NULL` with
  the Stage 64 partial unique index. Never delete ambiguous duplicate rows in a
  migration; block with a clear remediation message instead.
- Provider profile metadata may persist, but runtime clients do not survive a
  Backend restart and the Backend cannot read Stronghold. Expose the runtime
  activation state and require explicit reconnection after vault unlock; keep
  `.env` fallback behavior unchanged.
- Do not edit already-applied migrations, start sidecar packaging, enable Visual
  Retrieval, or claim opt-in real environment checks that were not executed.

Stage 64B packaging rules:

- Library/import API responses must not expose managed or source absolute paths.
  PDF opening accepts only a `library_item_id`; resolve it from the database,
  canonicalize the storage root and file, and reject traversal, root/symlink
  escapes, missing files, and non-PDF content before launching the system app.
- Applied Alembic revisions remain immutable. They are excluded only from the
  full-tree formatter; migration-chain checks and Ruff lint still run.
- Production streaming must support the synchronous PostgreSQL checkpoint saver.
  Keep the async-to-thread bridge in the timing wrapper unless the whole saver
  lifecycle is deliberately migrated and both JSON and SSE paths are retested.
- Release audits are `bun audit`, `pip-audit -r requirements.txt`, and
  `cargo audit`. Classify vulnerabilities, unsound advisories, unmaintained
  dependencies, and ordinary warnings separately; do not force incompatible
  transitive upgrades.

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
- Measure before optimizing. Keep TTFT, generation, embedding API, vector SQL,
  Memory, checkpoint, persistence, and frontend render timings distinct.
- Keep conversation memory, long-term user memory, learning events, and
  document knowledge in separate typed stores.
- Prefer existing services and schemas over new abstractions.
- Update `README.md` and this file when the MVP shape or operational
  commands change.
