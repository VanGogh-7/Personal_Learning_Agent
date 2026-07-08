# CODEX.md

## Project Overview

This repository is for a Personal Learning Agent.

The long-term goal is to build a local-first agent that helps the user manage learning materials, notes, books, study progress, and knowledge retrieval.

The project will later support:
- Document ingestion
- RAG over personal learning materials
- Short-term and long-term memory
- Learning progress tracking
- Study plan generation
- LangGraph-based agent workflows
- PostgreSQL + pgvector storage
- Optional Tauri + React desktop UI

Stage 1: Backend skeleton — completed.
Stage 2: Document ingestion MVP — completed.
Stage 3: PostgreSQL schema — completed.
Stage 4: Embedding + pgvector MVP — completed.
Stage 5: Minimal RAG Q&A MVP — completed.
Stage 6: Short-term Memory MVP — completed.
Stage 7: Long-term Memory MVP — completed.
Stage 8: Tauri + React Frontend MVP — completed.
Stage 9: Backend/Frontend Integration Polish — completed.
Stage 10: Book Library MVP — completed.
Stage 11: Open Local Files from Desktop App — completed.
Stage 12: Frontend Layout Redesign MVP — completed.
Stage 13: Library Detail Page / Panel MVP — completed.
Stage 14: Library Indexing MVP — completed.
Stage 15: Book-Scoped RAG MVP — completed.
Stage 16: Notes MVP — completed.
Stage 17: Generate LaTeX Notes from Chat — completed.
Stage 18: Local Notes File Export — completed.
Stage 19: Notes Workspace MVP — completed.
Stage 20: Open Exported Notes File — completed.
Stage 21: Real LLM Integration Boundary — completed.
Stage 22: Better Retrieval / Citations / Chunk Metadata — completed.
Stage 23: Book Summary + Topic Extraction — completed.
Stage 24: Learning History / Progress Timeline — completed.
Stage 25: Multi-Book RAG MVP — completed.
Stage 26: Chat RAG Graph Boundary MVP — completed.
Stage 27: Agent Chat Frontend Integration MVP — completed.
Stage 28: Agent Chat Stabilization / Regression Polish — completed.
Stage 29A: Frontend Bun Migration — completed.
Stage 29B: Workspace Layout Refactor MVP — completed.
Stage 30: PDF-First Library UX — completed.
Stage 31: Embedded PDF Viewer MVP — completed.
Stage 32: PDF Text Extraction / Page-Aware Indexing — completed.
Stage 33: Today Log / Calendar MVP — handled separately.
Stage 34: Backend PDF-to-RAG Pipeline MVP — completed.
Stage 35: Backend Dual-Agent LangGraph MVP — completed.
Stage 36: Real LLM Provider Integration — completed.
Stage 36A: Zhipu Real Embedding + DeepSeek Single-Book RAG Smoke Test — completed.
Stage 36C: Single-Book RAG Observability Polish — completed.
Stage 37: Retrieval Quality Baseline — completed.
Stage 38A: Retrieval Filtering for Front Matter and Back Matter — completed.
Stage 38B: Filtered Retrieval Baseline and Indexing Workflow Polish — completed.
Stage 39: Chunk Optimization v1 for Mathematical PDFs — completed.
Stage 40: Citation Formatting and Answer Grounding Polish — completed.
Stage 41: Backend Agent Chat Product API Polish — completed.
Stage 42: Frontend Agent Chat Simplification — current.

Current active stage: Stage 42: Frontend Agent Chat Simplification.

Do not implement the full product at once.

The default backend development port is `8081`.

Project stage roadmap:
1. Backend skeleton — completed
2. Document ingestion MVP — completed
3. PostgreSQL schema — completed
4. Embedding + pgvector — completed
5. Minimal RAG Q&A — completed
6. Short-term memory — completed
7. Long-term memory — completed
8. Tauri + React frontend — completed
9. Backend/frontend integration polish — completed
10. Book Library MVP — completed
11. Open local files from desktop app — completed
12. Frontend layout redesign — completed
13. Library detail page/panel — completed
14. Library indexing MVP — completed
15. Book-scoped RAG MVP — completed
16. Notes MVP — completed
17. Generate LaTeX Notes from Chat — completed
18. Local Notes File Export — completed
19. Notes Workspace MVP — completed
20. Open Exported Notes File — completed
21. Real LLM Integration Boundary — completed
22. Better Retrieval / Citations / Chunk Metadata — completed
23. Book Summary + Topic Extraction — completed
24. Learning History / Progress Timeline — completed
25. Multi-Book RAG MVP — completed
26. Chat RAG Graph Boundary MVP — completed
27. Agent Chat Frontend Integration MVP — completed
28. Agent Chat Stabilization / Regression Polish — completed
29A. Frontend Bun Migration — completed
29B. Workspace Layout Refactor MVP — completed
30. PDF-First Library UX — completed
31. Embedded PDF Viewer MVP — completed
32. PDF Text Extraction / Page-Aware Indexing — completed
33. Today Log / Calendar MVP — handled separately
34. Backend PDF-to-RAG Pipeline MVP — completed
35. Backend Dual-Agent LangGraph MVP — completed
36. Real LLM Provider Integration — completed
36A. Zhipu Real Embedding + DeepSeek Single-Book RAG Smoke Test — completed
36C. Single-Book RAG Observability Polish — completed
37. Retrieval Quality Baseline — completed
38A. Retrieval Filtering for Front Matter and Back Matter — completed
38B. Filtered Retrieval Baseline and Indexing Workflow Polish — completed
39. Chunk Optimization v1 for Mathematical PDFs — completed
40. Citation Formatting and Answer Grounding Polish — completed
41. Backend Agent Chat Product API Polish — completed
42. Frontend Agent Chat Simplification — current

---

## Current Development Scope

Stage 1 (completed): a clean backend skeleton — FastAPI app setup,
environment variable configuration, `.env.example`, health/status
endpoints, minimal DeepSeek client module, basic tests, README setup
instructions, clean backend directory structure.

Stage 2 (completed): a minimal document ingestion module for plain text
and Markdown content — character-based chunking, safe `.txt`/`.md`
loading from `backend/data`, `/api/ingestion` routes, and tests.

