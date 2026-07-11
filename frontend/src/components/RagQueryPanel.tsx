import { queryAgentChat, queryAgentChatStream } from "../api/client";
import type {
  AgentChatRequest,
  AgentChatResponse,
  LibraryItem,
  RagCitation,
  WebSource,
} from "../api/types";
import type {
  AgentRunState,
  AgentStreamEvent,
  CancelledEvent,
  ErrorEvent,
} from "../streaming/types";
import {
  assistantStatus,
  batchedTokenEvent,
  createAgentRunState,
  reduceAgentRun,
} from "../streaming/stateMachine";
import { useEffect, useRef, useState } from "react";
import type { Dispatch, FormEvent, SetStateAction, UIEvent } from "react";
import {
  ConversationState,
  createEmptyConversationState,
} from "../chat/conversationState";
import { ChatTurnMessage } from "./ChatTurnMessage";
import { FrontendLatencyTracker } from "../chat/latency";

export default function RagQueryPanel({
  conversation,
  onConversationChange,
  workspaceSelectedItems,
}: {
  conversation: ConversationState;
  onConversationChange: Dispatch<SetStateAction<ConversationState>>;
  workspaceSelectedItems: LibraryItem[];
}) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AgentChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<AgentRunState | null>(null);
  const scrollRegionRef = useRef<HTMLDivElement | null>(null);
  const shouldAutoScrollRef = useRef(true);
  const activeRunRef = useRef<AgentRunState | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const pendingTokensRef = useRef("");
  const tokenFlushTimerRef = useRef<number | null>(null);
  const flushIntervalRef = useRef(50);
  const runLockedRef = useRef(false);
  const latencyTrackerRef = useRef<FrontendLatencyTracker | null>(null);
  const loading =
    activeRun !== null &&
    !["completed", "cancelled", "failed"].includes(activeRun.status);
  const lastAnswerLength =
    conversation.messages[conversation.messages.length - 1]?.answer.length || 0;

  useEffect(() => {
    if (!shouldAutoScrollRef.current || !scrollRegionRef.current) {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      if (scrollRegionRef.current) {
        scrollRegionRef.current.scrollTop =
          scrollRegionRef.current.scrollHeight;
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [conversation.messages.length, lastAnswerLength, activeRun?.status]);

  useEffect(
    () => () => {
      controllerRef.current?.abort();
      if (tokenFlushTimerRef.current !== null) {
        window.clearTimeout(tokenFlushTimerRef.current);
      }
    },
    [],
  );

  function commitRunState(next: AgentRunState) {
    activeRunRef.current = next;
    setActiveRun(next);
    onConversationChange((current) => ({
      ...current,
      messages: current.messages.map((turn) =>
        turn.id === next.messageId
          ? {
              ...turn,
              answer: next.content,
              status: assistantStatus(next.status),
              citations: next.citations,
              webSources: next.webSources,
              activity: next.activity,
              serverMessageId: next.serverMessageId,
            }
          : turn,
      ),
    }));
  }

  function flushPendingTokens() {
    if (!pendingTokensRef.current || !activeRunRef.current) {
      return;
    }
    const delta = pendingTokensRef.current;
    const isFirstVisibleToken = activeRunRef.current.content.length === 0;
    pendingTokensRef.current = "";
    if (tokenFlushTimerRef.current !== null) {
      window.clearTimeout(tokenFlushTimerRef.current);
      tokenFlushTimerRef.current = null;
    }
    commitRunState(
      reduceAgentRun(activeRunRef.current, batchedTokenEvent(delta)),
    );
    if (isFirstVisibleToken) {
      window.requestAnimationFrame(() =>
        latencyTrackerRef.current?.recordFirstTokenRender(),
      );
    }
  }

  function handleStreamEvent(event: AgentStreamEvent) {
    latencyTrackerRef.current?.recordLastChunk();
    if (event.type === "status") {
      latencyTrackerRef.current?.recordFirstStatus();
      window.requestAnimationFrame(() =>
        latencyTrackerRef.current?.recordFirstActivityRender(),
      );
    } else if (event.type === "token") {
      latencyTrackerRef.current?.recordFirstToken();
    } else if (event.type === "done") {
      latencyTrackerRef.current?.recordDone();
    }
    if (event.type === "run_started") {
      flushIntervalRef.current = Math.max(
        30,
        Math.min(80, event.ui_flush_interval_ms),
      );
    }
    if (event.type === "token") {
      pendingTokensRef.current += event.delta;
      if (tokenFlushTimerRef.current === null) {
        tokenFlushTimerRef.current = window.setTimeout(
          flushPendingTokens,
          flushIntervalRef.current,
        );
      }
      return;
    }
    flushPendingTokens();
    if (!activeRunRef.current) return;
    const next = reduceAgentRun(activeRunRef.current, event);
    commitRunState(next);
    if (event.type === "final") {
      setResult(event.response);
      onConversationChange((current) => ({
        ...current,
        conversationId: event.response.conversation_id,
      }));
    } else if (event.type === "error") {
      setError(event.message);
    }
  }

  async function submitQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const submittedQuestion = question.trim();
    if (!submittedQuestion) {
      setError("Question is required.");
      return;
    }
    if (runLockedRef.current) return;
    runLockedRef.current = true;
    const latency = new FrontendLatencyTracker();
    latencyTrackerRef.current = latency;
    const payload = buildAgentChatRequest(
      conversation,
      workspaceSelectedItems,
      submittedQuestion,
    );
    const messageId = createClientMessageId();
    const initialRun = createAgentRunState(messageId);
    activeRunRef.current = initialRun;
    setActiveRun(initialRun);
    pendingTokensRef.current = "";
    setResult(null);
    setQuestion("");
    shouldAutoScrollRef.current = true;
    onConversationChange((current) => ({
      ...current,
      messages: [
        ...current.messages,
        {
          id: messageId,
          question: submittedQuestion,
          answer: "",
          status: "pending",
          activity: initialRun.activity,
        },
      ],
    }));
    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      await queryAgentChatStream(payload, {
        signal: controller.signal,
        onEvent: handleStreamEvent,
      });
      latency.recordCompleteResponse();
    } catch (err) {
      if (controller.signal.aborted) {
        flushPendingTokens();
        if (activeRunRef.current) {
          commitRunState(
            reduceAgentRun(activeRunRef.current, clientCancelledEvent()),
          );
        }
      } else if (isStreamingDisabledError(err)) {
        try {
          await completeWithNonStreamingFallback(payload, controller.signal);
        } catch (fallbackError) {
          if (controller.signal.aborted) {
            flushPendingTokens();
            if (activeRunRef.current) {
              commitRunState(
                reduceAgentRun(activeRunRef.current, clientCancelledEvent()),
              );
            }
          } else {
            failActiveRun(fallbackError);
          }
        }
      } else if (activeRunRef.current?.status !== "failed") {
        failActiveRun(err);
      }
    } finally {
      flushPendingTokens();
      controllerRef.current = null;
      runLockedRef.current = false;
      window.requestAnimationFrame(() => {
        const summary = latency.recordRenderComplete();
        if (import.meta.env.DEV) {
          console.debug("Agent frontend latency", summary);
        }
        if (latencyTrackerRef.current === latency) {
          latencyTrackerRef.current = null;
        }
      });
    }
  }

  async function completeWithNonStreamingFallback(
    payload: AgentChatRequest,
    signal: AbortSignal,
  ) {
    const response = await queryAgentChat(payload, signal);
    if (!activeRunRef.current) return;
    const next: AgentRunState = {
      ...activeRunRef.current,
      status: "completed",
      content: response.answer,
      citations: response.citations,
      webSources: response.web_sources || [],
      finalResponse: response,
      activity: { steps: [], compact: true },
    };
    commitRunState(next);
    setResult(response);
    onConversationChange((current) => ({
      ...current,
      conversationId: response.conversation_id,
    }));
  }

  function failActiveRun(reason: unknown) {
    const message = formatAgentChatError(reason);
    setResult(null);
    setError(message);
    if (activeRunRef.current) {
      commitRunState(
        reduceAgentRun(activeRunRef.current, clientErrorEvent(message)),
      );
    }
  }

  function stopGeneration() {
    if (!loading || activeRunRef.current?.status === "persisting") return;
    controllerRef.current?.abort();
  }

  function startNewChat() {
    onConversationChange(createEmptyConversationState());
    activeRunRef.current = null;
    setActiveRun(null);
    setQuestion("");
    setResult(null);
    setError(null);
    shouldAutoScrollRef.current = true;
  }

  function handleScroll(event: UIEvent<HTMLDivElement>) {
    const element = event.currentTarget;
    const distanceFromBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom < 80;
  }

  return (
    <section className="panel agent-chat-panel">
      <div className="panel-heading">
        <div>
          <h2>Agent Chat</h2>
          <p>{activeContextLabel(workspaceSelectedItems)}</p>
        </div>
        <button
          type="button"
          className="secondary-button compact-button"
          disabled={loading}
          onClick={startNewChat}
        >
          New Chat
        </button>
      </div>

      <div
        className="chat-scroll-region"
        ref={scrollRegionRef}
        onScroll={handleScroll}
      >
        {workspaceSelectedItems.some((item) => item.status !== "indexed") && (
          <p className="empty-state">
            Unindexed PDFs remain selected visually but are excluded from the
            next request.
          </p>
        )}

        <div
          className={
            conversation.messages.length === 0 && !loading
              ? "chat-thread empty-chat-thread"
              : "chat-thread"
          }
          aria-live="polite"
        >
          {conversation.messages.length === 0 && !loading ? (
            <p className="empty-state">
              Ask a question about the selected PDFs.
            </p>
          ) : (
            <>
              {conversation.messages.map((turn) => (
                <ChatTurnMessage turn={turn} key={turn.id} />
              ))}
            </>
          )}
        </div>

        {error && <p className="error">{error}</p>}

        {result && <AgentResultDetails result={result} />}
      </div>

      <form className="chat-compose" onSubmit={submitQuery}>
        <label>
          <span className="sr-only">Message</span>
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={3}
            placeholder="Ask about the selected PDFs..."
          />
        </label>
        <button
          type={loading ? "button" : "submit"}
          disabled={activeRun?.status === "persisting"}
          onClick={loading ? stopGeneration : undefined}
        >
          {activeRun?.status === "persisting"
            ? "正在保存..."
            : loading
              ? "停止生成"
              : "Send"}
        </button>
      </form>
    </section>
  );
}

