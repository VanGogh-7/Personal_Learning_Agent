import { useEffect, useState } from "react";
import { listLearningEvents } from "../api/client";
import type { LearningEvent, LearningEventListResponse } from "../api/types";

export default function ProgressPage() {
  const [selectedDate, setSelectedDate] = useState(todayInputValue());
  const [filters, setFilters] = useState({
    eventType: "",
    sourceType: "",
    limit: 100,
  });
  const [result, setResult] = useState<LearningEventListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadDay(selectedDate);
  }, [selectedDate]);

  async function loadDay(date: string) {
    setError(null);
    setLoading(true);
    try {
      const response = await listLearningEvents({
        date,
        event_type: filters.eventType.trim() || undefined,
        source_type: filters.sourceType.trim() || undefined,
        limit: filters.limit,
        offset: 0,
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Learning events request failed.");
    } finally {
      setLoading(false);
    }
  }

  function applyFilters() {
    void loadDay(selectedDate);
  }

  function jumpToToday() {
    setSelectedDate(todayInputValue());
  }

  return (
    <div className="page-stack">
      <section className="page-intro">
        <p>Learning events for a selected day. Start with today, then review another date when needed.</p>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Today Log</h2>
            <p>{formatSelectedDate(selectedDate)}</p>
          </div>
          <button type="button" className="secondary-button" disabled={loading} onClick={() => loadDay(selectedDate)}>
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        <div className="form-grid compact-heading">
          <label>
            date
            <input
              type="date"
              value={selectedDate}
              onChange={(event) => setSelectedDate(event.target.value || todayInputValue())}
            />
          </label>
          <label>
            event type
            <input
              value={filters.eventType}
              onChange={(event) => setFilters({ ...filters, eventType: event.target.value })}
              placeholder="note_created"
            />
          </label>
          <label>
            source type
            <input
              value={filters.sourceType}
              onChange={(event) => setFilters({ ...filters, sourceType: event.target.value })}
              placeholder="notes"
            />
          </label>
          <label>
            limit
            <input
              type="number"
              min={1}
              max={100}
              value={filters.limit}
              onChange={(event) =>
                setFilters({ ...filters, limit: event.target.valueAsNumber })
              }
            />
          </label>
          <div className="button-row">
            <button type="button" disabled={loading} onClick={applyFilters}>
              {loading ? "Loading..." : "Apply filters"}
            </button>
            <button type="button" className="secondary-button" disabled={loading} onClick={jumpToToday}>
              Today
            </button>
          </div>
        </div>

        {error && <p className="error">{error}</p>}

        <div className="response-block">
          <h3>Events{result ? ` (${result.total})` : ""}</h3>
          {!result ? (
            <p className="empty-state">No events loaded.</p>
          ) : result.events.length === 0 ? (
            <p className="empty-state">No learning events for this date.</p>
          ) : (
            <ol className="timeline-list">
              {result.events.map((event) => (
                <LearningEventItem event={event} key={event.id} />
              ))}
            </ol>
          )}
        </div>
      </section>
    </div>
  );
}

function LearningEventItem({ event }: { event: LearningEvent }) {
  const relatedTitle = event.library_item_title || event.note_title;
  const metadataItems = learningEventMetadata(event);
  const idItems = [
    event.library_item_id ? { label: "library id", value: event.library_item_id } : null,
    event.note_id ? { label: "note id", value: event.note_id } : null,
    event.session_id ? { label: "session", value: event.session_id } : null,
  ].filter((item): item is { label: string; value: string } => item !== null);

  return (
    <li className="timeline-item">
      <div className="timeline-marker" aria-hidden="true" />
      <div className="timeline-content">
        <div className="item-title">
          <span>{event.title || readableEventType(event.event_type)}</span>
          <time>{formatTime(event.created_at)}</time>
        </div>
        <div className="tag-row">
          <span className="tag-badge">{readableEventType(event.event_type)}</span>
          {event.source_type && <span className="tag-badge">{event.source_type}</span>}
        </div>
        {relatedTitle && <p className="today-log-related">{relatedTitle}</p>}
        {event.description && <p>{event.description}</p>}
        {metadataItems.length > 0 && (
          <dl className="event-metadata-list">
            {metadataItems.map((item) => (
              <EventMeta key={item.label} label={item.label} value={item.value} />
            ))}
          </dl>
        )}
        {idItems.length > 0 && (
          <dl className="event-metadata-list">
            {idItems.map((item) => (
              <EventMeta key={item.label} label={item.label} value={item.value} />
            ))}
          </dl>
        )}
        {hasAdditionalMetadata(event.metadata_json, metadataItems) && (
          <pre className="event-json">{JSON.stringify(event.metadata_json, null, 2)}</pre>
        )}
      </div>
    </li>
  );
}

function EventMeta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function todayInputValue(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatSelectedDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) {
    return value;
  }
  return new Date(year, month - 1, day).toLocaleDateString([], {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function readableEventType(eventType: string): string {
  const labels: Record<string, string> = {
    library_indexed: "Indexed PDF",
    metadata_draft_generated: "Generated metadata",
    book_rag_question_asked: "Asked PDF question",
    multi_book_rag_question_asked: "Asked multi-PDF question",
    agent_chat_question_asked: "Asked Agent Chat",
    note_created: "Created note",
    note_from_chat_created: "Created note from chat",
    note_exported: "Exported note",
  };
  return labels[eventType] || eventType.split("_").join(" ");
}

function learningEventMetadata(event: LearningEvent): Array<{ label: string; value: string }> {
  const metadata = event.metadata_json || {};
  return [
    metadataValue("question", metadata.question),
    metadataValue("scope", metadata.scope_type || metadata.scope),
    metadataValue("books", metadata.library_titles),
    metadataValue("chunks", metadata.total_retrieved || metadata.chunks_created),
    metadataValue("citations", metadata.citation_count),
    metadataValue("mode", metadata.mode),
    metadataValue("tags", metadata.topic_tags || metadata.topic_tags_count),
    metadataValue("document", metadata.document_id),
    metadataValue("export", metadata.export_path),
    metadataValue("status", metadata.status),
  ].filter((item): item is { label: string; value: string } => item !== null);
}

function hasAdditionalMetadata(
  metadata: Record<string, unknown> | null,
  displayedItems: Array<{ label: string; value: string }>,
): boolean {
  if (!metadata) {
    return false;
  }

  const displayedLabels = new Set(displayedItems.map((item) => item.label));
  const mappedKeys: Record<string, string> = {
    question: "question",
    scope_type: "scope",
    scope: "scope",
    library_titles: "books",
    total_retrieved: "chunks",
    chunks_created: "chunks",
    citation_count: "citations",
    mode: "mode",
    topic_tags: "tags",
    topic_tags_count: "tags",
    document_id: "document",
    export_path: "export",
    status: "status",
  };

  return Object.keys(metadata).some((key) => {
    const label = mappedKeys[key];
    return !label || !displayedLabels.has(label);
  });
}

function metadataValue(label: string, value: unknown): { label: string; value: string } | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (Array.isArray(value)) {
    return { label, value: value.map((item) => String(item)).join(", ") };
  }
  if (typeof value === "object") {
    return { label, value: JSON.stringify(value) };
  }
  return { label, value: String(value) };
}
