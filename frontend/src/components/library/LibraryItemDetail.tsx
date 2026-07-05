import { FormEvent, useEffect, useState } from "react";
import type {
  LibraryItem,
  LibraryItemIndexResponse,
  UpdateLibraryItemPayload,
} from "../../api/types";

type DetailFormState = {
  title: string;
  author: string;
  description: string;
  filePath: string;
  fileType: string;
  topicTags: string;
  status: string;
};

export default function LibraryItemDetail({
  item,
  opening,
  indexing,
  saving,
  indexResult,
  indexError,
  onEdit,
  onIndex,
  onOpen,
  onSave,
}: {
  item: LibraryItem | null;
  opening: boolean;
  indexing: boolean;
  saving: boolean;
  indexResult: LibraryItemIndexResponse | null;
  indexError: string | null;
  onEdit: (item: LibraryItem) => void;
  onIndex: (item: LibraryItem) => void;
  onOpen: (item: LibraryItem) => void;
  onSave: (itemId: string, payload: UpdateLibraryItemPayload) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<DetailFormState>(() => createFormState(item));
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    setEditing(false);
    setLocalError(null);
    setForm(createFormState(item));
  }, [item]);

  if (!item) {
    return (
      <aside className="library-detail panel-subsection">
        <p className="empty-state">Select a book to view details.</p>
      </aside>
    );
  }

  async function submitEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!item) {
      return;
    }

    setLocalError(null);
    if (!form.title.trim()) {
      setLocalError("Title is required.");
      return;
    }
    if (!form.status.trim()) {
      setLocalError("Status is required.");
      return;
    }

    try {
      await onSave(item.id, {
        title: form.title.trim(),
        author: emptyToNull(form.author),
        description: emptyToNull(form.description),
        file_path: emptyToNull(form.filePath),
        file_type: emptyToNull(form.fileType),
        topic_tags: parseTags(form.topicTags),
        status: form.status.trim(),
      });
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Library item update failed.");
      return;
    }
    setEditing(false);
  }

  return (
    <aside className="library-detail panel-subsection">
      <div className="detail-header">
        <div>
          <h3>{item.title}</h3>
          <p>{item.author || "Unknown author"}</p>
        </div>
        <span className="status-badge">{item.status}</span>
      </div>

      {editing ? (
        <form className="form-grid detail-edit-form" onSubmit={submitEdit}>
          <label className="full-width">
            title
            <input
              value={form.title}
              onChange={(event) => setForm({ ...form, title: event.target.value })}
            />
          </label>
          <label>
            author
            <input
              value={form.author}
              onChange={(event) => setForm({ ...form, author: event.target.value })}
            />
          </label>
          <label>
            status
            <input
              value={form.status}
              onChange={(event) => setForm({ ...form, status: event.target.value })}
            />
          </label>
          <label>
            file_path
            <input
              value={form.filePath}
              onChange={(event) => setForm({ ...form, filePath: event.target.value })}
            />
          </label>
          <label>
            file_type
            <input
              value={form.fileType}
              onChange={(event) => setForm({ ...form, fileType: event.target.value })}
            />
          </label>
          <label className="full-width">
            topic_tags
            <input
              value={form.topicTags}
              onChange={(event) => setForm({ ...form, topicTags: event.target.value })}
              placeholder="math, topology"
            />
          </label>
          <label className="full-width">
            description
            <textarea
              rows={4}
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
            />
          </label>
          <div className="button-row full-width">
            <button type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save metadata"}
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={saving}
              onClick={() => {
                setEditing(false);
                setLocalError(null);
                setForm(createFormState(item));
              }}
            >
              Cancel
            </button>
          </div>
          {localError && <p className="error full-width">{localError}</p>}
        </form>
      ) : (
        <>
          <dl className="detail-grid">
            <DetailRow label="id" value={item.id} mono />
            <DetailRow label="title" value={item.title} />
            <DetailRow label="author" value={item.author || "Unknown"} />
            <DetailRow label="description" value={item.description || "No description."} wide />
            <DetailRow
              label="file_path"
              value={item.file_path || "No local file path registered."}
              mono
              wide
            />
            <DetailRow label="file_type" value={item.file_type || "none"} />
            <DetailRow label="created_at" value={formatDate(item.created_at)} />
            <DetailRow label="updated_at" value={formatDate(item.updated_at)} />
          </dl>

          <div className="detail-section">
            <h4>Topic Tags</h4>
            {item.topic_tags?.length ? (
              <div className="tag-row">
                {item.topic_tags.map((tag) => (
                  <span className="tag-badge" key={tag}>
                    {tag}
                  </span>
                ))}
              </div>
            ) : (
              <p className="muted compact-note">No topic tags.</p>
            )}
          </div>

          <div className="detail-section">
            <h4>Local File</h4>
            {item.file_path?.trim() ? (
              <div className="button-row">
                <button type="button" disabled={opening} onClick={() => onOpen(item)}>
                  {opening ? "Opening..." : "Open File"}
                </button>
                <button type="button" disabled={indexing} onClick={() => onIndex(item)}>
                  {indexing ? "Indexing..." : "Index File"}
                </button>
              </div>
            ) : (
              <p className="empty-state">No local file path registered.</p>
            )}
            <p className="field-help">Indexing currently supports .txt and .md files only.</p>
            {isPdfLike(item) && (
              <p className="field-help">
                PDF files can be opened, but PDF indexing is not supported yet.
              </p>
            )}
            {indexResult && indexResult.item_id === item.id && (
              <p className="success">
                {indexResult.message} Chunks: {indexResult.chunks_created}; embeddings:{" "}
                {indexResult.embeddings_created}.
              </p>
            )}
            {indexError && <p className="error compact-error">{indexError}</p>}
          </div>

          <div className="button-row">
            <button type="button" onClick={() => setEditing(true)}>
              Edit Metadata
            </button>
            <button type="button" className="secondary-button" onClick={() => onEdit(item)}>
              Edit in form
            </button>
          </div>
        </>
      )}

      <div className="future-grid">
        <Placeholder title="Summary" text="Coming later: automatic summary after indexing." />
        <Placeholder
          title="Indexing"
          text="Available for .txt and .md files. PDF parsing and background indexing come later."
        />
        <Placeholder title="Related Notes" text="Coming later: notes connected to this book." />
        <Placeholder
          title="Chat with this Book"
          text="Coming later: book-scoped RAG conversation."
        />
      </div>
    </aside>
  );
}

