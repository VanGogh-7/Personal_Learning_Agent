import type {
  AgentChatResponse,
  AgentChatRoute,
  RagCitation,
  WebSource,
} from "../api/types";

export type AgentActivityStage =
  | "loading_context"
  | "retrieving_memory"
  | "routing"
  | "understanding_query"
  | "planning_research"
  | "responding_directly"
  | "retrieving_local"
  | "planning_web"
  | "searching_web"
  | "searching_academic"
  | "reading_pages"
  | "filtering_sources"
  | "evaluating_sources"
  | "correcting_retrieval"
  | "organizing_answer"
  | "verifying_citations"
  | "processing_sources"
  | "synthesizing"
  | "streaming"
  | "persisting";

export type AgentRunStatus =
  "idle" | AgentActivityStage | "completed" | "cancelled" | "failed";

export type AssistantMessageStatus =
  "pending" | "streaming" | "persisting" | "completed" | "cancelled" | "failed";

export type ActivityStepStatus =
  "pending" | "active" | "completed" | "failed" | "cancelled";

export interface AgentActivityStep {
  stage: AgentActivityStage;
  message: string;
  status: ActivityStepStatus;
  resultCount?: number;
}

export interface AgentActivityState {
  steps: AgentActivityStep[];
  compact: boolean;
}

interface StreamEventBase {
  type: string;
  request_id: string;
  conversation_id: string;
  run_id: string;
  sequence: number;
  timestamp: string;
}

export interface RunStartedEvent extends StreamEventBase {
  type: "run_started";
  ui_flush_interval_ms: number;
}

export interface StatusEvent extends StreamEventBase {
  type: "status";
  stage: AgentActivityStage;
  message: string;
}

export interface RouteSelectedEvent extends StreamEventBase {
  type: "route_selected";
  route: AgentChatRoute;
}

export interface RetrievalCompletedEvent extends StreamEventBase {
  type: "retrieval_completed";
  source: "local" | "web" | "academic";
  result_count: number;
}

export interface TokenEvent extends StreamEventBase {
  type: "token";
  delta: string;
}

export interface CitationsEvent extends StreamEventBase {
  type: "citations";
  citations: RagCitation[];
  web_sources: WebSource[];
}

export interface WarningEvent extends StreamEventBase {
  type: "warning";
  message: string;
}

export interface FinalEvent extends StreamEventBase {
  type: "final";
  message_id: string;
  response: AgentChatResponse;
}

export interface DoneEvent extends StreamEventBase {
  type: "done";
}

export interface CancelledEvent extends StreamEventBase {
  type: "cancelled";
  partial_output_preserved: boolean;
}

export interface ErrorEvent extends StreamEventBase {
  type: "error";
  code: string;
  message: string;
  recoverable: boolean;
  partial_output_preserved: boolean;
}

export type AgentStreamEvent =
  | RunStartedEvent
  | StatusEvent
  | RouteSelectedEvent
  | RetrievalCompletedEvent
  | TokenEvent
  | CitationsEvent
  | WarningEvent
  | FinalEvent
  | DoneEvent
  | CancelledEvent
  | ErrorEvent;

export interface AgentRunState {
  messageId: string;
  status: AgentRunStatus;
  content: string;
  activity: AgentActivityState;
  citations: RagCitation[];
  webSources: WebSource[];
  route: AgentChatRoute | null;
  finalResponse: AgentChatResponse | null;
  serverMessageId: string | null;
  error: string | null;
  warnings: string[];
}
