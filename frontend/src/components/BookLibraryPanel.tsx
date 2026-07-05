import { FormEvent, useState } from "react";
import {
  archiveLibraryItem,
  createLibraryItem,
  listLibraryItems,
  searchLibraryItems,
  updateLibraryItem,
} from "../api/client";
import type { LibraryItem, LibraryItemListResponse } from "../api/types";

const DEFAULT_STATUS = "registered";

export default function BookLibraryPanel() {
  const [form, setForm] = useState({
    title: "",
    author: "",
    description: "",
    filePath: "",
    fileType: "",
    topicTags: "",
    status: DEFAULT_STATUS,
  });
  const [filters, setFilters] = useState({
    keyword: "",
    tag: "",
    status: "",
    limit: 20,
  });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [result, setResult] = useState<LibraryItemListResponse | null>(null);
  const [lastMode, setLastMode] = useState<"list" | "search" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingSave, setLoadingSave] = useState(false);
  const [loadingList, setLoadingList] = useState(false);

  async function submitItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!form.title.trim()) {
      setError("Title is required.");
      return;
    }
    if (!form.status.trim()) {
      setError("Status is required.");
      return;
    }

    setLoadingSave(true);
    try {
      const payload = {
        title: form.title.trim(),
        author: emptyToNull(form.author),
        description: emptyToNull(form.description),
        file_path: emptyToNull(form.filePath),
        file_type: emptyToNull(form.fileType),
        topic_tags: parseTags(form.topicTags),
        status: form.status.trim(),
      };

      if (editingId) {
        await updateLibraryItem(editingId, payload);
      } else {
        await createLibraryItem(payload);
      }
      resetForm();
      await loadItems("list");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Library item save failed.");
    } finally {
      setLoadingSave(false);
    }
  }

  async function loadItems(mode: "list" | "search") {
    setError(null);

    if (!Number.isInteger(filters.limit) || filters.limit < 1 || filters.limit > 100) {
      setError("Limit must be an integer between 1 and 100.");
      return;
    }

    setLoadingList(true);
    try {
      const params = {
        keyword: filters.keyword.trim() || undefined,
        tag: filters.tag.trim() || undefined,
        status: filters.status.trim() || undefined,
        limit: filters.limit,
      };
      const response =
        mode === "search"
          ? await searchLibraryItems(params)
          : await listLibraryItems({
              tag: params.tag,
              status: params.status,
              limit: params.limit,
            });
      setResult(response);
      setLastMode(mode);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Library item request failed.");
    } finally {
      setLoadingList(false);
    }
  }

  async function archiveItem(itemId: string) {
    setError(null);
    try {
      await archiveLibraryItem(itemId);
      await loadItems(lastMode || "list");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Archive request failed.");
    }
  }

  function startEdit(item: LibraryItem) {
    setEditingId(item.id);
    setForm({
      title: item.title,
      author: item.author || "",
      description: item.description || "",
      filePath: item.file_path || "",
      fileType: item.file_type || "",
      topicTags: item.topic_tags?.join(", ") || "",
      status: item.status,
    });
  }

  function resetForm() {
    setEditingId(null);
    setForm({
      title: "",
      author: "",
      description: "",
      filePath: "",
      fileType: "",
      topicTags: "",
      status: DEFAULT_STATUS,
    });
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Book Library</h2>
          <p>Register books and learning materials as metadata only.</p>
        </div>
      </div>

      <div className="split-grid">
        <form className="form-grid" onSubmit={submitItem}>
          <h3 className="full-width">{editingId ? "Edit Item" : "Create Item"}</h3>
          <label>
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
            file_path
            <input
              value={form.filePath}
              onChange={(event) => setForm({ ...form, filePath: event.target.value })}
              placeholder="/path/to/book.pdf"
            />
          </label>
          <label>
            file_type
            <input
              value={form.fileType}
              onChange={(event) => setForm({ ...form, fileType: event.target.value })}
              placeholder="pdf, tex, md, txt, book"
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
            <button type="submit" disabled={loadingSave}>
              {loadingSave ? "Saving..." : editingId ? "Update item" : "Create item"}
            </button>
            {editingId && (
              <button type="button" className="secondary-button" onClick={resetForm}>
                Cancel edit
              </button>
            )}
          </div>
        </form>

        <div className="form-grid">
          <h3 className="full-width">List/Search Items</h3>
          <label>
            keyword
            <input
              value={filters.keyword}
              onChange={(event) => setFilters({ ...filters, keyword: event.target.value })}
              placeholder="Search title, author, description"
            />
          </label>
          <label>
            tag
            <input
              value={filters.tag}
              onChange={(event) => setFilters({ ...filters, tag: event.target.value })}
              placeholder="Optional"
            />
          </label>
          <label>
            status
            <input
              value={filters.status}
              onChange={(event) => setFilters({ ...filters, status: event.target.value })}
              placeholder="registered, indexed, archived"
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
          <div className="button-row full-width">
            <button type="button" disabled={loadingList} onClick={() => loadItems("list")}>
              {loadingList ? "Loading..." : "List items"}
            </button>
            <button type="button" disabled={loadingList} onClick={() => loadItems("search")}>
              {loadingList ? "Searching..." : "Search items"}
            </button>
          </div>
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      {result && (
        <div className="response-block">
          <h3>Library Items ({result.total})</h3>
          {result.items.length === 0 ? (
            <p className="empty-state">
              {lastMode === "search"
                ? "No library items matched this search."
                : "No library items found for these filters."}
            </p>
          ) : (
            <ul className="item-list">
              {result.items.map((item) => (
                <LibraryItemCard
                  key={item.id}
                  item={item}
                  onEdit={startEdit}
                  onArchive={archiveItem}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function LibraryItemCard({
  item,
  onEdit,
  onArchive,
}: {
  item: LibraryItem;
  onEdit: (item: LibraryItem) => void;
  onArchive: (itemId: string) => void;
}) {
  return (
    <li>
      <div className="item-title">
        <span>{item.title}</span>
        <span>{item.status}</span>
      </div>
      <p>{item.description || "No description."}</p>
      <small>
        id {item.id} · author {item.author || "unknown"} · file {item.file_path || "none"} · type{" "}
        {item.file_type || "none"} · tags{" "}
        {item.topic_tags?.length ? item.topic_tags.join(", ") : "none"}
      </small>
      <div className="button-row item-actions">
        <button type="button" className="secondary-button" onClick={() => onEdit(item)}>
          Edit
        </button>
        {item.status !== "archived" && (
          <button type="button" className="secondary-button" onClick={() => onArchive(item.id)}>
            Archive
          </button>
        )}
      </div>
    </li>
  );
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
