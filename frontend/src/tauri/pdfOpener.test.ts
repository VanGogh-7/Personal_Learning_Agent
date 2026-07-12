import { describe, expect, it, vi } from "vitest";
import type { LibraryItem } from "../api/types";
import { openManagedLibraryPdf } from "./pdfOpener";

const item: LibraryItem = {
  id: "book-1",
  title: "Analysis",
  author: null,
  description: null,
  file_type: "pdf",
  topic_tags: null,
  status: "indexed",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("managed PDF opener", () => {
  it("opens the managed PDF exactly once", async () => {
    const opener = vi.fn().mockResolvedValue(undefined);
    await openManagedLibraryPdf(item, opener);
    expect(opener).toHaveBeenCalledOnce();
    expect(opener).toHaveBeenCalledWith(item.id);
  });

  it("returns a clear missing-file error", async () => {
    const opener = vi.fn().mockRejectedValue(new Error("No such file"));
    await expect(openManagedLibraryPdf(item, opener)).rejects.toThrow(
      "managed PDF file no longer exists",
    );
  });

  it("rejects a non-PDF item before opening", async () => {
    const opener = vi.fn();
    await expect(
      openManagedLibraryPdf({ ...item, file_type: "txt" }, opener),
    ).rejects.toThrow("Only managed PDF files");
    expect(opener).not.toHaveBeenCalled();
  });
});
