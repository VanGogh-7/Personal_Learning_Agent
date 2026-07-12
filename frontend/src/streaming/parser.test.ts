import { describe, expect, it } from "vitest";
import { AgentSSEParser, SSEParseError } from "./parser";
import type { AgentStreamEvent } from "./types";

const base = {
  request_id: "request-1",
  conversation_id: "conversation-1",
  run_id: "run-1",
  timestamp: "2026-07-11T00:00:00Z",
};

function record(type: string, payload: object): string {
  return `event: ${type}\ndata: ${JSON.stringify(payload)}\n\n`;
}

describe("AgentSSEParser", () => {
  it("reassembles split events and multiple events in one chunk", () => {
    const seen: AgentStreamEvent[] = [];
    const parser = new AgentSSEParser((event) => seen.push(event));
    const stream =
      record("status", {
        ...base,
        type: "status",
        sequence: 1,
        stage: "routing",
        message: "正在分析问题",
      }) +
      record("token", {
        ...base,
        type: "token",
        sequence: 2,
        delta: "闭图像",
      });
    parser.feed(stream.slice(0, 17));
    parser.feed(stream.slice(17));
    parser.finish();
    expect(seen.map((event) => event.type)).toEqual(["status", "token"]);
  });

  it("accepts public MCP research activity without exposing tool details", () => {
    const seen: AgentStreamEvent[] = [];
    const parser = new AgentSSEParser((event) => seen.push(event));
    parser.feed(
      record("status", {
        ...base,
        type: "status",
        sequence: 1,
        stage: "searching_academic",
        message: "正在搜索学术资料",
      }),
    );
    expect(seen[0]).toMatchObject({
      type: "status",
      stage: "searching_academic",
    });
  });

  it("accepts every adaptive activity stage and academic retrieval", () => {
    const seen: AgentStreamEvent[] = [];
    const parser = new AgentSSEParser((event) => seen.push(event));
    const stages = [
      "understanding_query",
      "planning_research",
      "evaluating_sources",
      "correcting_retrieval",
      "organizing_answer",
      "verifying_citations",
    ];
    stages.forEach((stage, index) =>
      parser.feed(
        record("status", {
          ...base,
          type: "status",
          sequence: index + 1,
          stage,
          message: stage,
        }),
      ),
    );
    parser.feed(
      record("retrieval_completed", {
        ...base,
        type: "retrieval_completed",
        sequence: stages.length + 1,
        source: "academic",
        result_count: 2,
      }),
    );

    expect(seen.map((event) => event.type)).toEqual([
      ...stages.map(() => "status"),
      "retrieval_completed",
    ]);
    expect(seen[seen.length - 1]).toMatchObject({
      source: "academic",
      result_count: 2,
    });
  });

  it("preserves Unicode split across byte chunks and ignores heartbeats", () => {
    const seen: AgentStreamEvent[] = [];
    const parser = new AgentSSEParser((event) => seen.push(event));
    const bytes = new TextEncoder().encode(
      `: ping\n\n${record("token", {
        ...base,
        type: "token",
        sequence: 1,
        delta: "定理",
      })}`,
    );
    const split = bytes.indexOf(0xe5) + 1;
    const decoder = new TextDecoder();
    parser.feed(decoder.decode(bytes.slice(0, split), { stream: true }));
    parser.feed(decoder.decode(bytes.slice(split), { stream: true }));
    parser.feed(decoder.decode());
    parser.finish();
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ type: "token", delta: "定理" });
  });

  it("ignores unknown events and flushes a final event without a blank line", () => {
    const seen: AgentStreamEvent[] = [];
    const parser = new AgentSSEParser((event) => seen.push(event));
    parser.feed("event: future_event\ndata: {}\n\n");
    parser.feed(
      record("done", { ...base, type: "done", sequence: 1 }).trimEnd(),
    );
    parser.finish();
    expect(seen.map((event) => event.type)).toEqual(["done"]);
  });

  it("reports invalid JSON without crashing unrelated application state", () => {
    const parser = new AgentSSEParser(() => undefined);
    expect(() => parser.feed("event: token\ndata: {broken}\n\n")).toThrow(
      SSEParseError,
    );
  });

  it("rejects malformed known events and non-increasing sequences", () => {
    const malformed = new AgentSSEParser(() => undefined);
    expect(() =>
      malformed.feed(
        record("status", { ...base, type: "status", sequence: 1 }),
      ),
    ).toThrow(SSEParseError);

    const repeated = new AgentSSEParser(() => undefined);
    repeated.feed(record("done", { ...base, type: "done", sequence: 2 }));
    expect(() =>
      repeated.feed(record("done", { ...base, type: "done", sequence: 2 })),
    ).toThrow(SSEParseError);
  });
});
