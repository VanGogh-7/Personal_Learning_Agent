import { FormEvent, useState } from "react";
import { queryRag } from "../api/client";
import type { RagQueryResponse } from "../api/types";

export default function RagQueryPanel() {
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(5);
  const [sessionId, setSessionId] = useState("");
  const [includeLongTermMemory, setIncludeLongTermMemory] = useState(false);
  const [result, setResult] = useState<RagQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submitQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!question.trim()) {
      setError("Question is required.");
      return;
    }

    setLoading(true);
    try {
      const response = await queryRag({
        question: question.trim(),
        top_k: topK,
        session_id: sessionId.trim() || undefined,
        include_long_term_memory: includeLongTermMemory,
      });
      setResult(response);
      setSessionId(response.session_id);
    } catch (err) {
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
            onChange={(event) => setTopK(Number(event.target.value))}
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

      {error && <p className="error">{error}</p>}

      {result && (
        <div className="response-block">
          <h3>Answer</h3>
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
            <p className="muted">No chunks returned.</p>
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
