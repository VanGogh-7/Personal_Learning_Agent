# Personal Learning Agent

Local-first learning workspace with a FastAPI backend, PostgreSQL +
pgvector storage, deterministic mock embeddings by default, optional
real Zhipu embeddings, RAG, memory, Library metadata, Notes, and a
Tauri + React desktop frontend.

## Current Stage

Stage 46: LangGraph Dual-Agent Core.

The frontend now uses Bun + Tauri + React + Vite and opens to a
Repository + Chat learning workspace:

```text
Bun + Tauri + React + Vite
PDF Repository | Agent Chat
```

Stage 36 wires the existing OpenAI-compatible LLM provider boundary into
the Agent Chat synthesis path. Stage 36A adds a real Zhipu embedding
provider and backend-only scripts for a single-book PDF RAG smoke test.
Stage 36C adds retrieval-only search output for inspecting single-book
RAG quality before answer generation. Stage 37 adds a small repeatable
retrieval eval query set for comparing future retrieval changes.
Stage 38A classifies chunks by section type and excludes known front/back
matter from default retrieval. Stage 38B polishes the manual reindex and
filtered retrieval baseline workflow. Stage 39 adds larger readable
born-digital math-PDF chunks with lightweight heading metadata. Stage 40
polishes answer grounding and normalizes local RAG citation formatting.
Stage 41 makes `/api/agent/chat` accept the simplified product request
shape expected by the final Agent Chat. Stage 42 updates the right
Agent Chat dock to use that product API as a clean chat box for the
currently selected PDF context. Stage 43 adds the left Library
Explorer product flow for adding PDFs through the desktop file picker
and indexing them through the existing backend pipeline. Stage 44 copies
imported PDFs into backend-managed Library storage before indexing so
imported items do not depend on the original selected file path. Stage
45 removes the embedded PDF workspace from the MVP UI and keeps the
frontend focused on PDF Repository selection plus Agent Chat. Stage 46
formalizes `/api/agent/chat` as an explicit LangGraph dual-agent graph
with router, Local Library Agent, Web Research Agent, and synthesis
nodes:

```text
PDF -> page-aware extraction -> section classification -> math-PDF chunking
    -> heading metadata -> Zhipu embeddings -> pgvector
    -> body-default retrieval -> Local Library Agent with [S#] citations
    -> optional Web Research Agent boundary -> Synthesis Node
    -> product Agent Chat response
```

Deterministic/mock mode remains the default for local development and
tests. Real Zhipu and DeepSeek modes are enabled only through backend
`.env` configuration and secrets stay backend-only.

## Configuration

Use the `pla` conda environment for backend work. The backend runs on
`127.0.0.1:8081`, and the frontend connects to
`http://127.0.0.1:8081`.

Backend local configuration lives in `backend/.env`, which is
automatically loaded for local FastAPI startup and Alembic migrations.
Example placeholders are tracked in `backend/.env.example` only:

```env
LLM_PROVIDER=deterministic
EMBEDDING_PROVIDER=mock
WEB_RESEARCH_PROVIDER=none
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
ZHIPU_API_KEY=your_zhipu_api_key_here
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZHIPU_EMBEDDING_MODEL=embedding-3
ZHIPU_EMBEDDING_DIMENSION=2048
LIBRARY_STORAGE_DIR=storage/library
```

Real single-book smoke mode is opt-in:

```env
EMBEDDING_PROVIDER=zhipu
LLM_PROVIDER=deepseek
```

Do not commit real `.env` files or expose API keys to the frontend.

## What Stage 46 Does

- Defines an explicit `AgentGraphState` with user message, selected
  Library item IDs, route decision, structured local/web results, final
  answer, local citations, web sources, warnings, and errors.
- Wires `/api/agent/chat` through explicit LangGraph nodes:
  `router_node`, `local_library_agent_node`, `web_research_agent_node`,
  and `synthesis_node`.
- Keeps the product request shape simple: `message` plus optional
  `selected_library_item_id` or `selected_library_item_ids`.
- Reuses existing pgvector local retrieval, section filtering, and
  normalized `[S#]` citations with page metadata.
- Adds simple local evidence quality: `strong`, `partial`, `weak`, or
  `none`.
- Adds a Web Research Provider boundary. The default
  `WEB_RESEARCH_PROVIDER=none` returns a structured unavailable result;
  deterministic mock web results remain available for tests.
- Returns additive `local_citations`, `web_sources`, `warnings`, and
  `errors` fields while preserving existing `citations`,
  `retrieved_chunks`, `session_id`, and memory response fields.

Manual single-book smoke test:

```bash
conda activate pla
cd backend
alembic upgrade head
python scripts/index_pdf.py "../Analysis.pdf" --reindex
python scripts/eval_retrieval.py --library-item-id <library_item_id> \
  --top-k 5
python scripts/search_book.py --library-item-id <library_item_id> \
  "complete metric spaces"
python scripts/ask_book.py --library-item-id <library_item_id> \
  "What does this book say about completeness, Banach spaces, or metric spaces? Answer with citations."
```

The long-term product direction is:

```text
PDF Repository manages knowledge sources.
Agent Chat is the main interaction surface.
Today Log is the learning record; Calendar remains future expansion.
Settings will stay simple: theme + long-term memory only.
```

## What Stage 46 Does Not Do

No Settings UI, embedding provider settings, local embedding provider,
database schema changes, chunking/retrieval/citation changes, reranking,
hybrid search, LLM router, complex crawling/deep research, live web
provider integration, embedded PDF reader, citation-to-page navigation,
OCR, annotations, auth/user accounts, Settings UI, Calendar work, Notes
work, tool-calling framework, or autonomous planner. Stage 46 does not
reintroduce low-level RAG/debug controls in Agent Chat.

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
