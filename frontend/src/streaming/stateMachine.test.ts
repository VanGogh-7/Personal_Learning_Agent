import { describe, expect, it } from "vitest";
import { createAgentRunState, reduceAgentRun } from "./stateMachine";
import type { AgentStreamEvent } from "./types";

const common = {
  request_id: "request-1",
  conversation_id: "conversation-1",
  run_id: "run-1",
  timestamp: "2026-07-11T00:00:00Z",
};

function event(value: object): AgentStreamEvent {
  return { ...common, sequence: 1, ...value } as AgentStreamEvent;
}

describe("Agent run state machine", () => {
  it("follows backend status events through streaming and completion", () => {
    let state = createAgentRunState("message-1");
    for (const value of [
      {
        type: "status",
        stage: "loading_context",
        message: "Loading conversation context",
      },
      {
        type: "status",
        stage: "understanding_query",
        message: "Understanding the question",
      },
      {
        type: "status",
        stage: "planning_research",
        message: "Understanding the question",
      },
      {
        type: "status",
        stage: "retrieving_local",
        message: "Searching selected books",
      },
      {
        type: "status",
        stage: "evaluating_sources",
        message: "Evaluating sources",
      },
      {
        type: "status",
        stage: "organizing_answer",
        message: "Generating answer",
      },
      {
        type: "status",
        stage: "synthesizing",
        message: "Generating answer",
      },
      { type: "token", delta: "answer" },
      {
        type: "status",
        stage: "verifying_citations",
        message: "Verifying citations",
      },
      { type: "status", stage: "persisting", message: "Saving answer" },
      { type: "done" },
    ]) {
      state = reduceAgentRun(state, event(value));
    }
    expect(state.status).toBe("completed");
    expect(state.content).toBe("answer");
    expect(state.activity.steps.map((step) => step.stage)).toEqual([
      "loading_context",
      "understanding_query",
      "planning_research",
      "retrieving_local",
      "evaluating_sources",
      "organizing_answer",
      "synthesizing",
      "verifying_citations",
      "persisting",
    ]);
  });

  it.each(["cancelled", "failed"] as const)(
    "preserves partial content when streaming becomes %s",
    (terminal) => {
      let state = createAgentRunState("message-1");
      state = reduceAgentRun(state, event({ type: "token", delta: "partial" }));
      state = reduceAgentRun(
        state,
        terminal === "cancelled"
          ? event({ type: "cancelled", partial_output_preserved: true })
          : event({
              type: "error",
              code: "provider_stream_failed",
              message: "failed",
              recoverable: true,
              partial_output_preserved: true,
            }),
      );
      expect(state.status).toBe(terminal);
      expect(state.content).toBe("partial");
    },
  );

  it("tracks local and web research as parallel public branches", () => {
    let state = createAgentRunState("message-1");
    for (const value of [
      {
        type: "status",
        stage: "retrieving_local",
        message: "Searching selected books",
      },
      {
        type: "status",
        stage: "planning_research",
        message: "Searching the web",
      },
      {
        type: "status",
        stage: "searching_academic",
        message: "Searching academic sources",
      },
    ]) {
      state = reduceAgentRun(state, event(value));
    }
    expect(state.activity.steps).toMatchObject([
      { stage: "retrieving_local", status: "completed" },
      { stage: "planning_research", status: "completed" },
      { stage: "searching_academic", status: "active" },
    ]);
  });
});
