import { useEffect, useState } from "react";
import { getRecentLearningEvents, listLearningEvents } from "../api/client";
import type { LearningEvent, LearningEventListResponse } from "../api/types";

export default function ProgressPage() {
  const [filters, setFilters] = useState({
    eventType: "",
    sourceType: "",
    limit: 20,
  });
  const [result, setResult] = useState<LearningEventListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadRecent();
  }, []);

  async function loadRecent() {
    setError(null);
    setLoading(true);
    try {
      const response = await getRecentLearningEvents(filters.limit);
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Learning events request failed.");
    } finally {
      setLoading(false);
    }
  }

  async function applyFilters() {
    setError(null);
    setLoading(true);
    try {
      const response = await listLearningEvents({
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

  return (
    <div className="page-stack">
      <section className="page-intro">
        <p>Recent learning activity from Library, RAG, and Notes actions.</p>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Learning Progress</h2>
            <p>Timeline</p>
          </div>
          <button type="button" className="secondary-button" disabled={loading} onClick={loadRecent}>
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        <div className="form-grid compact-heading">
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
          </div>
        </div>

        {error && <p className="error">{error}</p>}

        <div className="response-block">
          <h3>Events{result ? ` (${result.total})` : ""}</h3>
          {!result ? (
            <p className="empty-state">No events loaded.</p>
          ) : result.events.length === 0 ? (
            <p className="empty-state">No learning events matched these filters.</p>
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
  return (
    <li className="timeline-item">
      <div className="timeline-marker" aria-hidden="true" />
      <div className="timeline-content">
        <div className="item-title">
          <span>{event.title}</span>
          <time>{formatDate(event.created_at)}</time>
        </div>
        <div className="tag-row">
          <span className="tag-badge">{event.event_type}</span>
          {event.source_type && <span className="tag-badge">{event.source_type}</span>}
        </div>
        {event.description && <p>{event.description}</p>}
        <dl className="event-metadata-list">
          {event.library_item_id && (
            <EventMeta label="library" value={event.library_item_id} />
          )}
          {event.note_id && <EventMeta label="note" value={event.note_id} />}
          {event.session_id && <EventMeta label="session" value={event.session_id} />}
        </dl>
        {event.metadata_json && Object.keys(event.metadata_json).length > 0 && (
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

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
