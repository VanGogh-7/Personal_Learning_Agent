import type {
  AgentActivityStage,
  AgentRunState,
  AgentStreamEvent,
  AssistantMessageStatus,
  TokenEvent,
} from "./types";

export function createAgentRunState(messageId: string): AgentRunState {
  return {
    messageId,
    status: "idle",
    content: "",
    activity: { steps: [], compact: false },
    citations: [],
    webSources: [],
    route: null,
    finalResponse: null,
    serverMessageId: null,
    error: null,
    warnings: [],
  };
}

export function reduceAgentRun(
  state: AgentRunState,
  event: AgentStreamEvent,
): AgentRunState {
  if (event.type === "run_started") {
    return state;
  }
  if (event.type === "status") {
    return {
      ...state,
      status: event.stage,
      activity: {
        compact: event.stage === "streaming" || state.activity.compact,
        steps: activateStep(state.activity.steps, event.stage, event.message),
      },
    };
  }
  if (event.type === "route_selected") {
    return { ...state, route: event.route };
  }
  if (event.type === "retrieval_completed") {
    const stage =
      event.source === "local"
        ? "retrieving_local"
        : event.source === "academic"
          ? "searching_academic"
          : "filtering_sources";
    const label =
      event.source === "local"
        ? `Searched selected books and found ${event.result_count} relevant chunks`
        : event.source === "academic"
          ? `Searched academic sources and found ${event.result_count} results`
          : `Searched the web and found ${event.result_count} results`;
    return {
      ...state,
      activity: {
        ...state.activity,
        steps: state.activity.steps.map((step) =>
          step.stage === stage ||
          (event.source !== "local" &&
            [
              "planning_web",
              "searching_web",
              "searching_academic",
              "reading_pages",
            ].includes(step.stage))
            ? {
                ...step,
                message: label,
                resultCount: event.result_count,
                status: "completed" as const,
              }
            : step,
        ),
      },
    };
  }
  if (event.type === "token") {
    return {
      ...state,
      status: "streaming",
      content: state.content + event.delta,
      activity: { ...state.activity, compact: true },
    };
  }
  if (event.type === "citations") {
    return {
      ...state,
      citations: event.citations,
      webSources: event.web_sources,
    };
  }
  if (event.type === "warning") {
    return { ...state, warnings: [...state.warnings, event.message] };
  }
  if (event.type === "final") {
    return {
      ...state,
      status: "persisting",
      content: event.response.answer,
      citations: event.response.citations,
      webSources: event.response.web_sources || [],
      finalResponse: event.response,
      serverMessageId: event.message_id,
    };
  }
  if (event.type === "done") {
    return {
      ...state,
      status: "completed",
      activity: {
        compact: true,
        steps: state.activity.steps.map((step) => ({
          ...step,
          status: "completed" as const,
        })),
      },
    };
  }
  if (event.type === "cancelled") {
    return terminalState(state, "cancelled", null);
  }
  if (event.type === "error") {
    return terminalState(state, "failed", event.message);
  }
  return state;
}

export function batchedTokenEvent(delta: string): TokenEvent {
  return {
    type: "token",
    delta,
    request_id: "client-batch",
    conversation_id: "client-batch",
    run_id: "client-batch",
    sequence: 0,
    timestamp: new Date().toISOString(),
  };
}

export function assistantStatus(
  status: AgentRunState["status"],
): AssistantMessageStatus {
  if (status === "completed") return "completed";
  if (status === "cancelled") return "cancelled";
  if (status === "failed") return "failed";
  if (status === "persisting") return "persisting";
  if (status === "streaming") return "streaming";
  return "pending";
}

function activateStep(
  steps: AgentRunState["activity"]["steps"],
  stage: AgentActivityStage,
  message: string,
) {
  const stageBranch = retrievalBranch(stage);
  const updated = steps.map((step) => {
    if (step.stage === stage) {
      return { ...step, message, status: "active" as const };
    }
    if (
      step.status === "active" &&
      (!stageBranch ||
        retrievalBranch(step.stage) === stageBranch ||
        !retrievalBranch(step.stage))
    ) {
      return { ...step, status: "completed" as const };
    }
    return step;
  });
  if (!updated.some((step) => step.stage === stage)) {
    updated.push({ stage, message, status: "active" });
  }
  return updated;
}

function retrievalBranch(stage: AgentActivityStage): "local" | "web" | null {
  if (stage === "retrieving_local") return "local";
  if (
    [
      "planning_web",
      "searching_web",
      "searching_academic",
      "reading_pages",
      "filtering_sources",
      "evaluating_sources",
      "correcting_retrieval",
    ].includes(stage)
  ) {
    return "web";
  }
  return null;
}

function terminalState(
  state: AgentRunState,
  status: "cancelled" | "failed",
  error: string | null,
): AgentRunState {
  return {
    ...state,
    status,
    error,
    citations: [],
    webSources: [],
    activity: {
      ...state.activity,
      steps: state.activity.steps.map((step) =>
        step.status === "active" ? { ...step, status } : step,
      ),
    },
  };
}
