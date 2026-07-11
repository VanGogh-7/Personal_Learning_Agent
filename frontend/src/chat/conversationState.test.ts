import { describe, expect, it } from "vitest";
import {
  createEmptyConversationState,
  pruneMissingLibraryItems,
  toggleSelectedLibraryItem,
} from "./conversationState";

describe("conversation state", () => {
  it("toggles deduplicated books without changing conversation or messages", () => {
    const initial = {
      conversationId: "conversation-a",
      messages: [{ id: 1, question: "Q", answer: "A" }],
      selectedLibraryItemIds: [] as string[],
    };
    const bookOne = toggleSelectedLibraryItem(initial, "book-1");
    const bookTwo = toggleSelectedLibraryItem(bookOne, "book-2");
    const removedBookOne = toggleSelectedLibraryItem(bookTwo, "book-1");

    expect(bookTwo.selectedLibraryItemIds).toEqual(["book-1", "book-2"]);
    expect(removedBookOne.selectedLibraryItemIds).toEqual(["book-2"]);
    expect(removedBookOne.conversationId).toBe("conversation-a");
    expect(removedBookOne.messages).toBe(initial.messages);
  });

  it("creates an independent empty state for New Chat", () => {
    const oldState = {
      conversationId: "conversation-a",
      messages: [{ id: 1, question: "Q", answer: "A" }],
      selectedLibraryItemIds: ["book-1"],
    };
    const newState = createEmptyConversationState();

    expect(newState).toEqual({
      conversationId: null,
      messages: [],
      selectedLibraryItemIds: [],
    });
    expect(oldState.messages).toHaveLength(1);
    expect(oldState.selectedLibraryItemIds).toEqual(["book-1"]);
  });

  it("removes missing restored book IDs without clearing conversation", () => {
    const state = {
      conversationId: "conversation-a",
      messages: [{ id: 1, question: "Q", answer: "A" }],
      selectedLibraryItemIds: ["book-1", "missing"],
    };
    const pruned = pruneMissingLibraryItems(state, new Set(["book-1"]));
    expect(pruned.selectedLibraryItemIds).toEqual(["book-1"]);
    expect(pruned.conversationId).toBe("conversation-a");
    expect(pruned.messages).toBe(state.messages);
  });
});