export function buildAgentChatRequest(
  conversation: ConversationState,
  selectedItems: LibraryItem[],
  message: string,
): AgentChatRequest {
  const selectedLibraryItemIds = [
    ...new Set(
      selectedItems
        .filter((item) => item.status === "indexed")
        .map((item) => item.id),
    ),
  ];
  return {
    message,
    ...(conversation.conversationId
      ? { conversation_id: conversation.conversationId }
      : {}),
    selected_library_item_ids: selectedLibraryItemIds,
  };
}

function AgentResultDetails({ result }: { result: AgentChatResponse }) {
  return (
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
                <small className="citation-meta">
                  {citationMetadata(citation)}
                </small>
                <p>{citation.excerpt || "No excerpt available."}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="result-block">
        <h3>Web Sources</h3>
        {!result.web_sources || result.web_sources.length === 0 ? (
          <p className="empty-state">
            No web sources were returned for this answer.
          </p>
        ) : (
          <ul className="citation-list">
            {result.web_sources.map((source) => (
              <li key={source.source_id}>
                <div className="item-title">
                  <span>
                    [{source.source_id}] {source.title}
                  </span>
                </div>
                <small className="citation-meta">
                  {webSourceMetadata(source)}
                </small>
                <p>{source.excerpt || "No summary available."}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
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

function sourceTitle(citation: RagCitation): string {
  return (
    citation.library_title ||
    citation.document_title ||
    citation.document_source_path ||
    "Unknown source"
  );
}

function activeContextLabel(items: LibraryItem[]): string {
  if (items.length === 0) {
    return "Ask a question. Selecting PDFs adds book context to this conversation.";
  }
  const indexedCount = items.filter((item) => item.status === "indexed").length;
  if (indexedCount !== items.length) {
    return `${items.length} PDFs selected; ${indexedCount} indexed and ready.`;
  }
  return `Using ${items.length} selected PDF${items.length === 1 ? "" : "s"}`;
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

function isStreamingDisabledError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    error.status === 409 &&
    "message" in error &&
    typeof error.message === "string" &&
    error.message.toLowerCase().includes("streaming is disabled")
  );
}

function createClientMessageId(): string {
  return (
    globalThis.crypto?.randomUUID?.() ||
    `pending-${Date.now()}-${Math.random().toString(16).slice(2)}`
  );
}

function clientCancelledEvent(): CancelledEvent {
  return {
    type: "cancelled",
    request_id: "client",
    conversation_id: "client",
    run_id: "client",
    sequence: 0,
    timestamp: new Date().toISOString(),
    partial_output_preserved: true,
  };
}

function clientErrorEvent(message: string): ErrorEvent {
  return {
    type: "error",
    request_id: "client",
    conversation_id: "client",
    run_id: "client",
    sequence: 0,
    timestamp: new Date().toISOString(),
    code: "stream_interrupted",
    message,
    recoverable: true,
    partial_output_preserved: true,
  };
}