Stage 3 (completed): PostgreSQL schema support — `DATABASE_URL` config,
SQLAlchemy 2.x models, and Alembic migrations for `learning_sources`,
`documents`, `document_chunks`, and `agent_runs`.

Stage 4 (completed): a minimal embedding + pgvector MVP — proving the
pipeline of document chunk text → deterministic mock embedding →
vector stored in PostgreSQL → basic similarity search, via
`backend/app/embeddings/` and `backend/app/db/vector_search.py`.

Stage 5 (completed): a minimal RAG Q&A MVP — proving the pipeline of
user question → deterministic mock embedding → pgvector similarity
search over `document_chunks` → simple deterministic (extractive,
non-LLM) answer → answer plus retrieved chunks and source metadata, via
`backend/app/rag/` and `POST /api/rag/query`.

Stage 6 (completed): a minimal short-term memory MVP — a user question
(with an optional `session_id`) loads recent conversation turns for
that session, the deterministic answer generator notes when recent
context was considered, the current turn is saved afterward, and the
response includes `session_id` plus memory metadata, via
`backend/app/memory/short_term.py`.

Stage 7 (completed): a minimal long-term memory MVP — memories are
created **manually** through a small service/API, stored in PostgreSQL,
listable/searchable by type, importance, and keyword, and optionally
usable as small bounded deterministic context in RAG answers.

Stage 8 (completed): a minimal Tauri + React frontend MVP — a small
TypeScript/Vite UI under `frontend/` that calls the existing FastAPI
backend on `127.0.0.1:8081` for health/status, RAG query, and long-term
memory create/list/search. The backend remains independently started on
port `8081`.

Stage 9 (completed): backend/frontend integration polish — frontend API
types aligned with backend schemas, centralized backend URL handling,
safer fetch errors, clearer UI empty states, explicit local-development
CORS, and local development docs cleanup.

Stage 10 (completed): a Book Library MVP — manual registration,
listing, updating, archiving, and search/filtering of book or
learning-material metadata. Library items may store title, author,
description, `file_path`, `file_type`, topic tags, and status.

Stage 11 (completed): local file opening from the Tauri desktop app
only. `file_path` remains metadata stored by the backend. The desktop
frontend may ask Tauri to open that path externally with the system
default application.

Stage 12 (completed): frontend layout redesign MVP. The single long
page was refactored into a calm three-page desktop workspace with
sidebar navigation for Chat, Library, and Notes.

Stage 13 (completed): Library detail page/panel MVP. The Library page
can select a library item, view all key metadata in a structured detail
area, edit metadata, choose local files, and open local files externally.

Stage 14 (completed): Library Indexing MVP. The user can manually index
a registered Library item that points to a `.txt` or `.md` local file.
The backend reads that selected local file path, chunks text, generates
deterministic mock embeddings, persists document chunks with pgvector
embeddings, associates the document to the Library item, and marks the
item indexed.

Stage 15 (completed): Book-Scoped RAG MVP. The Chat page can select one
indexed Library item and send RAG queries to
`POST /api/rag/query/library-item`, retrieving only chunks connected to
that item's `documents.library_item_id`. Global `POST /api/rag/query`
continues to work unchanged.

Stage 16 (completed): Notes MVP. The Notes page is a minimal
database-backed LaTeX note manager. Users can create, list, view, edit,
and archive notes. Notes may optionally reference a Library item through
`notes.library_item_id`.

Stage 17 (completed): Generate LaTeX Notes from Chat. The user can take
the latest global or book-scoped Chat/RAG response, generate a
deterministic LaTeX note draft from the question, answer, retrieved
chunks, optional Library item metadata, and optional session id, review
or edit that draft, and save it through the existing Notes API.

Stage 18 (completed): Local Notes File Export. The user can select an
existing database-backed note in the Notes page, choose a local save
path through the Tauri desktop app, and write the note's LaTeX source
as a UTF-8 `.tex` file. The backend does not write arbitrary local
paths.

Stage 19 (completed): Notes Workspace MVP. The user can choose a local
Notes workspace folder from the Tauri desktop app, have that path
remembered locally, and export the selected database-backed note into
that workspace with a sanitized unique `.tex` filename. The workspace
path is local machine configuration, not PostgreSQL data.

Stage 20 (completed): Open Exported Notes File. After a successful
manual `Export as .tex` or workspace `Export to Workspace`, the Notes
page remembers the actual final `.tex` path returned by that export
operation and offers `Open Exported File`. The desktop frontend opens
only that last successful exported `.tex` path with the system default
application through Tauri opener.

Stage 21 (completed): Real LLM Integration Boundary. RAG answer
generation goes through a small backend LLM provider interface. The
deterministic/mock provider is the default for local development and
tests. A DeepSeek/OpenAI-compatible provider may be selected only by
explicit backend configuration such as `LLM_PROVIDER=deepseek`, with API
key, base URL, and model read from the existing settings mechanism.

Stage 22 added Better Retrieval / Citations / Chunk Metadata. RAG
responses expose structured citation/source metadata for each retrieved
chunk and the Chat page displays those sources clearly. The retrieval
algorithm, pgvector search, mock embeddings, book-scoped filtering,
memory behavior, and Chat-to-Notes workflow remain unchanged.

Stage 23 is Book Summary + Topic Extraction. The user can request a
deterministic summary draft and topic tag draft for an indexed Library
item. The backend collects representative indexed chunks through
`documents.library_item_id`, generates a draft without mutating the
Library item, and returns it from
`POST /api/library/items/{item_id}/metadata-draft`. The frontend Library
detail panel lets the user review/edit the summary and tags, then saves
them through the existing `PATCH /api/library/items/{item_id}` flow.
Summary uses `library_items.description`; topic tags use
`library_items.topic_tags`. No database migration is needed.

Stage 24 is Learning History / Progress Timeline. The backend records a
small event log in `learning_events`, exposes simple create/list/filter
APIs, and the frontend adds a Progress page with a recent-event
timeline. This is an event-log foundation only, not analytics,
dashboards, planning, spaced repetition, or AI progress evaluation.

