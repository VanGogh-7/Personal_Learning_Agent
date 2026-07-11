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
      { type: "status", stage: "loading_context", message: "读取上下文" },
      { type: "status", stage: "routing", message: "分析问题" },
      { type: "status", stage: "retrieving_local", message: "检索书库" },
      { type: "status", stage: "processing_sources", message: "整合证据" },
      { type: "status", stage: "synthesizing", message: "生成回答" },
      { type: "token", delta: "answer" },
      { type: "status", stage: "persisting", message: "保存回答" },
      { type: "done" },
    ]) {
      state = reduceAgentRun(state, event(value));
    }
    expect(state.status).toBe("completed");
    expect(state.content).toBe("answer");
    expect(state.activity.steps.map((step) => step.stage)).toEqual([
      "loading_context",
      "routing",
      "retrieving_local",
      "processing_sources",
      "synthesizing",
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
});
