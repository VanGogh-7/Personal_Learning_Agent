import { queryAgentChat, queryAgentChatStream } from "../api/client";
import type { AgentChatRequest, LibraryItem } from "../api/types";
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
import ChatHeader from "./ChatHeader";
import ContextPanel, { type ContextPanelTab } from "./ContextPanel";
import type { ChatTurn } from "../chat/conversationState";

export default function RagQueryPanel({
  conversation,
  onConversationChange,
  workspaceSelectedItems,
  libraryItems = workspaceSelectedItems,
  conversationTitle = "New conversation",
  currentModel = "Configured Agent model",
  sidebarCollapsed = false,
  onNewChat,
  onOpenSidebar = () => undefined,
}: {
  conversation: ConversationState;
  onConversationChange: Dispatch<SetStateAction<ConversationState>>;
  workspaceSelectedItems: LibraryItem[];
  libraryItems?: LibraryItem[];
  conversationTitle?: string;
  currentModel?: string;
  sidebarCollapsed?: boolean;
  onNewChat?: () => void;
  onOpenSidebar?: () => void;
}) {
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<AgentRunState | null>(null);
  const [contextOpen, setContextOpen] = useState(false);
  const [contextTab, setContextTab] = useState<ContextPanelTab>("sources");
  const [contextTurn, setContextTurn] = useState<ChatTurn | null>(null);
  const [highlightedCitationId, setHighlightedCitationId] = useState<
    string | null
  >(null);
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
    onConversationChange((current) => ({
      ...current,
      conversationId: response.conversation_id,
    }));
  }

  function failActiveRun(reason: unknown) {
    const message = formatAgentChatError(reason);
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
    if (onNewChat) onNewChat();
    else onConversationChange(createEmptyConversationState());
    activeRunRef.current = null;
    setActiveRun(null);
    setQuestion("");
    setError(null);
    shouldAutoScrollRef.current = true;
  }

  function openSources(turn: ChatTurn, citationId?: string) {
    setContextTurn(turn);
    setHighlightedCitationId(citationId || null);
    setContextTab("sources");
    setContextOpen(true);
  }

  function openActivity(turn: ChatTurn) {
    setContextTurn(turn);
    setContextTab("activity");
    setContextOpen(true);
  }

  function handleScroll(event: UIEvent<HTMLDivElement>) {
    const element = event.currentTarget;
    const distanceFromBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom < 80;
  }

  const latestTurn =
    conversation.messages[conversation.messages.length - 1] || null;
  const statusLabel = loading ? "Agent working" : "Ready";

  return (
    <section className={`agent-workspace${contextOpen ? " context-open" : ""}`}>
      <main className="agent-chat-panel">
        <ChatHeader
          title={conversationTitle}
          status={statusLabel}
          selectedItems={workspaceSelectedItems}
          sidebarCollapsed={sidebarCollapsed}
          onOpenSidebar={onOpenSidebar}
          onNewChat={startNewChat}
          onToggleContext={() => {
            if (!contextOpen) {
              setContextTurn(contextTurn || latestTurn);
              setContextTab("context");
            }
            setContextOpen((value) => !value);
          }}
        />
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
              <EmptyChatState
                selectedItems={workspaceSelectedItems}
                onExample={setQuestion}
              />
            ) : (
              <>
                {conversation.messages.map((turn) => (
                  <ChatTurnMessage
                    turn={turn}
                    libraryItems={libraryItems}
                    onOpenSources={openSources}
                    onOpenActivity={openActivity}
                    key={turn.id}
                  />
                ))}
              </>
            )}
          </div>

          {error && <p className="error">{error}</p>}
        </div>

        <form className="chat-compose" onSubmit={submitQuery}>
          {workspaceSelectedItems.length > 0 && (
            <div className="composer-context-summary">
              Using {workspaceSelectedItems.length} selected book
              {workspaceSelectedItems.length === 1 ? "" : "s"}
            </div>
          )}
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
              ? "Saving..."
              : loading
                ? "Stop generating"
                : "Send"}
          </button>
        </form>
      </main>
      <ContextPanel
        open={contextOpen}
        tab={contextTab}
        turn={contextTurn || latestTurn}
        selectedItems={libraryItems.filter((item) =>
          conversation.selectedLibraryItemIds.includes(item.id),
        )}
        conversationId={conversation.conversationId}
        conversationTitle={conversationTitle}
        currentModel={currentModel}
        highlightedCitationId={highlightedCitationId}
        onTabChange={setContextTab}
        onClose={() => setContextOpen(false)}
      />
    </section>
  );
}

function EmptyChatState({
  selectedItems,
  onExample,
}: {
  selectedItems: LibraryItem[];
  onExample: (value: string) => void;
}) {
  const examples = [
    "Explain the main theorem and its assumptions.",
    "Compare the definitions used across these books.",
    "Create a proof outline for this result.",
  ];
  return (
    <section className="empty-chat-state">
      <p className="eyebrow">Personal Learning Agent</p>
      <h2>Begin a focused research conversation</h2>
      <p>Ask a question about the selected PDFs.</p>
      <p className="empty-chat-detail">
        You can also start with a broader mathematical question.
      </p>
      <div className="example-prompts">
        {examples.map((example) => (
          <button
            type="button"
            onClick={() => onExample(example)}
            key={example}
          >
            {example}
          </button>
        ))}
      </div>
      <small>
        {selectedItems.length
          ? `${selectedItems.length} selected book${selectedItems.length === 1 ? "" : "s"} will be used as context.`
          : "No books are selected yet."}
      </small>
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