Stage 25 is Multi-Book RAG MVP. The Chat page can select multiple
indexed Library items and send questions to
`POST /api/rag/query/library-items`. The backend validates the selected
items, retrieves only chunks whose documents have
`documents.library_item_id` in the selected IDs, returns selected
Library item metadata plus structured citations, preserves session and
long-term memory behavior, and records
`multi_book_rag_question_asked` only after successful responses.

Stage 26 is Chat RAG Graph Boundary MVP. The backend adds LangGraph and
`POST /api/agent/chat` as a minimal orchestration layer around existing
RAG, memory, citation, prompt, LLM provider, and learning-event
services. The graph is mostly linear:
validate_input -> resolve_scope -> load_memory -> retrieve_chunks ->
build_citations -> build_prompt -> generate_answer -> save_memory ->
record_learning_event -> format_response. This is not an open-ended
agent system, planner, tool-calling layer, or replacement for existing
RAG endpoints.

Stage 27 is Agent Chat Frontend Integration MVP. The frontend Chat page
keeps the existing UI but sends questions to `POST /api/agent/chat`.
The selected Library context maps to `scope_type`: no selected book is
`global`, one selected indexed item is `single_book`, and two or more
selected indexed items are `multi_book`. Citations, retrieved chunks,
memory metadata, loading/error states, and Chat-to-Notes remain
compatible. Existing backend RAG endpoints remain available.

Stage 28 is Agent Chat Stabilization / Regression Polish. It keeps the
Stage 27 `/api/agent/chat` integration and adds small frontend polish
for scope display, citation/source readability, empty retrieval states,
common error messages, loading/disabled states, and Chat-to-Notes
compatibility. It does not add planner behavior, tools, streaming,
graph visualization, settings, auth, themes, new graph nodes, or a new
RAG algorithm.

Stage 29A is Frontend Bun Migration. The frontend dependency workflow
uses Bun for install and script execution while preserving the existing
Tauri + React + Vite architecture. The frontend uses `bun.lock` and no
longer keeps the npm `package-lock.json`. Stage 29A does not change app
layout, backend APIs, RAG behavior, LangGraph behavior, or the Tauri,
React, and Vite architecture.

Stage 29B is Workspace Layout Refactor MVP. The product direction shifts
toward an IDE-like PDF learning workspace: PDF is the main workspace,
Library is a collapsible PDF/book explorer, Agent Chat is a docked
assistant, Today Log is the learning record, and Settings should later
stay limited to theme plus long-term memory. The
frontend opens to a Workspace page with a left PDF Library Explorer,
center PDF Workspace placeholder, and right Agent Chat panel. The
Library and Agent Chat panels can be hidden, shown, and resized, with
layout state stored in `localStorage` as `pla.workspace.layout`. Stage
29B does not add embedded PDF rendering or backend behavior.

Stage 30 is PDF-First Library UX. The official user-facing Library
format is PDF. The frontend file picker is PDF-only, new file-picker
selections infer `file_type = "pdf"`, visible Library create/edit forms
reject non-PDF paths and file types, and legacy non-PDF records are
marked unsupported in the PDF Library UI. Backend `.txt`/`.md` support
may remain for legacy/internal/test paths. Stage 30 does not add
embedded PDF rendering, PDF text extraction, PDF indexing changes,
backend API changes, or new RAG behavior.

Stage 31 is Embedded PDF Viewer MVP. The center Workspace renders the
selected local PDF using `react-pdf` and `pdfjs-dist`, with loading and
error states, previous/next page controls, total page count, and zoom
controls. The existing system PDF reader action remains available. A
minimal Tauri command reads selected local `.pdf` files as bytes for
the viewer; the FastAPI backend is unchanged. Stage 31 does not add PDF
text extraction, PDF indexing changes, page-aware citations, selected
text to chat, PDF annotations, new RAG behavior, or backend API changes.

Stage 32 is PDF Text Extraction / Page-Aware Indexing. The backend uses
`pypdf` to extract local PDF Library items page by page during indexing.
PDF chunks store nullable `document_chunks.page_start` and
`document_chunks.page_end`, and RAG citations/retrieved chunks expose
additive `page_number`, `page_start`, and `page_end` fields when page
metadata is available. The frontend Sources UI displays page metadata
minimally. Stage 32 does not add OCR, annotations, highlighting,
selected text to chat, citation-to-viewer navigation, new LangGraph
nodes, planner/tool behavior, reranking, hybrid search, BM25, or a new
RAG algorithm.

Stage 33 is Today Log / Calendar MVP. The existing learning event API
accepts an additive `date=YYYY-MM-DD` filter and returns related
Library item / Note titles when available. The frontend Today Log
defaults to today, lets the user select another date, and displays event
time, readable type, related PDF/book or note title, and useful event
metadata. Stage 33 does not add AI daily summaries, saved summaries,
full month calendar UI, streaks, duration analytics, charts,
notifications, settings, auth, new LangGraph nodes, planner/tool
behavior, multi-agent behavior, or new RAG behavior.

Stage 34 is Backend PDF-to-RAG Pipeline MVP. It hardens the backend path
from existing local PDF Library items through `pypdf` extraction,
page-aware chunking, deterministic embeddings, pgvector-backed chunk
storage, retrieval, simplified LangGraph Agent Chat orchestration, and
structured citations. The `/api/agent/chat` request contract remains the
preferred chat API. LangGraph remains orchestration only; PDF loading,
extraction, chunking, embedding, storage, retrieval, citation, memory,
and learning-event business logic stay in services. Frontend feature
expansion is paused for Stage 34.

Stage 35 is Backend Dual-Agent LangGraph MVP. The existing
`/api/agent/chat` endpoint orchestrates a deterministic router, fixed
Local Library Agent, deterministic/mock Web Research Agent, and
synthesis step. The router returns `local_only`, `web_only`, or `both`.
The Local Library Agent reuses existing PDF/RAG retrieval and page-aware
citations. The Web Research Agent does not make network calls by
default. Synthesis returns one final answer plus additive route,
summary, and web-source fields. LangGraph remains orchestration only,
not the business-logic layer. Frontend simplification is not part of
Stage 35.

