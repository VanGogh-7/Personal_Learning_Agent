import { describe, expect, it, vi } from "vitest";
import { openExternalSource } from "./externalOpener";

describe("external source opener", () => {
  it("opens DOI through its canonical HTTPS URL", async () => {
    const opener = vi.fn().mockResolvedValue(undefined);

    await openExternalSource(
      { doi: "https://doi.org/10.1000/test", url: "https://example.com" },
      opener,
    );

    expect(opener).toHaveBeenCalledWith("https://doi.org/10.1000/test");
  });

  it("opens an arXiv identifier through its canonical abstract URL", async () => {
    const opener = vi.fn().mockResolvedValue(undefined);

    await openExternalSource({ arxivId: "2401.01234" }, opener);

    expect(opener).toHaveBeenCalledWith("https://arxiv.org/abs/2401.01234");
  });

  it("rejects javascript and file URLs before invoking Tauri", async () => {
    const opener = vi.fn();

    await expect(
      openExternalSource({ url: "javascript:alert(1)" }, opener),
    ).rejects.toThrow("no safe HTTP or HTTPS link");
    await expect(
      openExternalSource({ url: "file:///tmp/private.pdf" }, opener),
    ).rejects.toThrow("no safe HTTP or HTTPS link");
    expect(opener).not.toHaveBeenCalled();
  });
});
