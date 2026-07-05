# Personal Learning Agent Frontend

Stage 8 adds a minimal Tauri + React + TypeScript frontend shell. The
FastAPI backend must be started separately on `127.0.0.1:8081`.

## Commands

```bash
npm install
npm run dev
npm run build
npm run tauri dev
```

## Current Features

- Backend health/status check
- RAG query form
- Long-term memory create form
- Long-term memory list/search

## Current Limitations

- Does not auto-start the FastAPI backend
- No MCP
- No LangGraph
- No real embedding provider integration
- No document ingestion UI or file parsing UI
- No repository analysis
- No production packaging workflow