Stage 36 is Real LLM Provider Integration. The existing backend LLM
provider abstraction remains the boundary, with
`LLM_PROVIDER=deterministic` as the default and `LLM_PROVIDER=deepseek`
as the explicit real OpenAI-compatible provider. Agent Chat synthesis
calls `get_llm_provider()` so `/api/agent/chat` can use the real model
when `backend/.env` provides `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`,
and `DEEPSEEK_MODEL`. Tests must not require real API keys or network
access. Secrets must stay in `backend/.env` and must never be printed,
logged, committed, or exposed to frontend code.

Stage 36A is Zhipu Real Embedding + DeepSeek Single-Book RAG Smoke Test.
It adds `EMBEDDING_PROVIDER=zhipu` for real Zhipu `embedding-3`
vectors, keeps `EMBEDDING_PROVIDER=mock` as the default for tests, and
adds backend-only scripts to index one local PDF and ask one indexed
book. DeepSeek remains the LLM provider for final answer generation
when `LLM_PROVIDER=deepseek` is configured. Stage 36A changes
`document_chunks.embedding` to `vector(2048)` and deletes old stored
chunks during migration; affected books must be re-indexed. It does
not touch frontend UI or add new retrieval algorithms.

Stage 36C is Single-Book RAG Observability Polish. It adds backend-only
`scripts/search_book.py` for inspecting the ranked chunks returned by
single-book retrieval, including scores, title metadata, chunk IDs or
indexes, page ranges, and snippets. It does not call the LLM provider,
generate answers, alter retrieval algorithms, add reranking, or change
frontend UI.

Stage 37 is Retrieval Quality Baseline. It adds backend-only
`scripts/retrieval_eval_queries.json` and `scripts/eval_retrieval.py` to
run a small repeatable single-book retrieval-only query set, print top
chunks with scores and page/snippet diagnostics, and summarize simple
expected-keyword hits. It does not call the LLM provider, change
chunking, change database schema, add reranking/hybrid search, or add
frontend UI.

Stage 38A is Retrieval Filtering for Front Matter and Back Matter. It
adds lightweight `document_chunks.section_type` metadata populated by
simple PDF indexing heuristics for body, contents, index, bibliography,
preface, and unknown sections. Default retrieval excludes known
non-body chunks, while backend scripts expose `--include-non-body` for
debugging. It does not change embedding providers, LLM providers,
chunking behavior, retrieval algorithms, frontend UI, or add ML-based
layout parsing.

Stage 38B is Filtered Retrieval Baseline and Indexing Workflow Polish.
It keeps the Stage 38A retrieval filter in place while making manual
`scripts/index_pdf.py --reindex` and `scripts/eval_retrieval.py`
baseline runs easier to inspect. The index script reports section-type
counts, and the eval summary reports query count, `top_k`, keyword hits,
page/snippet coverage, retrieved section-type counts, and non-body
retrieved count. It does not change database schema, embedding
providers, LLM providers, frontend UI, chunking, retrieval ranking,
reranking, or hybrid search.

Stage 39 is Chunk Optimization v1 for Mathematical PDFs. It changes the
PDF indexing path from small per-page chunks to larger section-aware
multi-page chunks tuned for born-digital math textbooks, with roughly
4000 characters per chunk, 650 characters of overlap, and a 350
character minimum tail target. It preserves `page_start` and `page_end`,
keeps Stage 38A/38B section filtering, and stores lightweight
`chapter_title` / `section_title` metadata using deterministic heading
heuristics. It does not add complex theorem/definition/proof parsing,
OCR, reranking, hybrid search, provider changes, frontend changes, or
retrieval ranking changes.

Stage 40 is Citation Formatting and Answer Grounding Polish. It keeps
retrieval, chunking, embeddings, provider boundaries, frontend behavior,
web research behavior, and LangGraph topology unchanged while polishing
local-library RAG answer prompts and source output. Retrieved context is
labeled with normalized `[S1]`, `[S2]`, `[S3]` IDs, real LLM answers are
asked to cite book-supported claims with those IDs, weak or indirect
context should be stated clearly, and `scripts/ask_book.py` prints a
normalized Sources list with page, chunk, section, heading, and score
metadata when available.

Stage 41 is Backend Agent Chat Product API Polish. It keeps frontend
code unchanged but lets `POST /api/agent/chat` accept a product-level
request with `message` and optional `selected_library_item_id` or
`selected_library_item_ids`. The backend infers local RAG scope from
selected Library items, keeps older debug fields optional for backward
compatibility, prefers local-library RAG for selected-book requests, and
preserves normalized citations/page/chunk/heading metadata in the
existing response shape. It does not change chunking, retrieval ranking,
embedding providers, LLM provider boundaries, web research behavior, or
LangGraph topology.

Stage 42 is Frontend Agent Chat Simplification. It keeps the existing
Workspace layout but simplifies the right Agent Chat dock into a product
chat box for the selected PDF context. The frontend sends
`POST /api/agent/chat` with `message` and, when the Workspace selection
is indexed, `selected_library_item_id`. The main UI no longer exposes
RAG mode, `top_k`, `session_id`, long-term memory, manual debug toggles,
or embedding/indexing details. Normalized Sources remain visible with
citation ID, title/source, page/page range, chunk, chapter, and section
metadata when returned. Stage 42 does not change backend code, database
schema, retrieval ranking, chunking, providers, web behavior, LangGraph
topology, settings UI, or PDF viewer behavior.

Allowed in Stage 22:
- Add structured citation/source metadata to RAG responses
- Preserve existing `retrieved_chunks` fields and add top-level `citations`
- Add deterministic citation IDs such as `S1`, `S2`, `S3`
- Include chunk, document, Library item, score, excerpt, and source path metadata where available
- Add a small citation builder/excerpt helper
- Display compact Sources on the frontend Chat page
- Preserve global RAG and book-scoped RAG retrieval behavior
- Preserve LLM provider boundary and deterministic defaults
- Preserve Chat-to-Notes compatibility
- Add deterministic tests that do not require real API keys or network calls
- Update README/CODEX.md

