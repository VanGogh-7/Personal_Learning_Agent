import type { AgentStreamEvent } from "./types";

const KNOWN_EVENT_TYPES = new Set([
  "run_started",
  "status",
  "route_selected",
  "retrieval_completed",
  "token",
  "citations",
  "warning",
  "final",
  "done",
  "cancelled",
  "error",
]);
const ACTIVITY_STAGES = new Set([
  "loading_context",
  "retrieving_memory",
  "routing",
  "understanding_query",
  "planning_research",
  "retrieving_local",
  "planning_web",
  "searching_web",
  "searching_academic",
  "reading_pages",
  "filtering_sources",
  "evaluating_sources",
  "correcting_retrieval",
  "organizing_answer",
  "verifying_citations",
  "processing_sources",
  "synthesizing",
  "streaming",
  "persisting",
]);

export class SSEParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SSEParseError";
  }
}

export class AgentSSEParser {
  private buffer = "";
  private eventName = "message";
  private dataLines: string[] = [];
  private lastSequence = 0;

  constructor(private readonly onEvent: (event: AgentStreamEvent) => void) {}

  feed(text: string): void {
    this.buffer += text;
    let newline = this.buffer.indexOf("\n");
    while (newline >= 0) {
      const rawLine = this.buffer.slice(0, newline);
      this.buffer = this.buffer.slice(newline + 1);
      this.processLine(rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine);
      newline = this.buffer.indexOf("\n");
    }
  }

  finish(): void {
    if (this.buffer) {
      this.processLine(
        this.buffer.endsWith("\r") ? this.buffer.slice(0, -1) : this.buffer,
      );
      this.buffer = "";
    }
    this.dispatch();
  }

  private processLine(line: string): void {
    if (line === "") {
      this.dispatch();
      return;
    }
    if (line.startsWith(":")) {
      return;
    }
    const separator = line.indexOf(":");
    const field = separator >= 0 ? line.slice(0, separator) : line;
    let value = separator >= 0 ? line.slice(separator + 1) : "";
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }
    if (field === "event") {
      this.eventName = value;
    } else if (field === "data") {
      this.dataLines.push(value);
    }
  }

  private dispatch(): void {
    if (this.dataLines.length === 0) {
      this.eventName = "message";
      return;
    }
    const eventName = this.eventName;
    const data = this.dataLines.join("\n");
    this.eventName = "message";
    this.dataLines = [];
    if (!KNOWN_EVENT_TYPES.has(eventName)) {
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(data);
    } catch {
      throw new SSEParseError(`Invalid JSON in ${eventName} event.`);
    }
    if (!isStreamEvent(parsed) || parsed.type !== eventName) {
      throw new SSEParseError(`Invalid ${eventName} event payload.`);
    }
    if (parsed.sequence <= this.lastSequence) {
      throw new SSEParseError("Agent stream event sequence is not increasing.");
    }
    this.lastSequence = parsed.sequence;
    this.onEvent(parsed);
  }
}

function isStreamEvent(value: unknown): value is AgentStreamEvent {
  if (!value || typeof value !== "object") {
    return false;
  }
  const event = value as Partial<AgentStreamEvent>;
  return (
    typeof event.type === "string" &&
    KNOWN_EVENT_TYPES.has(event.type) &&
    typeof event.request_id === "string" &&
    typeof event.conversation_id === "string" &&
    typeof event.run_id === "string" &&
    typeof event.sequence === "number" &&
    Number.isInteger(event.sequence) &&
    event.sequence > 0 &&
    typeof event.timestamp === "string" &&
    hasValidEventFields(value as Record<string, unknown>)
  );
}

function hasValidEventFields(event: Record<string, unknown>): boolean {
  switch (event.type) {
    case "run_started":
      return typeof event.ui_flush_interval_ms === "number";
    case "status":
      return (
        typeof event.stage === "string" &&
        ACTIVITY_STAGES.has(event.stage) &&
        typeof event.message === "string"
      );
    case "route_selected":
      return ["local_only", "web_only", "both"].includes(String(event.route));
    case "retrieval_completed":
      return (
        ["local", "web", "academic"].includes(String(event.source)) &&
        typeof event.result_count === "number"
      );
    case "token":
      return typeof event.delta === "string";
    case "citations":
      return Array.isArray(event.citations) && Array.isArray(event.web_sources);
    case "warning":
      return typeof event.message === "string";
    case "final":
      return (
        typeof event.message_id === "string" &&
        typeof event.response === "object" &&
        event.response !== null
      );
    case "done":
      return true;
    case "cancelled":
      return typeof event.partial_output_preserved === "boolean";
    case "error":
      return (
        typeof event.code === "string" &&
        typeof event.message === "string" &&
        typeof event.recoverable === "boolean" &&
        typeof event.partial_output_preserved === "boolean"
      );
    default:
      return false;
  }
}
