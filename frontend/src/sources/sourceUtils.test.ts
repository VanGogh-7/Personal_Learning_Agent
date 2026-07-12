import { describe, expect, it } from "vitest";
import type { RagCitation, WebSource } from "../api/types";
import {
  buildSourceCards,
  safeExternalSourceUrl,
  safeHttpUrl,
} from "./sourceUtils";

function citation(
  id: string,
  pageStart: number,
  pageEnd = pageStart,
): RagCitation {
  return {
    citation_id: id,
    chunk_id: `chunk-${id}`,
    document_id: "document-1",
    library_item_id: "book-1",
    library_title: "Analysis",
    library_author: null,
    document_title: "Analysis",
    document_source_path: "/private/path/analysis.pdf",
    chunk_index: pageStart,
    page_number: pageStart === pageEnd ? pageStart : null,
    page_start: pageStart,
    page_end: pageEnd,
    score: 0.9,
    excerpt: `Excerpt ${id}`,
    content: `Content ${id}`,
    section_path: ["Chapter 1", "Section 2"],
  };
}

function web(values: Partial<WebSource>): WebSource {
  return {
    source_id: "W1",
    title: "Paper",
    url: "https://example.com/paper",
    excerpt: "Abstract",
    provider: "openalex",
    ...values,
  };
}

describe("source normalization", () => {
  it("merges adjacent pages without changing citation marker aliases", () => {
    const cards = buildSourceCards([citation("S1", 4), citation("S2", 5)], []);

    expect(cards).toHaveLength(1);
    expect(cards[0].citationIds).toEqual(["S1", "S2"]);
    expect([cards[0].pageStart, cards[0].pageEnd]).toEqual([4, 5]);
  });

  it("deduplicates DOI, arXiv and canonical URL sources", () => {
    const cards = buildSourceCards(
      [],
      [
        web({ source_id: "W1", doi: "10.1000/ABC" }),
        web({ source_id: "W2", doi: "https://doi.org/10.1000/abc" }),
        web({ source_id: "W3", arxiv_id: "2401.01234" }),
        web({ source_id: "W4", arxiv_id: "arXiv:2401.01234" }),
        web({ source_id: "W5", doi: null, url: "https://EXAMPLE.com/page/" }),
        web({ source_id: "W6", doi: null, url: "https://example.com/page" }),
      ],
    );

    expect(cards).toHaveLength(3);
    expect(cards[0].citationIds).toEqual(["W1", "W2"]);
    expect(cards[1].citationIds).toEqual(["W3", "W4"]);
    expect(cards[2].citationIds).toEqual(["W5", "W6"]);
  });

  it("prefers canonical DOI and rejects unsafe protocols", () => {
    expect(
      safeExternalSourceUrl({
        doi: "10.5555/example",
        url: "https://publisher.example/article",
      }),
    ).toBe("https://doi.org/10.5555/example");
    expect(safeHttpUrl("javascript:alert(1)")).toBeNull();
    expect(safeHttpUrl("file:///tmp/private.pdf")).toBeNull();
  });
});