Do not implement in Stage 22:
- Reranking
- Hybrid search
- Full-text search
- BM25
- Query expansion
- Multi-book reasoning
- LangGraph
- Agent planning
- Tool calling
- MCP
- Multi-agent systems
- Streaming responses
- Function calling
- Advanced prompt management
- Prompt template database
- Real embedding provider
- OpenAI/DeepSeek embedding calls
- Replacing pgvector retrieval logic
- Changing chunking/indexing pipeline
- Changing embedding dimensions
- PDF page extraction
- PDF parsing
- DOCX parsing
- LaTeX parsing
- OCR
- Automatic book summary generation
- Whole-book summarization
- Complex mathematical proof generation
- Citation formatting engines
- CSL / BibTeX / Zotero integration
- Background jobs
- Redis / Celery / RQ
- Authentication or user accounts
- Production-grade secret management
- Cloud deployment
- Docker changes
- Frontend settings page
- Large UI redesign
- LaTeX compilation
- PDF generation
- PDF preview
- Internal PDF viewer
- `.pdf` export
- VS Code integration
- Opening notes in VS Code
- Dedicated VS Code integration
- Forcing files to open in VS Code
- Complex notes workspace management beyond the existing one-folder workflow
- Default `~/math_notes` workspace
- Git sync
- File watcher
- Automatic synchronization between database and local file
- Bidirectional editing
- Importing `.tex` files back into Notes
- Workspace scanning
- Multi-file LaTeX projects
- Attachments
- Folder export
- Batch export
- Background jobs
- Redis / Celery / RQ
- Changing the existing Notes CRUD architecture
- Changing the existing Chat-to-Notes architecture
- Backend arbitrary-path file writing
- Real AI note generation
- Real summarization
- Real embedding calls
- Markdown editor
- Rich text editor
- WYSIWYG editor
- CodeMirror
- Monaco editor
- Collaborative editing
- Multi-note generation
- Whole-book summary generation
- Automatic note generation on every chat response
- Complex note templates
- Complex citation system
- Changing the existing Notes CRUD architecture
- Complex tagging UI
- Full-text search
- Multi-file notes
- Attachments
- PDF parsing
- PDF preview
- Internal PDF viewer
- react-pdf
- PDF.js
- DOCX parsing
- LaTeX parsing
- File upload
- Drag-and-drop upload
- Batch import
- Folder import
- Automatic background indexing
- Automatic metadata extraction
- Automatic book summary generation
- Advanced ranking or reranking
- Multi-book RAG
- Queue system
- Redis
- Celery/RQ
- Real embedding provider
- OpenAI/DeepSeek embedding calls
- Chat with this Book actual functionality
- Related notes actual functionality
- Real LLM summary generation
- Notes generation
- LaTeX generation
- VS Code integration
- Real LLM answer generation
- MCP
- LangGraph
- Real embedding providers
- Backend auto-start from Tauri
- Complex Rust local backend logic
- Repository analysis
- Production packaging
- Authentication or user accounts
- Docker setup
- Redis or queues
- Major CSS framework migration

Allowed in Stage 23:
- Add deterministic Library metadata draft generation for indexed items
- Use existing `description` and `topic_tags` fields
- Select a small deterministic set of representative chunks
- Add Pydantic response schemas for metadata drafts
- Add `POST /api/library/items/{item_id}/metadata-draft`
- Keep draft generation non-mutating
- Reuse existing Library PATCH endpoint for saves
- Add minimal Library detail UI for generate/review/edit/save/cancel
- Add deterministic tests requiring no real API keys or network calls
- Update README/backend/frontend/CODEX documentation

Do not implement in Stage 23:
- LangGraph
- Agent planning
- Tool calling
- MCP
- Multi-agent systems
- Streaming responses
- Background jobs
- Redis / Celery / RQ
- Automatic indexing-triggered summary jobs
- Queue system
- Real embedding provider
- OpenAI/DeepSeek embedding calls
- Changing embedding dimensions
- Replacing pgvector retrieval
- Changing chunking/indexing pipeline
- PDF parsing
- DOCX parsing
- LaTeX parsing
- OCR
- Whole-book deep summarization
- Multi-book synthesis
- Knowledge graph
- Complex prompt framework
- Prompt template database
- Citation formatting engines
- BibTeX / Zotero integration
- Authentication
- User accounts
- Cloud deployment
- Large UI redesign
- Frontend API-key settings
- Exposing API keys to the frontend

Allowed in Stage 28:
- Keep Chat using `POST /api/agent/chat`
- Polish active scope display for Global RAG, Single Book, and
  Multi-Book states
- Show compact selected book titles for multi-book scope
- Improve citation/source readability using existing citation fields
- Show clear empty retrieval/citation states
- Normalize common user-facing error messages
- Disable duplicate submit and unstable context actions while a Chat
  request is running
- Preserve input text if a request fails
- Verify and minimally fix Chat-to-Notes compatibility for agent chat
  responses
- Clean up rough frontend TypeScript types without broad refactors
- Update README/frontend/CODEX documentation

Do not implement in Stage 28:
- Open-ended agent planner
- Tool calling
- MCP
- Multi-agent systems
- Autonomous agent behavior
- Reflection loop
- Retry loop
- Self-critique
- Streaming responses
- Function calling
- Frontend settings page
- User system
- Login/register
- Theme system
- New graph nodes
- Graph visualization
- New RAG algorithm
- Real embedding provider
- Real embeddings
- Reranking
- Hybrid search
- PDF parsing
- Large UI redesign

Allowed in Stage 29A:
- Use Bun for frontend dependency management and script execution
- Generate and commit `frontend/bun.lock`
- Remove `frontend/package-lock.json`
- Keep `frontend/`, `frontend/src/`, `frontend/src-tauri/`,
  `vite.config.ts`, and `package.json`
- Keep existing package scripts simple when they work with Bun
- Keep Tauri, React, and Vite unchanged
- Document `bun install`, `bun run build`, `bun run dev`, and
  `bun run tauri dev`
- Preserve backend conda environment `pla` and backend port `8081`
- Update README/backend/frontend/CODEX documentation