function DetailRow({
  label,
  value,
  mono = false,
  wide = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
  wide?: boolean;
}) {
  return (
    <div className={wide ? "detail-row wide" : "detail-row"}>
      <dt>{label}</dt>
      <dd className={mono ? "mono-value" : undefined}>{value}</dd>
    </div>
  );
}

function Placeholder({ title, text }: { title: string; text: string }) {
  return (
    <section className="future-placeholder">
      <h4>{title}</h4>
      <p>{text}</p>
    </section>
  );
}

function createFormState(item: LibraryItem | null): DetailFormState {
  return {
    title: item?.title || "",
    author: item?.author || "",
    description: item?.description || "",
    filePath: item?.file_path || "",
    fileType: item?.file_type || "",
    topicTags: item?.topic_tags?.join(", ") || "",
    status: item?.status || "registered",
  };
}

function parseTags(value: string): string[] | null {
  const tags = value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
  return tags.length > 0 ? tags : null;
}

function emptyToNull(value: string): string | null {
  const stripped = value.trim();
  return stripped || null;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function isPdfLike(item: LibraryItem): boolean {
  const fileType = item.file_type?.trim().toLowerCase().replace(/^\./, "");
  const path = item.file_path?.trim().toLowerCase() || "";
  return fileType === "pdf" || path.endsWith(".pdf");
}
