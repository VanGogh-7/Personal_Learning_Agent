import type { RagCitation, WebSource } from "../api/types";

export type SourceGroup = "local" | "web" | "academic";

export interface SourceCard {
  key: string;
  citationIds: string[];
  group: SourceGroup;
  title: string;
  excerpt: string;
  libraryItemId?: string | null;
  pageStart?: number | null;
  pageEnd?: number | null;
  sectionPath: string[];
  extractionMethod?: string | null;
  ocrConfidence?: number | null;
  boundingBoxes: Array<Record<string, unknown>>;
  url?: string | null;
  provider?: string | null;
  sourceType?: string | null;
  authors: string[];
  publishedAt?: string | null;
  doi?: string | null;
  arxivId?: string | null;
}

export function buildSourceCards(
  citations: RagCitation[] = [],
  webSources: WebSource[] = [],
): SourceCard[] {
  return [
    ...mergeLocalSources(citations),
    ...deduplicateExternalSources(webSources),
  ];
}

export function sourceIds(cards: SourceCard[]): Set<string> {
  return new Set(cards.flatMap((card) => card.citationIds));
}

export function safeExternalSourceUrl(source: {
  url?: string | null;
  doi?: string | null;
  arxivId?: string | null;
}): string | null {
  const doi = normalizeDoi(source.doi);
  if (doi) return `https://doi.org/${doi}`;
  const arxiv = normalizeArxivId(source.arxivId);
  if (arxiv) return `https://arxiv.org/abs/${arxiv}`;
  return safeHttpUrl(source.url);
}

export function safeHttpUrl(value?: string | null): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value.trim());
    if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname) {
      return null;
    }
    return parsed.toString();
  } catch {
    return null;
  }
}

export function sourceDomain(value?: string | null): string | null {
  const safe = safeHttpUrl(value);
  return safe ? new URL(safe).hostname.replace(/^www\./, "") : null;
}

export function isLowOcrConfidence(card: SourceCard): boolean {
  return (
    isOcrSource(card) &&
    card.ocrConfidence !== null &&
    card.ocrConfidence !== undefined &&
    card.ocrConfidence < 0.8
  );
}

export function isOcrSource(card: SourceCard): boolean {
  return /ocr/i.test(card.extractionMethod || "");
}

export function pageLabel(card: SourceCard): string | null {
  if (card.pageStart && card.pageEnd) {
    return card.pageStart === card.pageEnd
      ? `Page ${card.pageStart}`
      : `Pages ${card.pageStart}–${card.pageEnd}`;
  }
  if (card.pageStart) return `Page ${card.pageStart}`;
  if (card.pageEnd) return `Page ${card.pageEnd}`;
  return null;
}

export function truncatedExcerpt(value: string, maxLength = 320): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length <= maxLength
    ? normalized
    : `${normalized.slice(0, maxLength - 1).trimEnd()}…`;
}

function mergeLocalSources(citations: RagCitation[]): SourceCard[] {
  const cards: SourceCard[] = [];
  for (const citation of citations) {
    const pageStart = citation.page_start ?? citation.page_number;
    const pageEnd = citation.page_end ?? citation.page_number;
    const bookKey = citation.library_item_id || citation.document_id;
    const previous = cards[cards.length - 1];
    if (
      previous?.group === "local" &&
      previous.key.startsWith(`local:${bookKey}:`) &&
      pagesTouch(previous.pageStart, previous.pageEnd, pageStart, pageEnd)
    ) {
      previous.citationIds.push(citation.citation_id);
      previous.pageStart = minPage(previous.pageStart, pageStart);
      previous.pageEnd = maxPage(previous.pageEnd, pageEnd);
      previous.excerpt = joinExcerpt(previous.excerpt, citation.excerpt);
      previous.sectionPath = unique([
        ...previous.sectionPath,
        ...citationSectionPath(citation),
      ]);
      previous.boundingBoxes.push(...(citation.bounding_boxes || []));
      if (
        citation.ocr_confidence !== null &&
        citation.ocr_confidence !== undefined
      ) {
        previous.ocrConfidence = Math.min(
          previous.ocrConfidence ?? 1,
          citation.ocr_confidence,
        );
      }
      continue;
    }
    cards.push({
      key: `local:${bookKey}:${pageStart ?? "unknown"}:${citation.citation_id}`,
      citationIds: [citation.citation_id],
      group: "local",
      title:
        citation.title ||
        citation.library_title ||
        citation.document_title ||
        "Unavailable local source",
      excerpt: citation.excerpt || "",
      libraryItemId: citation.library_item_id,
      pageStart,
      pageEnd,
      sectionPath: citationSectionPath(citation),
      extractionMethod: citation.extraction_method,
      ocrConfidence: citation.ocr_confidence,
      boundingBoxes: [...(citation.bounding_boxes || [])],
      authors: [],
    });
  }
  return cards;
}