Do not implement in Stage 29A:
- Workspace layout refactor
- Embedded PDF viewer
- PDF.js or react-pdf integration
- PDF extraction
- Settings page
- Theme system
- User system
- Auth
- New LangGraph nodes
- Backend changes
- New RAG algorithm
- Large frontend redesign

Allowed in Stage 29B:
- Make Workspace the default frontend page
- Add a left PDF Library Explorer using existing Library APIs
- Add a center PDF Workspace placeholder only
- Dock the existing Agent Chat UI on the right
- Preserve `POST /api/agent/chat`, global/single-book/multi-book scope
  behavior, structured citations, loading/error/empty states, and
  Chat-to-Notes compatibility
- Prefer a selected indexed Library item as the current single-PDF
  Agent Chat scope when this can be done without backend changes
- Let the PDF Library and Agent Chat panels hide/show and resize by
  dragging
- Persist panel visibility and widths in `localStorage` under
  `pla.workspace.layout`
- Update navigation toward Workspace and Learning Progress; keep
  Notes/LaTeX as legacy code, not a primary product surface
- Keep Bun + Tauri + React + Vite as the frontend stack
- Update README/backend/frontend/CODEX documentation

Do not implement in Stage 29B:
- Embedded PDF viewer
- PDF.js or react-pdf integration
- PDF text extraction
- Page-aware citations
- Calendar daily summary generation
- Settings page
- Theme system
- Long-term memory management UI
- Login/register
- User system
- Auth
- New LangGraph nodes
- Planner
- Tool calling
- Multi-agent behavior
- New RAG algorithm
- Backend contract changes
- Retrieval behavior changes
- Large backend changes

Allowed in Stage 33:
- Add date filtering to the existing learning events API
- Add related Library item / Note titles to learning event responses
- Add a Today Log frontend view that defaults to today
- Allow selecting another date
- Show learning event loading, empty, and error states
- Display event time, readable type, related PDF/book or note title,
  and useful metadata when available
- Preserve Workspace, Library Explorer, embedded PDF viewer, Agent Chat,
  RAG behavior, citations, and Notes legacy behavior

Do not implement in Stage 33:
- AI-generated daily summary
- Edit/save daily summary
- Full month calendar view
- Streaks/check-ins
- Learning duration analytics
- Charts/statistics dashboard
- Notification system
- Settings page
- Theme system
- Long-term memory settings UI
- Login/register
- User system
- Auth
- New LangGraph nodes
- Planner
- Tool calling
- Multi-agent behavior
- New RAG algorithm
- Backend contract changes
- Large backend changes

Allowed in Stage 34:
- Reuse existing Library item and Document models for local PDF indexing
- Validate PDF source existence, file type, and readability
- Harden existing `pypdf` extraction where needed
- Preserve page metadata through chunking and stored document chunks
- Use the existing embedding abstraction/provider boundary
- Keep deterministic/mock embeddings as the default for tests
- Reuse existing pgvector-backed chunk storage and retrieval services
- Reuse `/api/agent/chat` for the end-to-end RAG path
- Keep LangGraph as orchestration over existing services only
- Return existing structured citations with additive page metadata
- Add deterministic backend integration tests for the PDF-to-RAG path
- Update backend and project-context documentation

Do not implement in Stage 34:
- New frontend pages
- Today Log / Calendar expansion
- Embedded PDF viewer changes
- PDF annotation
- Highlighting
- Selected text to chat
- Jump from citation to PDF page
- OCR
- Planner
- Tool calling
- Multi-agent behavior
- Authentication or user accounts
- Settings system
- Reranking
- Hybrid search
- BM25
- New RAG algorithm
- Real embedding provider integration as a default
- Large backend architecture refactor

Allowed in Stage 35:
- Add a deterministic router for `local_only`, `web_only`, and `both`
- Add fixed Local Library Agent and Web Research Agent service boundaries
- Keep the Web Research Agent deterministic/mock by default
- Reuse existing local retrieval, pgvector search, and citation services
- Preserve page-aware citation metadata when local retrieval is used
- Add a deterministic synthesis step
- Extend `POST /api/agent/chat` responses additively with route,
  summaries, and web sources
- Keep LangGraph as orchestration over services only
- Add deterministic backend tests with no network or API-key requirement
- Update backend and project-context documentation

Do not implement in Stage 35:
- Frontend UI simplification
- New frontend pages
- PDF viewer changes
- OCR
- PDF annotation or highlighting
- Citation jump to PDF page
- Authentication or user accounts
- Large settings system
- Autonomous planner
- Broad tool-calling framework
- Open-ended multi-agent behavior
- New RAG algorithm
- BM25
- Hybrid search
- Reranking
- Real web provider by default
- Database schema changes
- Major backend rewrite

Allowed in Stage 36:
- Reuse the existing backend LLM provider abstraction
- Keep deterministic/mock provider as the default
- Use `LLM_PROVIDER=deepseek` for the real OpenAI-compatible provider
- Read DeepSeek API key, base URL, and model from backend-only config
- Make Agent Chat synthesis call the configured provider
- Keep `/api/agent/chat` request/response compatibility
- Add tests that use deterministic providers or mocked HTTP clients
- Return clear configuration/provider errors without leaking secrets
- Update backend and project-context documentation

Do not implement in Stage 36:
- Frontend changes
- Frontend settings UI
- Authentication or user accounts
- Tool-calling framework
- Autonomous planner
- Web browsing implementation
- New RAG algorithm
- BM25
- Hybrid search
- Reranking
- Database schema changes
- Alembic migration
- Exposing provider secrets to frontend code

---

## Tech Stack

Backend:
- Python
- FastAPI
- pytest
- PostgreSQL (schema layer only, via SQLAlchemy 2.x + Alembic)
- SQLAlchemy 2.x
- Alembic
- psycopg (v3)
- pgvector (nullable embedding column + basic similarity search only;
  embeddings are deterministic mocks, not a real provider)
- LangGraph (Stage 26 graph boundary only; no planner, tools, MCP, or
  autonomous loop)
