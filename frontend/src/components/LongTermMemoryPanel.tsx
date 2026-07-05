import { FormEvent, useState } from "react";
import {
  createLongTermMemory,
  listLongTermMemories,
  searchLongTermMemories,
} from "../api/client";
import type { LongTermMemory, LongTermMemoryListResponse } from "../api/types";

export default function LongTermMemoryPanel() {
  const [memoryType, setMemoryType] = useState("");
  const [content, setContent] = useState("");
  const [importance, setImportance] = useState(3);
  const [source, setSource] = useState("manual");
  const [tags, setTags] = useState("");
  const [createdMemory, setCreatedMemory] = useState<LongTermMemory | null>(null);
  const [filters, setFilters] = useState({
    memoryType: "",
    minImportance: "",
    limit: 20,
    keyword: "",
  });
  const [listResult, setListResult] = useState<LongTermMemoryListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingCreate, setLoadingCreate] = useState(false);
  const [loadingList, setLoadingList] = useState(false);

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!memoryType.trim()) {
      setError("Memory type is required.");
      return;
    }
    if (!content.trim()) {
      setError("Content is required.");
      return;
    }
    if (importance < 1 || importance > 5) {
      setError("Importance must be between 1 and 5.");
      return;
    }

    setLoadingCreate(true);
    try {
      const response = await createLongTermMemory({
        memory_type: memoryType.trim(),
        content: content.trim(),
        importance,
        source: source.trim() || null,
        tags: parseTags(tags),
      });
      setCreatedMemory(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Memory create failed.");
    } finally {
      setLoadingCreate(false);
    }
  }

  async function loadMemories(mode: "list" | "search") {
    setError(null);

    if (mode === "search" && !filters.keyword.trim()) {
      setError("Keyword is required for search.");
      return;
    }

    setLoadingList(true);
    try {
      const params = {
        memory_type: filters.memoryType.trim() || undefined,
        min_importance: optionalNumber(filters.minImportance),
        limit: filters.limit,
      };
      const response =
        mode === "list"
          ? await listLongTermMemories(params)
          : await searchLongTermMemories({ ...params, keyword: filters.keyword.trim() });
      setListResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Memory request failed.");
    } finally {
      setLoadingList(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Long-term Memory</h2>
          <p>Create, list, and keyword-search manual memories.</p>
        </div>
      </div>

      <div className="split-grid">
        <form className="form-grid" onSubmit={submitCreate}>
          <h3 className="full-width">Create Memory</h3>
          <label>
            memory_type
            <input value={memoryType} onChange={(event) => setMemoryType(event.target.value)} />
          </label>
          <label>
            importance
            <input
              type="number"
              min={1}
              max={5}
              value={importance}
              onChange={(event) => setImportance(Number(event.target.value))}
            />
          </label>
          <label>
            source
            <input value={source} onChange={(event) => setSource(event.target.value)} />
          </label>
          <label>
            tags
            <input
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              placeholder="comma, separated"
            />
          </label>
          <label className="full-width">
            content
            <textarea
              rows={4}
              value={content}
              onChange={(event) => setContent(event.target.value)}
            />
          </label>
          <button type="submit" disabled={loadingCreate}>
            {loadingCreate ? "Creating..." : "Create memory"}
          </button>
        </form>

        <div className="form-grid">
          <h3 className="full-width">List/Search Memories</h3>
          <label>
            memory_type
            <input
              value={filters.memoryType}
              onChange={(event) => setFilters({ ...filters, memoryType: event.target.value })}
              placeholder="Optional"
            />
          </label>
          <label>
            min_importance
            <input
              type="number"
              min={1}
              max={5}
              value={filters.minImportance}
              onChange={(event) => setFilters({ ...filters, minImportance: event.target.value })}
              placeholder="Optional"
            />
          </label>
          <label>
            limit
            <input
              type="number"
              min={1}
              max={50}
              value={filters.limit}
              onChange={(event) => setFilters({ ...filters, limit: Number(event.target.value) })}
            />
          </label>
          <label>
            keyword
            <input
              value={filters.keyword}
              onChange={(event) => setFilters({ ...filters, keyword: event.target.value })}
              placeholder="Required for search"
            />
          </label>
          <div className="button-row full-width">
            <button type="button" disabled={loadingList} onClick={() => loadMemories("list")}>
              {loadingList ? "Loading..." : "List memories"}
            </button>
            <button type="button" disabled={loadingList} onClick={() => loadMemories("search")}>
              {loadingList ? "Searching..." : "Search memories"}
            </button>
          </div>
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      {createdMemory && (
        <div className="response-block">
          <h3>Created Memory</h3>
          <MemoryCard memory={createdMemory} />
        </div>
      )}

      {listResult && (
        <div className="response-block">
          <h3>Memories ({listResult.total})</h3>
          {listResult.memories.length === 0 ? (
            <p className="muted">No memories returned.</p>
          ) : (
            <ul className="item-list">
              {listResult.memories.map((memory) => (
                <MemoryItem key={memory.id} memory={memory} />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function MemoryItem({ memory }: { memory: LongTermMemory }) {
  return (
    <li>
      <MemoryCardContent memory={memory} />
    </li>
  );
}

function MemoryCard({ memory }: { memory: LongTermMemory }) {
  return (
    <div className="memory-card">
      <MemoryCardContent memory={memory} />
    </div>
  );
}

function MemoryCardContent({ memory }: { memory: LongTermMemory }) {
  return (
    <>
      <div className="item-title">
        <span>{memory.memory_type}</span>
        <span>importance {memory.importance}</span>
      </div>
      <p>{memory.content}</p>
      <small>
        id {memory.id} · source {memory.source || "none"} · tags{" "}
        {memory.tags?.length ? memory.tags.join(", ") : "none"} · created{" "}
        {new Date(memory.created_at).toLocaleString()}
      </small>
    </>
  );
}

function parseTags(value: string): string[] | null {
  const parsed = value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);

  return parsed.length > 0 ? parsed : null;
}

function optionalNumber(value: string): number | undefined {
  if (!value.trim()) {
    return undefined;
  }

  return Number(value);
}
