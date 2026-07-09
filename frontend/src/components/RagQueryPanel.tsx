import { FormEvent, useEffect, useState } from "react";
import { queryAgentChat } from "../api/client";
import type {
  AgentChatRequest,
  AgentChatResponse,
  LibraryItem,
  RagCitation,
  WebSource,
} from "../api/types";

export default function RagQueryPanel({
  workspaceSelectedItem,
}: {
  workspaceSelectedItem?: LibraryItem | null;
}) {
  const [question, setQuestion] = useState("");
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>([]);
  const [result, setResult] = useState<AgentChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setChatTurns([]);
    setResult(null);
    setError(null);
  }, [workspaceSelectedItem?.id]);

  async function submitQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const submittedQuestion = question.trim();
    if (!submittedQuestion) {
      setError("Question is required.");
      return;
    }

    setLoading(true);
    try {
      const payload: AgentChatRequest = {
        message: submittedQuestion,
      };
      if (workspaceSelectedItem?.status === "indexed") {
        payload.selected_library_item_id = workspaceSelectedItem.id;
      }
      const response = await queryAgentChat(payload);
      setResult(response);
      setChatTurns((current) => [
        ...current,
        {
          id: current.length + 1,
          question: submittedQuestion,
          answer: response.answer,
        },
      ]);
      setQuestion("");
    } catch (err) {
      setResult(null);
      setError(formatAgentChatError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel agent-chat-panel">
      <div className="panel-heading">
        <div>
          <h2>Agent Chat</h2>
          <p>{activeContextLabel(workspaceSelectedItem)}</p>
        </div>
      </div>

      {workspaceSelectedItem && workspaceSelectedItem.status !== "indexed" && (
        <p className="empty-state">
          Selected PDF is not indexed yet. This message will use the general chat route.
        </p>
      )}

      <div className="chat-thread" aria-live="polite">
        {chatTurns.length === 0 && !loading ? (
          <p className="empty-state">Ask a question about the selected PDF.</p>
        ) : (
          <>
            {chatTurns.map((turn) => (
              <div className="chat-turn" key={turn.id}>
                <div className="chat-message user-message">
                  <p>{turn.question}</p>
                </div>
                <div className="chat-message assistant-message">
                  <div className="answer-text">{turn.answer}</div>
                </div>
              </div>
            ))}
            {loading && <p className="empty-state">Sending...</p>}
          </>
        )}
      </div>

      <form className="chat-compose" onSubmit={submitQuery}>
        <label>
          <span className="sr-only">Message</span>
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={3}
            placeholder="Ask about this PDF..."
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Sending..." : "Send"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {result && (
        <div className="response-block">
          <div className="scope-summary">
            <strong>{responseContextLabel(result)}</strong>
            <span>{routeLabel(result.route)}</span>
          </div>

          <div className="result-block">
            <h3>Local Citations</h3>
            {result.citations.length === 0 ? (
              <p className="empty-state">
                No relevant indexed chunks were retrieved for this question.
              </p>
            ) : (
              <ul className="citation-list">
                {result.citations.map((citation) => (
                  <li key={citation.citation_id}>
                    <div className="item-title">
                      <span>
                        [{citation.citation_id}] {sourceTitle(citation)}
                      </span>
                    </div>
                    <small className="citation-meta">{citationMetadata(citation)}</small>
                    <p>{citation.excerpt || "No excerpt available."}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="result-block">
            <h3>Web Sources</h3>
            {!result.web_sources || result.web_sources.length === 0 ? (
              <p className="empty-state">No web sources were returned for this answer.</p>
            ) : (
              <ul className="citation-list">
                {result.web_sources.map((source) => (
                  <li key={source.source_id}>
                    <div className="item-title">
                      <span>
                        [{source.source_id}] {source.title}
                      </span>
                    </div>
                    <small className="citation-meta">{webSourceMetadata(source)}</small>
                    <p>{source.excerpt || "No summary available."}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function webSourceMetadata(source: WebSource): string {
  const parts = [
    source.provider ? `Provider: ${source.provider}` : null,
    source.published_date ? `Published: ${source.published_date}` : null,
    source.url,
  ];
  return parts.filter(Boolean).join(" · ");
}

type ChatTurn = {
  id: number;
  question: string;
  answer: string;
};

function sourceTitle(citation: RagCitation): string {
  return (
    citation.library_title ||
    citation.document_title ||
    citation.document_source_path ||
    "Unknown source"
  );
}

function activeContextLabel(item?: LibraryItem | null): string {
  if (!item) {
    return "Ask a question. Selecting a PDF adds book context automatically.";
  }
  if (item.status !== "indexed") {
    return `${item.title} is selected but not indexed.`;
  }
  return `Using ${item.title}`;
}

function responseContextLabel(result: AgentChatResponse): string {
  if (result.selected_library_items.length === 0) {
    return "General chat";
  }
  return result.selected_library_items.map((item) => item.title).join(", ");
}

function routeLabel(route: AgentChatResponse["route"]): string {
  if (route === "local_only") {
    return "Local library";
  }
  if (route === "web_only") {
    return "Web route";
  }
  return "Local library and web route";
}

function citationMetadata(citation: RagCitation): string {
  const parts = [
    citationPageLabel(citation),
    `Chunk: ${citation.chunk_index}`,
    citation.chapter_title ? `Chapter: ${citation.chapter_title}` : null,
    citation.section_title ? `Section: ${citation.section_title}` : null,
    citation.document_title ? `Document: ${citation.document_title}` : null,
  ];
  return parts.filter(Boolean).join(" · ");
}

function citationPageLabel(citation: RagCitation): string | null {
  if (citation.page_number) {
    return `Page: ${citation.page_number}`;
  }
  if (citation.page_start && citation.page_end) {
    return citation.page_start === citation.page_end
      ? `Page: ${citation.page_start}`
      : `Pages: ${citation.page_start}-${citation.page_end}`;
  }
  return null;
}

function formatAgentChatError(error: unknown): string {
  const message = error instanceof Error ? error.message : "";
  const normalized = message.toLowerCase();

  if (normalized.includes("network request failed")) {
    return "Backend unavailable. Make sure the FastAPI backend is running at http://127.0.0.1:8081.";
  }
  if (normalized.includes("scope_type")) {
    return "The chat request is invalid. Reload the page and try again.";
  }
  if (
    normalized.includes("not been indexed") ||
    normalized.includes("no indexed chunks")
  ) {
    return "The selected book is not indexed or has no searchable chunks.";
  }
  if (normalized.includes("library item not found")) {
    return "One selected book could not be found. Reload the book list and try again.";
  }

  return message || "Agent chat request failed.";
}