- Minimal RAG Q&A (`backend/app/rag/`): deterministic mock embeddings +
  pgvector search + simple extractive answer generation; no real LLM or
  embedding provider
- Short-term memory (`backend/app/memory/short_term.py`): bounded,
  per-session `conversation_turns` in PostgreSQL; deterministic context
  only, no LLM summarization
- Long-term memory MVP (`backend/app/memory/long_term.py`): manually
  created `long_term_memories` in PostgreSQL, keyword (`ILIKE`) search
  only, deterministic bounded context only; no embeddings/vector search,
  no automatic extraction or promotion

Frontend:
- Tauri + React + TypeScript + Vite frontend shell (`frontend/`)
- Fetch-based local API client for `http://127.0.0.1:8081`
- No backend auto-start, no Rust backend API
- Stage 12 layout uses local React state for Chat/Library/Notes page
  switching; do not add routing dependencies without a concrete need
- Book Library UI stores `file_path` as backend metadata and can open it
  externally through Tauri in the desktop app; it does not preview,
  parse, upload, copy, or read file contents
- Library file picker may populate `file_path` and infer `file_type`,
  but must not read, upload, copy, parse, ingest, or validate files
- Stage 14 indexing reads `.txt` and `.md` library item paths on the
  backend only after the user clicks `Index File`
- Stage 14 uses deterministic mock embeddings only; no real embedding
  provider or LLM API calls
- Stage 15 book-scoped RAG retrieves from one selected indexed Library
  item only
- Stage 16 Notes MVP stores LaTeX notes in PostgreSQL, optionally
  associates notes with Library items, and archives notes through soft
  status updates; it does not compile, preview, export, or generate
  notes
- Stage 17 Chat-to-Notes creates deterministic template-based LaTeX
  drafts from Chat/RAG responses and saves reviewed drafts through the
  existing Notes API; it does not call LLMs, summarize with AI, compile
  LaTeX, preview PDFs, or export files
- Stage 18 Notes export writes selected note editor content to a local
  `.tex` file through Tauri after a save dialog; the backend does not
  write arbitrary local file paths and no export history/sync is stored
- Stage 19 Notes Workspace stores one local workspace path in
  `localStorage` and exports selected notes into that folder with unique
  `.tex` filenames; the backend still does not know or write workspace
  paths
- Stage 20 Open Exported Notes File remembers the last successful
  exported `.tex` path from manual or workspace export and opens that
  file with the system default application through Tauri opener; it does
  not add VS Code-specific integration, LaTeX compilation, PDF
  generation, file sync, watchers, or backend file-opening endpoints
- Stage 21 Real LLM Integration Boundary adds `backend/app/llm/providers.py`
  with a deterministic default provider, optional DeepSeek-compatible
  provider selected by `LLM_PROVIDER=deepseek`, and RAG answer generation
  routed through that boundary; retrieval, mock embeddings, book-scoped
  filtering, memory behavior, and Chat-to-Notes remain deterministic by
  default
- Stage 22 Better Retrieval / Citations / Chunk Metadata adds
  structured RAG `citations`, per-chunk citation objects, deterministic
  source IDs, citation excerpts, and a compact Chat page Sources section;
  retrieval ranking, pgvector search, mock embeddings, and book-scoped
  filtering remain unchanged
- Stage 23 Book Summary + Topic Extraction adds deterministic Library
  metadata drafts for indexed items using representative chunks; drafts
  do not auto-save, reviewed summaries use `description`, reviewed tags
  use `topic_tags`, and real LLM summary/tag generation is not default
- Stage 24 Learning History / Progress Timeline adds a small
  `learning_events` table, event APIs, targeted event hooks, and a
  Progress page timeline; it does not add dashboards, charts, planning,
  reminders, or AI progress evaluation
- Stage 25 Multi-Book RAG MVP adds
  `POST /api/rag/query/library-items` and a Chat multi-select context
  for indexed Library items; retrieval is scoped in the backend through
  selected `documents.library_item_id` values, citations identify the
  source book, and no reranking, hybrid search, graph workflow, or
  agent planning is added
- Stage 26 Chat RAG Graph Boundary MVP adds `langgraph`,
  `backend/app/graphs/chat_rag_graph.py`, and `POST /api/agent/chat`.
  The graph orchestrates existing validation, scope resolution, memory,
  retrieval, citation, prompt, LLM provider, memory save, and
  learning-event services; it does not add planning, tools, MCP,
  streaming, or autonomous behavior
- Stage 27 Agent Chat Frontend Integration switches the Chat page query
  submission to `POST /api/agent/chat` while preserving the existing
  global, single-book, multi-book, citations, retrieved chunks,
  long-term memory, session id, and Chat-to-Notes user experience
- Stage 28 Agent Chat Stabilization / Regression Polish improves Chat
  scope labels, selected-book summaries, citation/source readability,
  empty retrieval states, common error messages, and disabled/loading
  states without adding new backend graph behavior or redesigning Chat
- Stage 29A Frontend Bun Migration uses Bun for frontend dependency
  management and script execution, keeps Tauri + React + Vite
  unchanged, adds `frontend/bun.lock`, removes
  `frontend/package-lock.json`, and does not change app architecture,
  backend APIs, RAG behavior, or LangGraph behavior
- Stage 29B Workspace Layout Refactor MVP makes Workspace the default
  frontend page with a collapsible/resizable PDF Library Explorer,
  center PDF Workspace placeholder, and docked Agent Chat panel.
  Workspace layout state is persisted in `localStorage` under
  `pla.workspace.layout`. Notes/LaTeX remains legacy functionality, and
  no embedded PDF viewer, PDF parsing, settings UI, auth, backend API
  contract change, retrieval change, or new LangGraph behavior is added
- Stage 30 PDF-First Library UX makes PDF the official user-facing
  Library format, restricts the frontend file picker to PDFs, marks
  legacy non-PDF records unsupported in the UI, preserves system PDF
  opening and Agent Chat scoping, and does not add PDF text extraction,
  PDF indexing changes, backend contract changes, or new RAG behavior
