import { describe, expect, it } from "vitest";
import {
  activeConversation,
  createConversationWorkspace,
  selectConversation,
  startNewConversation,
  updateActiveConversation,
  updateConversationEntry,
} from "./conversationWorkspace";

describe("conversation workspace", () => {
  it("keeps completed conversations available and isolates New Chat", () => {
    const initial = createConversationWorkspace();
    const withTurn = updateActiveConversation(initial, {
      conversationId: "conversation-a",
      messages: [{ id: 1, question: "Explain compactness", answer: "Answer" }],
      selectedLibraryItemIds: ["book-1"],
    });
    const next = startNewConversation(withTurn);

    expect(next.conversations).toHaveLength(2);
    expect(activeConversation(next).state).toMatchObject({
      conversationId: null,
      messages: [],
      selectedLibraryItemIds: [],
    });
    const restored = selectConversation(next, withTurn.activeKey);
    expect(activeConversation(restored).state.conversationId).toBe(
      "conversation-a",
    );
    expect(activeConversation(restored).state.selectedLibraryItemIds).toEqual([
      "book-1",
    ]);
  });

  it("does not create repeated blank conversations", () => {
    const initial = createConversationWorkspace();
    expect(startNewConversation(initial)).toBe(initial);
  });

  it("applies late streaming updates only to their originating conversation", () => {
    const first = updateActiveConversation(createConversationWorkspace(), {
      conversationId: "conversation-a",
      messages: [{ id: "a", question: "A", answer: "" }],
      selectedLibraryItemIds: [],
    });
    const second = startNewConversation(first);
    const updated = updateConversationEntry(
      second,
      first.activeKey,
      (state) => ({
        ...state,
        messages: state.messages.map((turn) => ({
          ...turn,
          answer: "Answer A",
        })),
      }),
    );

    expect(activeConversation(updated).state.messages).toEqual([]);
    expect(
      updated.conversations.find((entry) => entry.key === first.activeKey)
        ?.state.messages[0].answer,
    ).toBe("Answer A");
  });
});