function deduplicateExternalSources(sources: WebSource[]): SourceCard[] {
  const cards = new Map<string, SourceCard>();
  for (const source of sources) {
    const citationId = source.citation_id || source.source_id;
    const doi = normalizeDoi(source.doi);
    const arxivId = normalizeArxivId(source.arxiv_id);
    const url = safeHttpUrl(source.url);
    const key = doi
      ? `doi:${doi.toLowerCase()}`
      : arxivId
        ? `arxiv:${arxivId.toLowerCase()}`
        : `url:${canonicalUrl(url) || `missing:${citationId}`}`;
    const existing = cards.get(key);
    if (existing) {
      if (!existing.citationIds.includes(citationId)) {
        existing.citationIds.push(citationId);
      }
      continue;
    }
    const academic =
      source.source_type === "academic" || Boolean(doi) || Boolean(arxivId);
    cards.set(key, {
      key,
      citationIds: [citationId],
      group: academic ? "academic" : "web",
      title: source.title || "Unavailable external source",
      excerpt: source.excerpt || source.content || "",
      sectionPath: [],
      boundingBoxes: [],
      url,
      provider: source.provider,
      sourceType: source.source_type,
      authors: source.authors || [],
      publishedAt: source.published_at || source.published_date,
      doi,
      arxivId,
    });
  }
  return [...cards.values()];
}

function citationSectionPath(citation: RagCitation): string[] {
  return unique(
    citation.section_path?.length
      ? citation.section_path
      : [citation.chapter_title, citation.section_title].filter(
          (value): value is string => Boolean(value),
        ),
  );
}

function normalizeDoi(value?: string | null): string | null {
  const normalized = (value || "")
    .trim()
    .replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "")
    .replace(/^doi:\s*/i, "");
  return /^10\.\d{4,9}\/\S+$/i.test(normalized) ? normalized : null;
}

function normalizeArxivId(value?: string | null): string | null {
  const normalized = (value || "")
    .trim()
    .replace(/^arxiv:\s*/i, "")
    .replace(/^https?:\/\/arxiv\.org\/(?:abs|pdf)\//i, "")
    .replace(/\.pdf$/i, "");
  return /^(?:[a-z.-]+\/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?$/i.test(normalized)
    ? normalized
    : null;
}

function canonicalUrl(value: string | null): string | null {
  if (!value) return null;
  const parsed = new URL(value);
  parsed.hash = "";
  parsed.hostname = parsed.hostname.toLowerCase();
  parsed.pathname = parsed.pathname.replace(/\/$/, "") || "/";
  return parsed.toString();
}

function pagesTouch(
  leftStart?: number | null,
  leftEnd?: number | null,
  rightStart?: number | null,
  rightEnd?: number | null,
): boolean {
  if (!leftStart || !leftEnd || !rightStart || !rightEnd) return false;
  return rightStart <= leftEnd + 1 && leftStart <= rightEnd + 1;
}

function minPage(left?: number | null, right?: number | null) {
  return left && right ? Math.min(left, right) : left || right || null;
}

function maxPage(left?: number | null, right?: number | null) {
  return left && right ? Math.max(left, right) : left || right || null;
}

function joinExcerpt(left: string, right: string): string {
  if (!right || left.includes(right)) return left;
  return `${left} ${right}`.trim();
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}