- Stage 31 Embedded PDF Viewer MVP renders selected local PDFs in the
  center Workspace with previous/next page controls, total page count,
  loading/error states, and zoom controls. It uses a minimal Tauri
  command to load local `.pdf` bytes, preserves system PDF opening and
  Agent Chat behavior, and does not add PDF text extraction, indexing,
  page-aware citations, annotations, backend API changes, or new RAG
  behavior
- Stage 32 PDF Text Extraction / Page-Aware Indexing adds backend
  `pypdf` extraction for local PDFs, nullable chunk page metadata,
  additive citation page fields, and a minimal Sources display update.
  It preserves existing RAG/Agent Chat behavior and does not add OCR,
  annotations, selected-text workflows, citation-to-viewer navigation,
  reranking, hybrid search, BM25, new LangGraph nodes, or a new RAG
  algorithm
- Stage 33 Today Log / Calendar MVP adds `date=YYYY-MM-DD` filtering to
  `GET /api/learning-events`, related Library item / Note titles on
  learning event responses, and a Today Log UI for viewing events by
  selected day. It does not add AI summaries, full calendar views,
  analytics, notifications, settings, auth, new LangGraph nodes, or new
  RAG behavior
- Stage 34 Backend PDF-to-RAG Pipeline MVP hardens the backend path from
  local PDF Library item to page-aware extraction, chunking, deterministic
  embeddings, pgvector-backed storage/retrieval, LangGraph Agent Chat,
  and structured page-aware citations. It pauses frontend feature
  expansion, keeps `/api/agent/chat` additive/backward-compatible, and
  does not add new RAG algorithms or move business logic into graph nodes
- Stage 35 Backend Dual-Agent LangGraph MVP adds a fixed deterministic
  router, Local Library Agent, deterministic/mock Web Research Agent, and
  synthesis step behind `/api/agent/chat`. It keeps local retrieval and
  citations in services, adds route/web-source response fields
  additively, and does not add frontend simplification, broad tools,
  autonomous planning, or open-ended multi-agent behavior
- Stage 36 Real LLM Provider Integration wires Agent Chat synthesis to
  the configured backend LLM provider. `LLM_PROVIDER=deterministic`
  remains default; `LLM_PROVIDER=deepseek` uses the OpenAI-compatible
  DeepSeek provider only when backend `.env` supplies key, base URL, and
  model. Tests mock provider/client behavior and require no real key or
  network access
- Stage 36A Zhipu Real Embedding + DeepSeek Single-Book RAG Smoke Test
  adds `EMBEDDING_PROVIDER=zhipu` for 2048-dimensional Zhipu
  `embedding-3` vectors, keeps `EMBEDDING_PROVIDER=mock` as the test
  default, and adds backend-only `scripts/index_pdf.py` and
  `scripts/ask_book.py` commands. It changes `document_chunks.embedding`
  to `vector(2048)` and deletes existing chunks during migration, so
  affected books must be re-indexed
- Stage 36C Single-Book RAG Observability Polish adds backend-only
  `scripts/search_book.py` to print ranked retrieval diagnostics for one
  Library item without LLM generation. It preserves existing retrieval
  behavior and keeps tests on deterministic/mock providers
- Stage 37 Retrieval Quality Baseline adds backend-only
  `scripts/retrieval_eval_queries.json` and `scripts/eval_retrieval.py`
  for a lightweight repeatable single-book retrieval baseline. It prints
  top-k chunks, page/snippet presence, and simple expected-keyword hit
  summaries without LLM generation, schema changes, chunking changes, or
  frontend changes
- Stage 38A Retrieval Filtering for Front Matter and Back Matter adds
  `document_chunks.section_type`, classifies PDF pages/chunks with simple
  heuristics, and excludes known non-body sections from default retrieval.
  `scripts/search_book.py` and `scripts/eval_retrieval.py` support
  `--include-non-body` for debugging
- Stage 38B Filtered Retrieval Baseline and Indexing Workflow Polish
  keeps body-only retrieval as the default, adds section-type counts to
  `scripts/index_pdf.py --reindex`, and adds aggregate section/non-body
  counts to `scripts/eval_retrieval.py`
- Stage 39 Chunk Optimization v1 for Mathematical PDFs changes PDF
  indexing to larger readable multi-page chunks, preserves page ranges,
  and adds nullable `chapter_title` / `section_title` chunk metadata
- Stage 40 Citation Formatting and Answer Grounding Polish keeps
  retrieval/chunking/provider/frontend behavior unchanged while
  normalizing `[S#]` source IDs in prompts and ask-book Sources output,
  and carrying page/section/heading metadata through citation responses
- Stage 41 Backend Agent Chat Product API Polish adds the simple
  `message` plus selected Library item request shape to
  `POST /api/agent/chat`, infers single/multi-book local RAG scope, and
  keeps debug fields optional/backward-compatible without changing
  frontend code or retrieval behavior
- Stage 42 Frontend Agent Chat Simplification removes low-level RAG and
  memory controls from the right Agent Chat dock, sends only `message`
  plus selected Library item context to `/api/agent/chat`, and keeps
  normalized Sources visible in the existing Workspace layout

Planned later:
- Production-quality agent workflows
- Calendar-style Today Log expansion
- Simple settings for theme and long-term memory
- Semantic memory embeddings and long-term memory vector search
- Rust local backend
- MCP integration

LLM provider:
- `LLM_PROVIDER=deterministic` is the default and requires no API key
- `LLM_PROVIDER=deepseek` is optional and must be explicitly configured
- DeepSeek API key, base URL, and model are read from environment/config only
- API keys must never be hard-coded, printed, logged, committed, or exposed to frontend code

Embedding provider:
- `EMBEDDING_PROVIDER=mock` is the default and requires no API key
- `EMBEDDING_PROVIDER=zhipu` is optional and must be explicitly configured
- Zhipu API key, base URL, model, and dimension are read from environment/config only
- Real PDF files used for smoke tests must stay untracked local files

---

## Security Rules

Never print, log, commit, expose, or hard-code secrets.

Never read or modify `.env` unless explicitly asked.

`.env` must be ignored by Git.

Use `.env.example` for placeholder environment variables only.

Allowed example:

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
LLM_PROVIDER=deterministic
