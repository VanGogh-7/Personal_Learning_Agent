import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { LibraryItem } from "../api/types";
import type { ConversationState } from "../chat/conversationState";
import RagQueryPanel, { buildAgentChatRequest } from "./RagQueryPanel";

const book = (id: string, status = "indexed"): LibraryItem => ({
  id,
  title: id,
  author: null,
  description: null,
  file_type: "pdf",
  topic_tags: null,
  status,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});

describe("Agent Chat panel", () => {
  it("builds a deduplicated multi-book payload with the same conversation", () => {
    const conversation: ConversationState = {
      conversationId: "conversation-a",
      messages: [],
      selectedLibraryItemIds: ["book-1", "book-2"],
    };
    expect(
      buildAgentChatRequest(
        conversation,
        [
          book("book-1"),
          book("book-2"),
          book("book-2"),
          book("draft", "registered"),
        ],
        "Explain it",
      ),
    ).toEqual({
      conversation_id: "conversation-a",
      message: "Explain it",
      selected_library_item_ids: ["book-1", "book-2"],
    });
  });

  it("keeps the same bottom composer and message list when context changes", () => {
    const empty: ConversationState = {
      conversationId: "conversation-a",
      messages: [],
      selectedLibraryItemIds: [],
    };
    const onChange = vi.fn();
    const { container, rerender } = render(
      <RagQueryPanel
        conversation={empty}
        onConversationChange={onChange}
        workspaceSelectedItems={[]}
      />,
    );
    const panel = container.querySelector(".agent-chat-panel")!;
    const composer = container.querySelector(".chat-compose")!;
    const scrollRegion = container.querySelector(".chat-scroll-region")!;
    expect(panel.lastElementChild).toBe(composer);
    expect(scrollRegion).toContainElement(
      screen.getByText("Ask a question about the selected PDFs."),
    );

    rerender(
      <RagQueryPanel
        conversation={{
          ...empty,
          messages: [
            {
              id: 1,
              question: "Question",
              answer: "## Answer\n\nFor $x \\in X$.",
            },
          ],
          selectedLibraryItemIds: ["book-1"],
        }}
        onConversationChange={onChange}
        workspaceSelectedItems={[book("book-1")]}
      />,
    );
    expect(container.querySelector(".chat-compose")).toBe(composer);
    expect(container.querySelector(".chat-scroll-region")).toBe(scrollRegion);
    expect(panel.lastElementChild).toBe(composer);
    expect(screen.getByText("Answer")).toBeInTheDocument();
    expect(container.querySelector(".assistant-message .katex")).not.toBeNull();
    fireEvent.scroll(scrollRegion, { target: { scrollTop: 0 } });
  });
});
