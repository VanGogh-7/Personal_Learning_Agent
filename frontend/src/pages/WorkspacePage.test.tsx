import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentChatResponse, LibraryItem } from "../api/types";
import { persistConversationState } from "../chat/conversationState";
import WorkspacePage from "./WorkspacePage";

vi.mock("../api/client", () => ({
  importLibraryPdfs: vi.fn(),
  listLibraryItems: vi.fn(),
  queryAgentChat: vi.fn(),
  queryAgentChatStream: vi
    .fn()
    .mockRejectedValue({ status: 409, message: "Agent streaming is disabled" }),
}));
vi.mock("../tauri/filePicker", () => ({ selectLocalPdfFiles: vi.fn() }));
vi.mock("../tauri/pdfOpener", () => ({ openManagedLibraryPdf: vi.fn() }));

import { listLibraryItems, queryAgentChat } from "../api/client";
import { openManagedLibraryPdf } from "../tauri/pdfOpener";

const books: LibraryItem[] = [libraryItem("book-1"), libraryItem("book-2")];

describe("Repository and conversation behavior", () => {
  beforeEach(() => {
    vi.mocked(listLibraryItems).mockResolvedValue({
      items: books,
      total: books.length,
    });
    vi.mocked(queryAgentChat).mockImplementation(async (payload) =>
      agentResponse(
        payload.conversation_id || "conversation-new",
        payload.message,
      ),
    );
    vi.mocked(openManagedLibraryPdf).mockResolvedValue(undefined);
  });

  it("accumulates and removes books without changing conversation or messages", async () => {
    persistConversationState({
      conversationId: "conversation-a",
      messages: [{ id: 1, question: "Old question", answer: "Old answer" }],
      selectedLibraryItemIds: [],
    });
    render(<WorkspacePage />);
    const bookOne = await screen.findByRole("button", { name: /book-1/ });
    const bookTwo = screen.getByRole("button", { name: /book-2/ });

    vi.useFakeTimers();
    fireEvent.click(bookOne, { detail: 1 });
    act(() => vi.advanceTimersByTime(230));
    fireEvent.click(bookTwo, { detail: 1 });
    act(() => vi.advanceTimersByTime(230));
    expect(bookOne).toHaveAttribute("aria-pressed", "true");
    expect(bookTwo).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Old answer")).toBeInTheDocument();
    vi.useRealTimers();

    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), {
      target: { value: "First new question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(queryAgentChat).toHaveBeenCalledTimes(1));
    expect(vi.mocked(queryAgentChat).mock.calls[0][0]).toMatchObject({
      conversation_id: "conversation-a",
      selected_library_item_ids: ["book-1", "book-2"],
    });

    vi.useFakeTimers();
    fireEvent.click(bookOne, { detail: 1 });
    act(() => vi.advanceTimersByTime(230));
    expect(bookOne).toHaveAttribute("aria-pressed", "false");
    expect(bookTwo).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Old answer")).toBeInTheDocument();
    vi.useRealTimers();

    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), {
      target: { value: "Second new question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(queryAgentChat).toHaveBeenCalledTimes(2));
    expect(vi.mocked(queryAgentChat).mock.calls[1][0]).toMatchObject({
      conversation_id: "conversation-a",
      selected_library_item_ids: ["book-2"],
    });
  });

  it("opens on double-click once without toggling selection", async () => {
    render(<WorkspacePage />);
    const bookOne = await screen.findByRole("button", { name: /book-1/ });
    vi.useFakeTimers();
    fireEvent.click(bookOne, { detail: 1 });
    fireEvent.click(bookOne, { detail: 2 });
    fireEvent.doubleClick(bookOne);
    await act(async () => {
      vi.advanceTimersByTime(230);
      await Promise.resolve();
    });
    expect(openManagedLibraryPdf).toHaveBeenCalledOnce();
    expect(bookOne).toHaveAttribute("aria-pressed", "false");
    vi.useRealTimers();
  });

  it("shows a non-blocking PDF open error", async () => {
    vi.mocked(openManagedLibraryPdf).mockRejectedValueOnce(
      new Error(
        "The managed PDF file no longer exists. Re-import it to continue.",
      ),
    );
    render(<WorkspacePage />);
    const bookOne = await screen.findByRole("button", { name: /book-1/ });
    fireEvent.doubleClick(bookOne);
    expect(
      await screen.findByText(/managed PDF file no longer exists/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New Chat" })).toBeEnabled();
  });

  it("starts a new chat only from New Chat and clears its selected context", async () => {
    persistConversationState({
      conversationId: "conversation-a",
      messages: [{ id: 1, question: "Old question", answer: "Old answer" }],
      selectedLibraryItemIds: ["book-1"],
    });
    render(<WorkspacePage />);
    await screen.findByRole("button", { name: /book-1/ });
    fireEvent.click(screen.getByRole("button", { name: "New Chat" }));
    expect(screen.queryByText("Old answer")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /book-1/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), {
      target: { value: "New conversation question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(queryAgentChat).toHaveBeenCalledOnce());
    expect(vi.mocked(queryAgentChat).mock.calls[0][0]).toEqual({
      message: "New conversation question",
      selected_library_item_ids: [],
    });
  });
});

function libraryItem(id: string): LibraryItem {
  return {
    id,
    title: id,
    author: null,
    description: null,
    file_path: `/managed/library/${id}.pdf`,
    file_type: "pdf",
    topic_tags: null,
    status: "indexed",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function agentResponse(
  conversationId: string,
  answer: string,
): AgentChatResponse {
  return {
    conversation_id: conversationId,
    answer,
    scope_type: "multi_book",
    route: "local_only",
    selected_library_items: [],
    retrieved_chunks: [],
    citations: [],
    total_retrieved: 0,
    memory: {
      used_recent_turns: 0,
      saved_current_turn: true,
      used_long_term_memories: 0,
    },
  };
}
