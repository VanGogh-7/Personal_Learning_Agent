import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  createChatNoteDraft,
  createNote,
  listLibraryItems,
  queryAgentChat,
} from "../api/client";
import type {
  AgentChatRequest,
  AgentChatResponse,
  AgentChatScopeType,
  ChatNoteDraftResponse,
  LibraryItem,
  Note,
  RagCitation,
} from "../api/types";

export default function RagQueryPanel({
  workspaceSelectedItem,
}: {
  workspaceSelectedItem?: LibraryItem | null;
}) {
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(5);
  const [sessionId, setSessionId] = useState("");
  const [includeLongTermMemory, setIncludeLongTermMemory] = useState(false);
  const [libraryItems, setLibraryItems] = useState<LibraryItem[]>([]);
  const [selectedLibraryItemIds, setSelectedLibraryItemIds] = useState<string[]>([]);
  const [result, setResult] = useState<AgentChatResponse | null>(null);
  const [lastQuestion, setLastQuestion] = useState("");
  const [noteDraft, setNoteDraft] = useState<ChatNoteDraftResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [contextError, setContextError] = useState<string | null>(null);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [noteSuccess, setNoteSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingContexts, setLoadingContexts] = useState(false);
  const [generatingNote, setGeneratingNote] = useState(false);
  const [savingNote, setSavingNote] = useState(false);

  const selectedLibraryItems = useMemo(
    () => libraryItems.filter((item) => selectedLibraryItemIds.includes(item.id)),
    [libraryItems, selectedLibraryItemIds],
  );
  const activeScope = scopeTypeForSelection(selectedLibraryItemIds);

  useEffect(() => {
    void loadLibraryContexts();
  }, []);

  useEffect(() => {
    if (!workspaceSelectedItem) {
      return;
    }

    if (workspaceSelectedItem.status !== "indexed") {
      setSelectedLibraryItemIds([]);
      setResult(null);
      setError(null);
      setLastQuestion("");
      clearNoteDraft();
      return;
    }

    setLibraryItems((current) =>
      current.some((item) => item.id === workspaceSelectedItem.id)
        ? current.map((item) =>
            item.id === workspaceSelectedItem.id ? workspaceSelectedItem : item,
          )
        : [workspaceSelectedItem, ...current],
    );
    setSelectedLibraryItemIds([workspaceSelectedItem.id]);
    setResult(null);
    setError(null);
    setLastQuestion("");
    clearNoteDraft();
  }, [workspaceSelectedItem]);

  async function loadLibraryContexts() {
    setContextError(null);
    setLoadingContexts(true);
    try {
      const response = await listLibraryItems({ status: "indexed", limit: 100 });
      const indexedItems =
        workspaceSelectedItem?.status === "indexed" &&
        !response.items.some((item) => item.id === workspaceSelectedItem.id)
          ? [workspaceSelectedItem, ...response.items]
          : response.items;
      setLibraryItems(indexedItems);
      setSelectedLibraryItemIds((current) =>
        current.filter((itemId) => indexedItems.some((item) => item.id === itemId)),
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
      const payload: AgentChatRequest = {
        question: question.trim(),
        scope_type: activeScope,
        library_item_id:
          selectedLibraryItemIds.length === 1 ? selectedLibraryItemIds[0] : null,
        library_item_ids:
          selectedLibraryItemIds.length >= 2 ? selectedLibraryItemIds : [],
        top_k: topK,
        session_id: sessionId.trim() || undefined,
        include_long_term_memory: includeLongTermMemory,
      };
      const response = await queryAgentChat(payload);
      setResult(response);
      setLastQuestion(payload.question);
      setSessionId(response.session_id);
      clearNoteDraft();
    } catch (err) {
      setResult(null);
      setError(formatAgentChatError(err));
    } finally {
      setLoading(false);
    }
  }

  async function generateNoteDraft() {
    if (!result) {
      return;
    }

    setNoteError(null);
    setNoteSuccess(null);
    setGeneratingNote(true);
    try {
      const draft = await createChatNoteDraft({
        question: lastQuestion || question.trim(),
        answer: result.answer,
        retrieved_chunks: result.retrieved_chunks.map((chunk) => ({
          id: chunk.chunk_id,
          document_id: chunk.document_id,
          document_title: chunk.document_title,
          chunk_index: chunk.chunk_index,
          content: chunk.content,
          score: chunk.score,
        })),
        library_item:
          result.scope_type === "single_book"
            ? result.selected_library_items[0] || null
            : null,
        session_id: result.session_id,
      });
      setNoteDraft(draft);
    } catch (err) {
      setNoteError(err instanceof Error ? err.message : "Could not generate note draft.");
    } finally {
      setGeneratingNote(false);
    }
  }

  async function saveNoteDraft() {
    if (!noteDraft) {
      return;
    }

    setNoteError(null);
    setNoteSuccess(null);
    setSavingNote(true);
    try {
      const note: Note = await createNote({
        title: noteDraft.title,
        content_latex: noteDraft.content_latex,
        description: noteDraft.description || null,
        library_item_id: noteDraft.library_item_id || null,
        source_session_id: noteDraft.source_session_id || null,
        topic_tags: noteDraft.topic_tags || null,
      });
      setNoteSuccess(`Saved note "${note.title}".`);
      setNoteDraft(null);
    } catch (err) {
      setNoteError(err instanceof Error ? err.message : "Could not save note.");
    } finally {
      setSavingNote(false);
    }
  }

  function clearNoteDraft() {
    setNoteDraft(null);
    setNoteError(null);
    setNoteSuccess(null);
  }

  function toggleLibraryItem(itemId: string) {
    setSelectedLibraryItemIds((current) =>
      current.includes(itemId)
        ? current.filter((selectedId) => selectedId !== itemId)
        : [...current, itemId],
    );
    setResult(null);
    setError(null);
    setLastQuestion("");
    clearNoteDraft();
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Agent Chat</h2>
          <p>Ask across indexed PDFs and inspect retrieved source chunks.</p>
        </div>
      </div>

      {workspaceSelectedItem && workspaceSelectedItem.status !== "indexed" && (
        <p className="empty-state">
          Selected PDF is not indexed yet. Agent Chat is using Global RAG.
        </p>
      )}

      <form className="form-grid" onSubmit={submitQuery}>
        <div className="field-group full-width">
          <span className="field-label">Context</span>
          <div className="context-selector">
            <div className="context-selector-header">
              <div>
                <strong>{scopeDisplayLabel(activeScope, selectedLibraryItems)}</strong>
                <span>{contextHelp(selectedLibraryItems)}</span>
              </div>
              <button
                type="button"
                className="secondary-button"
                disabled={loading || selectedLibraryItemIds.length === 0}
                onClick={() => {
                  setSelectedLibraryItemIds([]);
                  setResult(null);
                  setError(null);
                  setLastQuestion("");
                  clearNoteDraft();
                }}
              >
                Global RAG
              </button>
            </div>
            <div className="context-book-list">
              {libraryItems.length === 0 ? (
                <p className="empty-state">
                  {loadingContexts
                    ? "Loading indexed PDF Library items..."
                    : "No indexed PDF Library items are available."}
                </p>
              ) : (
                libraryItems.map((item) => (
                  <label key={item.id} className="context-book-option">
                    <input
                      type="checkbox"
                      checked={selectedLibraryItemIds.includes(item.id)}
                      disabled={loading}
                      onChange={() => toggleLibraryItem(item.id)}
                    />
                    <span>
                      <strong>{item.title}</strong>
                      <small>
                        {item.author ? `${item.author} · ` : ""}
                        status {item.status} · type {item.file_type || "unknown"}
                      </small>
                    </span>
                  </label>
                ))
              )}
            </div>
            <button
              type="button"
              className="secondary-button"
              disabled={loading || loadingContexts}
              onClick={loadLibraryContexts}
            >
              {loadingContexts ? "Loading..." : "Reload PDFs"}
            </button>
          </div>
        </div>

        <label className="full-width">
          Question
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={4}
            placeholder="Ask a question about indexed PDFs..."
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
          {loading ? "Asking agent..." : "Submit query"}
        </button>
      </form>

      {contextError && <p className="error">{contextError}</p>}
      {error && <p className="error">{error}</p>}

      {result && (
        <div className="response-block">
          <h3>Answer</h3>
          <div className="scope-summary">
            <strong>{scopeDisplayLabel(result.scope_type, result.selected_library_items)}</strong>
            {result.scope_type === "multi_book" && result.selected_library_items.length > 0 && (
              <div className="scope-chip-row">
                {compactSelectedTitles(result.selected_library_items).map((title) => (
                  <span key={title} className="tag-badge">
                    {title}
                  </span>
                ))}
              </div>
            )}
          </div>
          {result.scope_type === "single_book" && result.selected_library_items[0] && (
            <div className="result-block">
              <h3>Selected Book</h3>
              <p>
                {result.selected_library_items[0].title}
                {result.selected_library_items[0].author
                  ? ` by ${result.selected_library_items[0].author}`
                  : ""}
              </p>
              <small>
                status {result.selected_library_items[0].status} · type{" "}
                {result.selected_library_items[0].file_type || "unknown"}
              </small>
            </div>
          )}
          {result.scope_type === "multi_book" && result.selected_library_items.length > 0 && (
            <div className="result-block">
              <h3>Selected Books</h3>
              <ul className="plain-list">
                {result.selected_library_items.map((item) => (
                  <li key={item.id}>
                    {item.title}
                    {item.author ? ` by ${item.author}` : ""}
                    <small>
                      {" "}
                      status {item.status} · type {item.file_type || "unknown"}
                    </small>
                  </li>
                ))}
              </ul>
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

          <div className="result-block">
            <div className="panel-heading compact-heading">
              <div>
                <h3>Create LaTeX Note</h3>
                <p>
                  Generate a deterministic draft from this answer, review it, then save it to
                  Notes.
                </p>
              </div>
              <button type="button" disabled={generatingNote} onClick={generateNoteDraft}>
                {generatingNote ? "Generating..." : "Create LaTeX Note"}
              </button>
            </div>

            {noteError && <p className="error compact-error">{noteError}</p>}
            {noteSuccess && <p className="success">{noteSuccess}</p>}

            {noteDraft && (
              <div className="chat-note-draft">
                <label>
                  title
                  <input
                    value={noteDraft.title}
                    onChange={(event) =>
                      setNoteDraft({ ...noteDraft, title: event.target.value })
                    }
                  />
                </label>
                <label>
                  description
                  <input
                    value={noteDraft.description || ""}
                    onChange={(event) =>
                      setNoteDraft({ ...noteDraft, description: event.target.value })
                    }
                  />
                </label>
                <label className="full-width">
                  content_latex
                  <textarea
                    className="latex-textarea"
                    rows={14}
                    value={noteDraft.content_latex}
                    onChange={(event) =>
                      setNoteDraft({ ...noteDraft, content_latex: event.target.value })
                    }
                  />
                </label>
                <p className="muted compact-note">
                  {noteDraft.library_item_id
                    ? `Will save with library_item_id ${noteDraft.library_item_id}.`
                    : "Will save without an associated book."}
                  {noteDraft.source_session_id
                    ? ` Source session: ${noteDraft.source_session_id}.`
                    : ""}
                </p>
                <div className="button-row full-width">
                  <button type="button" disabled={savingNote} onClick={saveNoteDraft}>
                    {savingNote ? "Saving..." : "Save note"}
                  </button>
                  <button type="button" className="secondary-button" onClick={clearNoteDraft}>
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="result-block">
            <h3>Sources</h3>
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
                      <span>score {citation.score.toFixed(4)}</span>
                    </div>
                    <small className="citation-meta">{citationMetadata(citation)}</small>
                    <p>{citation.excerpt || "No excerpt available."}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <h3>Retrieved Chunks</h3>
          {result.retrieved_chunks.length === 0 ? (
            <p className="empty-state">
              No relevant indexed chunks were retrieved for this question.
            </p>
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
                    {chunk.citation.library_title ? `${chunk.citation.library_title} · ` : ""}
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

function sourceTitle(citation: RagCitation): string {
  return (
    citation.library_title ||
    citation.document_title ||
    citation.document_source_path ||
    "Unknown source"
  );
}

function scopeDisplayLabel(scopeType: AgentChatScopeType, selectedItems: Pick<LibraryItem, "title">[]): string {
  if (scopeType === "global") {
    return "Global RAG";
  }
  if (scopeType === "single_book") {
    return `Single PDF: ${selectedItems[0]?.title || "selected PDF"}`;
  }
  return `Multi-PDF: ${selectedItems.length} selected PDFs`;
}

function contextHelp(selectedItems: LibraryItem[]): string {
  if (selectedItems.length === 0) {
    return "Queries use the global indexed knowledge base.";
  }
  if (selectedItems.length === 1) {
    return `PDF-scoped RAG: ${selectedItems[0].title}`;
  }
  return `Multi-PDF RAG: ${selectedItems.map((item) => item.title).join(", ")}`;
}

function compactSelectedTitles(selectedItems: Pick<LibraryItem, "title">[]): string[] {
  const titles = selectedItems.map((item) => item.title);
  if (titles.length <= 3) {
    return titles;
  }
  return [...titles.slice(0, 3), `+${titles.length - 3} more`];
}

function citationMetadata(citation: RagCitation): string {
  const parts = [
    citation.library_author ? `Author: ${citation.library_author}` : null,
    citation.document_title ? `Document: ${citation.document_title}` : null,
    citation.document_source_path ? `Path: ${citation.document_source_path}` : null,
    `Chunk: ${citation.chunk_index}`,
  ];
  return parts.filter(Boolean).join(" · ");
}

function scopeTypeForSelection(selectedIds: string[]): AgentChatScopeType {
  if (selectedIds.length === 0) {
    return "global";
  }
  if (selectedIds.length === 1) {
    return "single_book";
  }
  return "multi_book";
}

function formatAgentChatError(error: unknown): string {
  const message = error instanceof Error ? error.message : "";
  const normalized = message.toLowerCase();

  if (normalized.includes("network request failed")) {
    return "Backend unavailable. Make sure the FastAPI backend is running at http://127.0.0.1:8081.";
  }
  if (normalized.includes("scope_type")) {
    return "The selected chat scope is invalid. Reload the page and try again.";
  }
  if (
    normalized.includes("not been indexed") ||
    normalized.includes("no indexed chunks")
  ) {
    return "The selected book is not indexed or has no searchable chunks.";
  }
  if (normalized.includes("library_item_ids must not be empty")) {
    return "Select at least one indexed book for multi-book chat.";
  }
  if (normalized.includes("library item not found")) {
    return "One selected book could not be found. Reload the book list and try again.";
  }

  return message || "Agent chat request failed.";
}
