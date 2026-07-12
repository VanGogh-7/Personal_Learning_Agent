import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { LibraryItem, RagCitation } from "../api/types";
import { ChatTurnMessage } from "./ChatTurnMessage";

const { openManagedLibraryPdf } = vi.hoisted(() => ({
  openManagedLibraryPdf: vi.fn().mockResolvedValue(undefined),
}));
vi.mock("../tauri/pdfOpener", () => ({ openManagedLibraryPdf }));
vi.mock("../tauri/externalOpener", () => ({
  openExternalSource: vi.fn().mockResolvedValue("https://example.com"),
}));

const item: LibraryItem = {
  id: "book-1",
  title: "Scanned Analysis",
  author: null,
  description: null,
  file_type: "pdf",
  topic_tags: null,
  status: "indexed",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const citation: RagCitation = {
  citation_id: "S1",
  chunk_id: "chunk-1",
  document_id: "document-1",
  library_item_id: item.id,
  library_title: item.title,
  library_author: null,
  document_title: item.title,
  document_source_path: "/managed/scanned-analysis.pdf",
  chunk_index: 1,
  page_number: 12,
  page_start: 12,
  page_end: 12,
  score: 0.8,
  excerpt: "The OCR theorem excerpt.",
  content: "The OCR theorem excerpt.",
  extraction_method: "ocr",
  ocr_confidence: 0.62,
  bounding_boxes: [{ x0: 10, y0: 20, x1: 50, y1: 40 }],
};

describe("Sources panel interaction", () => {
  it("maps a keyboard-operable marker to and highlights its source", async () => {
    const { container } = render(
      <ChatTurnMessage
        libraryItems={[item]}
        turn={{
          id: "answer-1",
          question: "Question",
          answer: "The theorem follows [S1] and $x^2$ remains readable.",
          status: "completed",
          citations: [citation],
        }}
      />,
    );

    expect(container.querySelector(".katex")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show source S1" }));

    await waitFor(() =>
      expect(
        container.querySelector(".source-card.highlighted"),
      ).not.toBeNull(),
    );
    expect(screen.getByText("Local Sources")).toBeInTheDocument();
    expect(screen.getByText("Scanned page / OCR")).toBeInTheDocument();
    expect(screen.getByText(/OCR confidence is low/)).toBeInTheDocument();
  });

  it("opens the matched managed PDF without displaying its absolute path", async () => {
    const { container } = render(
      <ChatTurnMessage
        libraryItems={[item]}
        turn={{
          id: "answer-2",
          question: "Question",
          answer: "See [S1].",
          status: "completed",
          citations: [citation],
        }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^Sources/ }));
    fireEvent.click(
      screen.getByRole("button", {
        name: "Open Scanned Analysis, Page 12 in the system PDF reader",
      }),
    );

    await waitFor(() =>
      expect(openManagedLibraryPdf).toHaveBeenCalledWith(item),
    );
    expect(container).not.toHaveTextContent("/managed/");
  });

  it("degrades clearly when a marker has no source payload", async () => {
    render(
      <ChatTurnMessage
        turn={{
          id: "answer-3",
          question: "Question",
          answer: "Missing [W9].",
          status: "completed",
        }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Show source W9" }));

    expect(
      await screen.findByText("Source [W9] is unavailable in this response."),
    ).toBeInTheDocument();
  });
});
