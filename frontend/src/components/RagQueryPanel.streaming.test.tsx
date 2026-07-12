import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentChatResponse } from "../api/types";
import { queryAgentChatStream } from "../api/client";
import {
  createEmptyConversationState,
  type ConversationState,
} from "../chat/conversationState";
import type { AgentStreamEvent } from "../streaming/types";
import RagQueryPanel from "./RagQueryPanel";

vi.mock("../api/client", () => ({
  queryAgentChat: vi.fn(),
  queryAgentChatStream: vi.fn(),
}));

const common = {
  request_id: "request-1",
  conversation_id: "conversation-1",
  run_id: "run-1",
  timestamp: "2026-07-11T00:00:00Z",
};

function streamEvent(value: object, sequence = 1): AgentStreamEvent {
  return { ...common, sequence, ...value } as AgentStreamEvent;
}

function response(answer: string): AgentChatResponse {
  return {
    conversation_id: "conversation-1",
    scope_type: "global",
    route: "local_only",
    selected_library_items: [],
    answer,
    retrieved_chunks: [],
    citations: [],
    total_retrieved: 0,
    memory: {
      used_recent_turns: 0,
      saved_current_turn: true,
      used_long_term_memories: 0,
    },
    web_sources: [],
    warnings: [],
    errors: [],
  };
}

const streamedCitation = {
  citation_id: "S1",
  chunk_id: "chunk-1",
  document_id: "document-1",
  library_item_id: null,
  library_title: "Analysis",
  library_author: null,
  document_title: "Analysis",
  document_source_path: null,
  chunk_index: 0,
  page_number: 3,
  page_start: 3,
  page_end: 3,
  score: 0.9,
  excerpt: "A complete metric space.",
  content: "A complete metric space.",
};

function Harness() {
  const [conversation, setConversation] = useState<ConversationState>(
    createEmptyConversationState(),
  );
  return (
    <RagQueryPanel
      conversation={conversation}
      onConversationChange={setConversation}
      workspaceSelectedItems={[]}
    />
  );
}

describe("Agent Chat streaming UI", () => {
  beforeEach(() => vi.clearAllMocks());

  it("creates one placeholder and shows only real route activity", async () => {
    let continueStream: (() => void) | undefined;
    const finalResponse = response("完整回答 [S1]");
    finalResponse.citations = [streamedCitation];
    vi.mocked(queryAgentChatStream).mockImplementation(
      async (_payload, { onEvent }) => {
        onEvent(
          streamEvent({ type: "run_started", ui_flush_interval_ms: 50 }, 1),
        );
        onEvent(
          streamEvent(
            {
              type: "status",
              stage: "loading_context",
              message: "正在读取会话上下文",
            },
            2,
          ),
        );
        onEvent(
          streamEvent(
            { type: "status", stage: "routing", message: "正在分析问题" },
            3,
          ),
        );
        onEvent(
          streamEvent(
            {
              type: "status",
              stage: "retrieving_local",
              message: "正在检索已选书籍",
            },
            4,
          ),
        );
        await new Promise<void>((resolve) => {
          continueStream = resolve;
        });
        onEvent(streamEvent({ type: "token", delta: "完整回答" }, 5));
        onEvent(
          streamEvent(
            {
              type: "status",
              stage: "persisting",
              message: "正在保存完整回答",
            },
            6,
          ),
        );
        onEvent(
          streamEvent(
            {
              type: "citations",
              citations: [streamedCitation],
              web_sources: [],
            },
            7,
          ),
        );
        onEvent(
          streamEvent(
            {
              type: "final",
              message_id: "message-server-1",
              response: finalResponse,
            },
            8,
          ),
        );
        onEvent(streamEvent({ type: "done" }, 9));
      },
    );
    const { container } = render(<Harness />);
    fireEvent.change(
      screen.getByPlaceholderText("Ask about the selected PDFs..."),
      {
        target: { value: "Question" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(screen.getAllByText("Question")).toHaveLength(1);
    expect(await screen.findByText("正在检索已选书籍")).toBeInTheDocument();
    expect(screen.queryByText("正在搜索网络资料")).not.toBeInTheDocument();
    expect(container.querySelectorAll(".assistant-message")).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "停止生成" }),
    ).toBeInTheDocument();

    await act(async () => continueStream?.());
    expect(await screen.findByText(/完整回答/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument(),
    );
    expect(
      container.querySelector(".assistant-message.completed"),
    ).not.toBeNull();
    expect(screen.queryByLabelText("Agent Activity")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^Sources/ }),
    ).toBeInTheDocument();
  });

  it("keeps partial text, marks cancellation, and unlocks the next turn", async () => {
    vi.mocked(queryAgentChatStream).mockImplementation(
      async (_payload, { signal, onEvent }) => {
        onEvent(
          streamEvent({ type: "run_started", ui_flush_interval_ms: 50 }, 1),
        );
        onEvent(streamEvent({ type: "token", delta: "部分回答" }, 2));
        await new Promise<void>((_resolve, reject) => {
          signal.addEventListener("abort", () =>
            reject(new DOMException("Aborted")),
          );
        });
      },
    );
    const { container } = render(<Harness />);
    fireEvent.change(
      screen.getByPlaceholderText("Ask about the selected PDFs..."),
      {
        target: { value: "Question" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    fireEvent.click(await screen.findByRole("button", { name: "停止生成" }));

    expect(await screen.findByText("部分回答")).toBeInTheDocument();
    expect(await screen.findByText("已停止生成")).toBeInTheDocument();
    expect(
      container.querySelector(".assistant-message.cancelled"),
    ).not.toBeNull();
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
  });
});
