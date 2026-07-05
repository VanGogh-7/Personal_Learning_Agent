import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  archiveNote,
  createNote,
  listLibraryItems,
  listNotes,
  searchNotes,
  updateNote,
} from "../api/client";
import type { LibraryItem, Note, NoteCreateRequest, NoteUpdateRequest } from "../api/types";
import { exportTexNote } from "../tauri/noteExport";

const DEFAULT_TEMPLATE = String.raw`\section{Title}

\subsection{Definition}

\subsection{Example}

\subsection{Remarks}
`;

const EMPTY_FORM = {
  title: "",
  description: "",
  contentLatex: DEFAULT_TEMPLATE,
  libraryItemId: "",
  sourceSessionId: "",
  topicTags: "",
};

export default function NotesPage() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [libraryItems, setLibraryItems] = useState<LibraryItem[]>([]);
  const [selectedNote, setSelectedNote] = useState<Note | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [loadingNotes, setLoadingNotes] = useState(false);
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [saving, setSaving] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [lastMode, setLastMode] = useState<"list" | "search">("list");

  useEffect(() => {
    void loadNotes("list");
    void loadLibraryItems();
  }, []);

  const associatedLibraryItem = useMemo(
    () => libraryItems.find((item) => item.id === form.libraryItemId) || null,
    [form.libraryItemId, libraryItems],
  );

  async function loadNotes(mode: "list" | "search") {
    setError(null);
    setLoadingNotes(true);
    try {
      const response =
        mode === "search" && searchKeyword.trim()
          ? await searchNotes({ keyword: searchKeyword.trim(), status: "active", limit: 50 })
          : await listNotes({ status: "active", limit: 50 });
      setNotes(response.notes);
      setSelectedNote((current) =>
        current ? response.notes.find((note) => note.id === current.id) || null : null,
      );
      setLastMode(mode);
    } catch (err) {
      setNotes([]);
      setError(err instanceof Error ? err.message : "Notes request failed.");
    } finally {
      setLoadingNotes(false);
    }
  }

  async function loadLibraryItems() {
    setLoadingLibrary(true);
    try {
      const response = await listLibraryItems({ limit: 100 });
      setLibraryItems(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load library items.");
    } finally {
      setLoadingLibrary(false);
    }
  }

  async function saveNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);

    if (!form.title.trim()) {
      setError("Title is required.");
      return;
    }

    setSaving(true);
    try {
      const payload: NoteCreateRequest | NoteUpdateRequest = {
        title: form.title.trim(),
        content_latex: form.contentLatex,
        description: emptyToNull(form.description),
        library_item_id: emptyToNull(form.libraryItemId),
        source_session_id: emptyToNull(form.sourceSessionId),
        topic_tags: parseTags(form.topicTags),
      };

      const saved = selectedNote
        ? await updateNote(selectedNote.id, payload)
        : await createNote({ ...payload, status: "active" } as NoteCreateRequest);

      setSelectedNote(saved);
      setForm(noteToForm(saved));
      setNotes((current) => upsertNote(current, saved));
      setMessage(selectedNote ? "Note saved." : "Note created.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Note save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function archiveSelectedNote() {
    if (!selectedNote) {
      return;
    }
    setError(null);
    setMessage(null);
    setArchiving(true);
    try {
      const archived = await archiveNote(selectedNote.id);
      setNotes((current) => current.filter((note) => note.id !== archived.id));
      startNewNote();
      setMessage("Note archived.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Note archive failed.");
    } finally {
      setArchiving(false);
    }
  }

  async function exportSelectedNote() {
    setError(null);
    setMessage(null);

    if (!selectedNote) {
      setError("Select an existing note before exporting.");
      return;
    }
    if (!form.contentLatex.trim()) {
      setError("Cannot export an empty LaTeX note.");
      return;
    }

    setExporting(true);
    try {
      const exportedPath = await exportTexNote({
        title: form.title || selectedNote.title,
        contentLatex: form.contentLatex,
      });
      if (exportedPath) {
        setMessage(`Exported .tex file to ${exportedPath}.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Note export failed.");
    } finally {
      setExporting(false);
    }
  }

  function selectNote(note: Note) {
    setSelectedNote(note);
    setForm(noteToForm(note));
    setError(null);
    setMessage(null);
  }

  function startNewNote() {
    setSelectedNote(null);
    setForm(EMPTY_FORM);
    setError(null);
  }

  return (
    <div className="page-stack">
      <section className="page-intro">
        <p>
          Create and maintain LaTeX study notes in the app database. Notes can optionally be
          associated with a Library item, but they are not compiled, exported, or generated by AI.
        </p>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>LaTeX Notes</h2>
            <p>Plain LaTeX source notes with optional Library item context.</p>
          </div>
          <button type="button" onClick={startNewNote}>
            New note
          </button>
        </div>

        <div className="notes-workspace">
          <aside className="panel-subsection notes-list-panel">
            <div className="notes-list-header">
              <div>
                <h3>Notes</h3>
                <p className="muted">{loadingNotes ? "Loading notes..." : `${notes.length} active`}</p>
              </div>
            </div>

            <label>
              search
              <input
                value={searchKeyword}
                onChange={(event) => setSearchKeyword(event.target.value)}
                placeholder="Title or description"
              />
            </label>
            <div className="button-row">
              <button type="button" disabled={loadingNotes} onClick={() => loadNotes("list")}>
                {loadingNotes && lastMode === "list" ? "Loading..." : "List"}
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={loadingNotes}
                onClick={() => loadNotes("search")}
              >
                {loadingNotes && lastMode === "search" ? "Searching..." : "Search"}
              </button>
            </div>

            {notes.length === 0 ? (
              <p className="empty-state">
                {lastMode === "search"
                  ? "No active notes matched this search."
                  : "No active notes yet. Create a note to begin."}
              </p>
            ) : (
              <ul className="item-list notes-list">
                {notes.map((note) => (
                  <NoteListItem
                    key={note.id}
                    note={note}
                    selected={selectedNote?.id === note.id}
                    libraryItem={libraryItems.find((item) => item.id === note.library_item_id)}
                    onSelect={selectNote}
                  />
                ))}
              </ul>
            )}
          </aside>

          <form className="panel-subsection notes-editor" onSubmit={saveNote}>
            <div className="detail-header">
              <div>
                <h3>{selectedNote ? "Edit Note" : "New Note"}</h3>
                <p className="muted">
                  {selectedNote ? `id ${selectedNote.id}` : "Stored in PostgreSQL after saving."}
                </p>
              </div>
              {selectedNote && <span className="status-badge">{selectedNote.status}</span>}
            </div>

            <div className="form-grid">
              <label className="full-width">
                title
                <input
                  value={form.title}
                  onChange={(event) => setForm({ ...form, title: event.target.value })}
                />
              </label>
              <label className="full-width">
                description
                <input
                  value={form.description}
                  onChange={(event) =>
                    setForm({ ...form, description: event.target.value })
                  }
                />
              </label>
              <label>
                associated book
                <select
                  value={form.libraryItemId}
                  disabled={loadingLibrary}
                  onChange={(event) =>
                    setForm({ ...form, libraryItemId: event.target.value })
                  }
                >
                  <option value="">No associated book</option>
                  {libraryItems.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.title}
                      {item.author ? ` - ${item.author}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                topic_tags
                <input
                  value={form.topicTags}
                  onChange={(event) => setForm({ ...form, topicTags: event.target.value })}
                  placeholder="linear algebra, vector spaces"
                />
              </label>
              <label className="full-width">
                source_session_id
                <input
                  value={form.sourceSessionId}
                  onChange={(event) =>
                    setForm({ ...form, sourceSessionId: event.target.value })
                  }
                  placeholder="Optional chat session id"
                />
              </label>
              <label className="full-width">
                content_latex
                <textarea
                  className="latex-textarea"
                  rows={18}
                  value={form.contentLatex}
                  onChange={(event) =>
                    setForm({ ...form, contentLatex: event.target.value })
                  }
                />
              </label>
            </div>

            {associatedLibraryItem && (
              <p className="muted compact-note">
                Associated with {associatedLibraryItem.title}
                {associatedLibraryItem.author ? ` by ${associatedLibraryItem.author}` : ""}.
              </p>
            )}
            {selectedNote && (
              <p className="muted compact-note">
                Created {formatDate(selectedNote.created_at)} · Updated{" "}
                {formatDate(selectedNote.updated_at)}
              </p>
            )}
            {selectedNote && (
              <p className="muted compact-note">
                Export writes the current editor content to a local `.tex` file. Save first if you
                want the database note updated too.
              </p>
            )}
            {error && <p className="error compact-error">{error}</p>}
            {message && <p className="success">{message}</p>}

            <div className="button-row">
              <button type="submit" disabled={saving}>
                {saving ? "Saving..." : selectedNote ? "Save note" : "Create note"}
              </button>
              {selectedNote && (
                <button
                  type="button"
                  className="secondary-button"
                  disabled={archiving}
                  onClick={archiveSelectedNote}
                >
                  {archiving ? "Archiving..." : "Archive note"}
                </button>
              )}
              {selectedNote && (
                <button
                  type="button"
                  className="secondary-button"
                  disabled={exporting}
                  onClick={exportSelectedNote}
                >
                  {exporting ? "Exporting..." : "Export as .tex"}
                </button>
              )}
            </div>
          </form>
        </div>
      </section>
    </div>
  );
}

function NoteListItem({
  note,
  selected,
  libraryItem,
  onSelect,
}: {
  note: Note;
  selected: boolean;
  libraryItem?: LibraryItem;
  onSelect: (note: Note) => void;
}) {
  return (
    <li className={selected ? "library-list-item selected" : "library-list-item"}>
      <div className="item-title">
        <span>{note.title}</span>
        <span className="status-badge">{note.status}</span>
      </div>
      <p>{note.description || "No description."}</p>
      <small>
        {libraryItem ? `book ${libraryItem.title}` : "no associated book"} · tags{" "}
        {note.topic_tags?.length ? note.topic_tags.join(", ") : "none"} · updated{" "}
        {formatDate(note.updated_at)}
      </small>
      <div className="button-row item-actions">
        <button type="button" className="secondary-button" onClick={() => onSelect(note)}>
          {selected ? "Selected" : "Open"}
        </button>
      </div>
    </li>
  );
}

function noteToForm(note: Note) {
  return {
    title: note.title,
    description: note.description || "",
    contentLatex: note.content_latex,
    libraryItemId: note.library_item_id || "",
    sourceSessionId: note.source_session_id || "",
    topicTags: note.topic_tags?.join(", ") || "",
  };
}

function upsertNote(notes: Note[], saved: Note): Note[] {
  if (saved.status === "archived") {
    return notes.filter((note) => note.id !== saved.id);
  }
  if (notes.some((note) => note.id === saved.id)) {
    return notes.map((note) => (note.id === saved.id ? saved : note));
  }
  return [saved, ...notes];
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
  return new Date(value).toLocaleString();
}
