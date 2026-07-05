import { FormEvent, useEffect, useMemo, useState } from "react";
import { listLibraryItems, queryLibraryItemRag, queryRag } from "../api/client";
import type {
  LibraryItem,
  LibraryItemRagQueryResponse,
  RagQueryResponse,
} from "../api/types";

export default function RagQueryPanel() {
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(5);
  const [sessionId, setSessionId] = useState("");
  const [includeLongTermMemory, setIncludeLongTermMemory] = useState(false);
  const [libraryItems, setLibraryItems] = useState<LibraryItem[]>([]);
  const [selectedLibraryItemId, setSelectedLibraryItemId] = useState("");
  const [result, setResult] = useState<RagQueryResponse | LibraryItemRagQueryResponse | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [contextError, setContextError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingContexts, setLoadingContexts] = useState(false);

  const selectedLibraryItem = useMemo(
    () => libraryItems.find((item) => item.id === selectedLibraryItemId) || null,
    [libraryItems, selectedLibraryItemId],
  );

  useEffect(() => {
    void loadLibraryContexts();
  }, []);

  async function loadLibraryContexts() {
    setContextError(null);
    setLoadingContexts(true);
    try {
      const response = await listLibraryItems({ status: "indexed", limit: 100 });
      setLibraryItems(response.items);
      setSelectedLibraryItemId((current) =>
        current && response.items.some((item) => item.id === current) ? current : "",
      );
    } catch (err) {
      setLibraryItems([]);
      setContextError(
        err instanceof Error ? err.message : "Could not load indexed library items.",
      );
    } finally {
      setLoadingContexts(false);
    }
  }

  async function submitQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!question.trim()) {
      setError("Question is required.");
      return;
    }
    if (!Number.isInteger(topK) || topK < 1 || topK > 20) {
      setError("top_k must be an integer between 1 and 20.");
      return;
    }

    setLoading(true);
    try {
      const payload = {
        question: question.trim(),
        top_k: topK,
        session_id: sessionId.trim() || undefined,
        include_long_term_memory: includeLongTermMemory,
      };
      const response = selectedLibraryItemId
        ? await queryLibraryItemRag({
            ...payload,
            library_item_id: selectedLibraryItemId,
          })
        : await queryRag(payload);
      setResult(response);
      setSessionId(response.session_id);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "RAG query failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>RAG Query</h2>
          <p>Ask the local backend and inspect retrieved chunks.</p>
        </div>
      </div>

      <form className="form-grid" onSubmit={submitQuery}>
        <label className="full-width">
          Context
          <div className="input-with-action">
            <select
              value={selectedLibraryItemId}
              onChange={(event) => {
                setSelectedLibraryItemId(event.target.value);
                setResult(null);
                setError(null);
              }}
            >
              <option value="">Global RAG</option>
              {libraryItems.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                  {item.author ? ` — ${item.author}` : ""}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="secondary-button"
              disabled={loadingContexts}
              onClick={loadLibraryContexts}
            >
              {loadingContexts ? "Loading..." : "Reload books"}
            </button>
          </div>
          <span className="field-help">
            {selectedLibraryItem
              ? `Book-scoped RAG: ${selectedLibraryItem.title}`
              : "No specific book selected. Queries use the global indexed knowledge base."}
          </span>
        </label>

        <label className="full-width">
          Question
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={4}
            placeholder="Ask a question about indexed learning material..."
          />
        </label>

        <label>
          top_k
          <input
            type="number"
            min={1}
            max={20}
            value={topK}
            onChange={(event) => setTopK(event.target.valueAsNumber)}
          />
        </label>

        <label>
          session_id
          <input
            value={sessionId}
            onChange={(event) => setSessionId(event.target.value)}
            placeholder="Optional"
          />
        </label>

        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={includeLongTermMemory}
            onChange={(event) => setIncludeLongTermMemory(event.target.checked)}
          />
          Include long-term memory
        </label>

        <button type="submit" disabled={loading}>
          {loading ? "Submitting..." : "Submit query"}
        </button>
      </form>

      {contextError && <p className="error">{contextError}</p>}
      {error && <p className="error">{error}</p>}

      {result && (
        <div className="response-block">
          <h3>Answer</h3>
          {isLibraryItemResult(result) && (
            <div className="result-block">
              <h3>Selected Book</h3>
              <p>
                {result.library_item.title}
                {result.library_item.author ? ` by ${result.library_item.author}` : ""}
              </p>
              <small>
                status {result.library_item.status} · type{" "}
                {result.library_item.file_type || "unknown"}
              </small>
            </div>
          )}
          <p>{result.answer}</p>

          <dl className="metadata-list">
            <div>
              <dt>session_id</dt>
              <dd>{result.session_id}</dd>
            </div>
            <div>
              <dt>retrieved</dt>
              <dd>{result.total_retrieved}</dd>
            </div>
            <div>
              <dt>recent turns</dt>
              <dd>{result.memory.used_recent_turns}</dd>
            </div>
            <div>
              <dt>long-term memories</dt>
              <dd>{result.memory.used_long_term_memories}</dd>
            </div>
          </dl>

          <h3>Retrieved Chunks</h3>
          {result.retrieved_chunks.length === 0 ? (
            <p className="empty-state">No retrieved chunks returned for this query.</p>
          ) : (
            <ul className="item-list">
              {result.retrieved_chunks.map((chunk) => (
                <li key={chunk.chunk_id}>
                  <div className="item-title">
                    <span>{chunk.document_title || "Untitled document"}</span>
                    <span>score {chunk.score.toFixed(4)}</span>
                  </div>
                  <p>{preview(chunk.content)}</p>
                  <small>
                    chunk {chunk.chunk_index} · chars {chunk.char_start}-{chunk.char_end}
                  </small>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function preview(content: string): string {
  return content.length > 260 ? `${content.slice(0, 260)}...` : content;
}

function isLibraryItemResult(
  result: RagQueryResponse | LibraryItemRagQueryResponse,
): result is LibraryItemRagQueryResponse {
  return "library_item" in result;
}
