import { FormEvent, useState } from "react";
import {
  archiveLibraryItem,
  createLibraryItem,
  generateLibraryMetadataDraft,
  getLibraryItem,
  indexLibraryItem,
  listLibraryItems,
  searchLibraryItems,
  updateLibraryItem,
} from "../api/client";
import type {
  LibraryItem,
  LibraryItemIndexResponse,
  LibraryItemListResponse,
  LibraryMetadataDraft,
  UpdateLibraryItemPayload,
} from "../api/types";
import LibraryItemDetail from "./library/LibraryItemDetail";
import { inferFileTypeFromPath, selectLocalFile } from "../tauri/filePicker";
import { openLocalFile } from "../tauri/localFiles";

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
  const [selectedItem, setSelectedItem] = useState<LibraryItem | null>(null);
  const [lastMode, setLastMode] = useState<"list" | "search" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingSave, setLoadingSave] = useState(false);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetailSave, setLoadingDetailSave] = useState(false);
  const [choosingFile, setChoosingFile] = useState(false);
  const [openingItemId, setOpeningItemId] = useState<string | null>(null);
  const [indexingItemId, setIndexingItemId] = useState<string | null>(null);
  const [indexResult, setIndexResult] = useState<LibraryItemIndexResponse | null>(null);
  const [indexError, setIndexError] = useState<string | null>(null);

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

      let savedItem: LibraryItem;
      if (editingId) {
        savedItem = await updateLibraryItem(editingId, payload);
      } else {
        savedItem = await createLibraryItem(payload);
      }
      setSelectedItem(savedItem);
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
      setSelectedItem((current) =>
        current ? response.items.find((item) => item.id === current.id) || current : null,
      );
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
      setSelectedItem((current) =>
        current?.id === itemId ? { ...current, status: "archived" } : current,
      );
      await loadItems(lastMode || "list");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Archive request failed.");
    }
  }

  async function openItemFile(item: LibraryItem) {
    setError(null);
    setOpeningItemId(item.id);
    try {
      await openLocalFile(item.file_path || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open local file.");
    } finally {
      setOpeningItemId(null);
    }
  }

  async function indexItemFile(item: LibraryItem) {
    setError(null);
    setIndexError(null);
    setIndexResult(null);
    setIndexingItemId(item.id);
    try {
      const response = await indexLibraryItem(item.id);
      setIndexResult(response);
      const refreshed = await getLibraryItem(item.id);
      updateItemInState(refreshed);
    } catch (err) {
      setIndexError(err instanceof Error ? err.message : "Library item indexing failed.");
    } finally {
      setIndexingItemId(null);
    }
  }

  async function chooseFileForForm() {
    setError(null);
    setChoosingFile(true);
    try {
      const selectedPath = await selectLocalFile();
      if (!selectedPath) {
        return;
      }

      setForm((current) => ({
        ...current,
        filePath: selectedPath,
        fileType: current.fileType.trim()
          ? current.fileType
          : inferFileTypeFromPath(selectedPath),
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "File picker failed.");
    } finally {
      setChoosingFile(false);
    }
  }

  function startEdit(item: LibraryItem) {
    selectItem(item);
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

  function selectItem(item: LibraryItem) {
    setSelectedItem(item);
    setIndexError(null);
    setIndexResult(null);
  }

  async function saveDetailEdit(itemId: string, payload: UpdateLibraryItemPayload) {
    setError(null);
    setLoadingDetailSave(true);
    try {
      const updated = await updateLibraryItem(itemId, payload);
      updateItemInState(updated);
      if (editingId === itemId) {
        startEdit(updated);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Library item update failed.");
      throw err;
    } finally {
      setLoadingDetailSave(false);
    }
  }

  function generateMetadataDraft(itemId: string): Promise<LibraryMetadataDraft> {
    return generateLibraryMetadataDraft(itemId);
  }

  function updateItemInState(updated: LibraryItem) {
    setSelectedItem(updated);
    setResult((current) =>
      current
        ? {
            ...current,
            items: current.items.map((item) => (item.id === updated.id ? updated : item)),
          }
        : current,
    );
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
          <label className="full-width">
            file_path
            <div className="input-with-action">
              <input
                value={form.filePath}
                onChange={(event) => setForm({ ...form, filePath: event.target.value })}
                placeholder="/path/to/book.pdf"
              />
              <button
                type="button"
                className="secondary-button"
                disabled={choosingFile}
                onClick={chooseFileForForm}
              >
                {choosingFile ? "Choosing..." : "Choose File"}
              </button>
            </div>
            <span className="field-help">
              Select a local book or note file. The path is stored as metadata.
            </span>
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
            <div className="library-workspace">
              <ul className="item-list library-list">
                {result.items.map((item) => (
                  <LibraryItemCard
                    key={item.id}
                    item={item}
                    selected={selectedItem?.id === item.id}
                    opening={openingItemId === item.id}
                    onSelect={selectItem}
                    onEdit={startEdit}
                    onOpen={openItemFile}
                    onArchive={archiveItem}
                  />
                ))}
              </ul>
              <LibraryItemDetail
                item={selectedItem}
                opening={selectedItem ? openingItemId === selectedItem.id : false}
                indexing={selectedItem ? indexingItemId === selectedItem.id : false}
                saving={loadingDetailSave}
                indexResult={indexResult}
                indexError={indexError}
                onEdit={startEdit}
                onIndex={indexItemFile}
                onOpen={openItemFile}
                onGenerateMetadataDraft={generateMetadataDraft}
                onSave={saveDetailEdit}
              />
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function LibraryItemCard({
  item,
  selected,
  opening,
  onSelect,
  onEdit,
  onOpen,
  onArchive,
}: {
  item: LibraryItem;
  selected: boolean;
  opening: boolean;
  onSelect: (item: LibraryItem) => void;
  onEdit: (item: LibraryItem) => void;
  onOpen: (item: LibraryItem) => void;
  onArchive: (itemId: string) => void;
}) {
  const hasFilePath = Boolean(item.file_path?.trim());

  return (
    <li className={selected ? "library-list-item selected" : "library-list-item"}>
      <div className="item-title">
        <span>{item.title}</span>
        <span className="status-badge">{item.status}</span>
      </div>
      <p>{item.description || "No description."}</p>
      <small>
        id {item.id} · author {item.author || "unknown"} · file {item.file_path || "none"} · type{" "}
        {item.file_type || "none"} · tags{" "}
        {item.topic_tags?.length ? item.topic_tags.join(", ") : "none"}
      </small>
      {!hasFilePath && <p className="muted compact-note">No local file path.</p>}
      <div className="button-row item-actions">
        <button type="button" className="secondary-button" onClick={() => onSelect(item)}>
          {selected ? "Selected" : "View details"}
        </button>
        {hasFilePath && (
          <button
            type="button"
            className="secondary-button"
            disabled={opening}
            onClick={() => onOpen(item)}
          >
            {opening ? "Opening..." : "Open"}
          </button>
        )}
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
