import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AgentStreamInterruptedError,
  queryAgentChatStream,
} from "./client";

const common = {
  request_id: "request-1",
  conversation_id: "conversation-1",
  run_id: "run-1",
  sequence: 1,
  timestamp: "2026-07-11T00:00:00Z",
};

function responseFrom(chunks: string[]): Response {
  const encoded = chunks.map((chunk) => new TextEncoder().encode(chunk));
  let index = 0;
  return {
    ok: true,
    status: 200,
    headers: new Headers({ "Content-Type": "text/event-stream" }),
    body: {
      getReader: () => ({
        read: async () =>
          index < encoded.length
            ? { done: false, value: encoded[index++] }
            : { done: true, value: undefined },
        releaseLock: vi.fn(),
      }),
    },
  } as unknown as Response;
}

describe("queryAgentChatStream", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("accepts a final terminal event without a trailing network chunk", async () => {
    const record = `event: done\ndata: ${JSON.stringify({
      ...common,
      type: "done",
    })}`;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responseFrom([record])));
    const events: string[] = [];
    await queryAgentChatStream(
      { message: "Question", selected_library_item_ids: [] },
      {
        signal: new AbortController().signal,
        onEvent: (event) => events.push(event.type),
      },
    );
    expect(events).toEqual(["done"]);
  });

  it("reports an unexpected disconnect before a terminal event", async () => {
    const record = `event: token\ndata: ${JSON.stringify({
      ...common,
      type: "token",
      delta: "partial",
    })}\n\n`;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responseFrom([record])));
    await expect(
      queryAgentChatStream(
        { message: "Question", selected_library_item_ids: [] },
        {
          signal: new AbortController().signal,
          onEvent: () => undefined,
        },
      ),
    ).rejects.toBeInstanceOf(AgentStreamInterruptedError);
  });
});
