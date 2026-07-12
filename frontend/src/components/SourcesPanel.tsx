import { useMemo, useState } from "react";
import type { LibraryItem, RagCitation, WebSource } from "../api/types";
import {
  buildSourceCards,
  isLowOcrConfidence,
  isOcrSource,
  pageLabel,
  safeExternalSourceUrl,
  sourceDomain,
  sourceIds,
  truncatedExcerpt,
  type SourceCard,
  type SourceGroup,
} from "../sources/sourceUtils";
import { openExternalSource } from "../tauri/externalOpener";
import { openManagedLibraryPdf } from "../tauri/pdfOpener";

export function SourcesPanel({
  citations,
  webSources,
  libraryItems,
  expanded,
  highlightedCitationId,
  missingCitationId,
  onExpandedChange,
}: {
  citations?: RagCitation[];
  webSources?: WebSource[];
  libraryItems: LibraryItem[];
  expanded: boolean;
  highlightedCitationId: string | null;
  missingCitationId: string | null;
  onExpandedChange: (expanded: boolean) => void;
}) {
  const cards = useMemo(
    () => buildSourceCards(citations, webSources),
    [citations, webSources],
  );
  const ids = useMemo(() => sourceIds(cards), [cards]);
  const [interactionMessage, setInteractionMessage] = useState<string | null>(
    null,
  );
  if (cards.length === 0 && !missingCitationId) return null;

  return (
    <section className="sources-panel" aria-label="Sources">
      <button
        type="button"
        className="sources-toggle"
        aria-expanded={expanded}
        onClick={() => onExpandedChange(!expanded)}
      >
        <span>Sources</span>
        <span className="source-count">{cards.length}</span>
        <span aria-hidden="true">{expanded ? "▴" : "▾"}</span>
      </button>
      {expanded && (
        <div className="sources-content">
          {missingCitationId && !ids.has(missingCitationId) && (
            <p className="source-notice" role="status">
              Source [{missingCitationId}] is unavailable in this response.
            </p>
          )}
          {(["local", "web", "academic"] as SourceGroup[]).map((group) => {
            const grouped = cards.filter((card) => card.group === group);
            return grouped.length ? (
              <SourceGroupSection
                cards={grouped}
                group={group}
                highlightedCitationId={highlightedCitationId}
                libraryItems={libraryItems}
                onMessage={setInteractionMessage}
                key={group}
              />
            ) : null;
          })}
          {interactionMessage && (
            <p className="source-notice" role="status">
              {interactionMessage}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function SourceGroupSection({
  cards,
  group,
  highlightedCitationId,
  libraryItems,
  onMessage,
}: {
  cards: SourceCard[];
  group: SourceGroup;
  highlightedCitationId: string | null;
  libraryItems: LibraryItem[];
  onMessage: (message: string | null) => void;
}) {
  return (
    <section className="source-group" aria-label={groupLabel(group)}>
      <h4>{groupLabel(group)}</h4>
      <ul className="source-card-list">
        {cards.map((card) => (
          <SourceCardView
            card={card}
            highlighted={Boolean(
              highlightedCitationId &&
              card.citationIds.includes(highlightedCitationId),
            )}
            libraryItems={libraryItems}
            onMessage={onMessage}
            key={card.key}
          />
        ))}
      </ul>
    </section>
  );
}

function SourceCardView({
  card,
  highlighted,
  libraryItems,
  onMessage,
}: {
  card: SourceCard;
  highlighted: boolean;
  libraryItems: LibraryItem[];
  onMessage: (message: string | null) => void;
}) {
  const page = pageLabel(card);
  const externalUrl = safeExternalSourceUrl(card);
  const domain = sourceDomain(externalUrl);
  const markerLabel = card.citationIds.map((id) => `[${id}]`).join(" ");

  async function openSource() {
    onMessage(null);
    try {
      if (card.group === "local") {
        const item = libraryItems.find(
          (value) => value.id === card.libraryItemId,
        );
        if (!item) {
          throw new Error(
            "This local source is no longer available in the Repository.",
          );
        }
        await openManagedLibraryPdf(item);
        onMessage(
          card.pageStart
            ? `Opened ${card.title}. If the system reader did not jump automatically, go to page ${card.pageStart}.`
            : `Opened ${card.title} in the system PDF reader.`,
        );
      } else {
        await openExternalSource({
          url: card.url,
          doi: card.doi,
          arxivId: card.arxivId,
        });
      }
    } catch (error) {
      onMessage(
        error instanceof Error
          ? error.message
          : "The source could not be opened.",
      );
    }
  }

  return (
    <li
      className={`source-card${highlighted ? " highlighted" : ""}`}
      data-citation-ids={card.citationIds.join(" ")}
      tabIndex={-1}
    >
      <div className="source-card-heading">
        <span className="source-markers">{markerLabel}</span>
        <button
          type="button"
          className="source-title-button"
          onClick={openSource}
          aria-label={openLabel(card, page)}
        >
          {card.title}
        </button>
      </div>
      <div className="source-meta">
        {page && <span>{page}</span>}
        {card.sectionPath.length > 0 && (
          <span>{card.sectionPath.join(" › ")}</span>
        )}
        {card.group === "local" && (
          <span>
            {isOcrSource(card) ? "Scanned page / OCR" : "Native text"}
          </span>
        )}
        {domain && <span>{domain}</span>}
        {externalUrl && <span className="source-url">{externalUrl}</span>}
        {card.publishedAt && <span>{card.publishedAt}</span>}
        {card.authors.length > 0 && <span>{card.authors.join(", ")}</span>}
        {card.doi && <span>DOI {card.doi}</span>}
        {card.arxivId && <span>arXiv {card.arxivId}</span>}
        {card.sourceType && <span>{card.sourceType}</span>}
        {card.provider && (
          <span className="source-provider">{card.provider}</span>
        )}
      </div>
      {isLowOcrConfidence(card) && (
        <p className="ocr-warning" role="note">
          OCR confidence is low ({Math.round((card.ocrConfidence || 0) * 100)}
          %). Verify the scanned page before quoting it.
        </p>
      )}
      {!externalUrl && card.group !== "local" && (
        <p className="source-notice">No safe external URL is available.</p>
      )}
      {card.excerpt ? (
        <details className="source-excerpt">
          <summary>Show excerpt</summary>
          <p>{truncatedExcerpt(card.excerpt)}</p>
        </details>
      ) : (
        <p className="source-notice">No source excerpt is available.</p>
      )}
    </li>
  );
}

function groupLabel(group: SourceGroup): string {
  if (group === "local") return "Local Sources";
  if (group === "academic") return "Academic Sources";
  return "Web Sources";
}

function openLabel(card: SourceCard, page: string | null): string {
  if (card.group === "local") {
    return `Open ${card.title}${page ? `, ${page}` : ""} in the system PDF reader`;
  }
  return `Open ${card.title} in the system browser`;
}
