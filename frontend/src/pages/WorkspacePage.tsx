import { useEffect, useMemo, useState } from "react";
import {
  importLibraryPdfs,
  listLibraryItems,
} from "../api/client";
import type { LibraryItem } from "../api/types";
import RagQueryPanel from "../components/RagQueryPanel";
import { selectLocalPdfFiles } from "../tauri/filePicker";
import {
  fileNameFromPath,
  pdfSupportLabel,
  workspaceStatusLabel,
} from "../utils/libraryFiles";

export default function WorkspacePage() {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [addingPdfs, setAddingPdfs] = useState(false);
  const [addPdfStatus, setAddPdfStatus] = useState<string | null>(null);
  const [addPdfError, setAddPdfError] = useState<string | null>(null);

  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedItemId) || null,
    [items, selectedItemId],
  );

  useEffect(() => {
    void loadLibrary();
  }, []);

  async function loadLibrary() {
    setLoadingLibrary(true);
    setLibraryError(null);
    try {
      const response = await listLibraryItems({ limit: 100 });
      setItems(response.items);
      setSelectedItemId((current) =>
        current && response.items.some((item) => item.id === current) ? current : null,
      );
    } catch (error) {
      setItems([]);
      setSelectedItemId(null);
      setLibraryError(
        error instanceof Error ? error.message : "Could not load PDF Library items.",
      );
    } finally {
      setLoadingLibrary(false);
    }
  }

  async function addPdfs() {
    setAddPdfError(null);
    setAddPdfStatus(null);
    setAddingPdfs(true);

    try {
      const selectedPaths = await selectLocalPdfFiles();
      if (selectedPaths.length === 0) {
        return;
      }

      let lastIndexedItem: LibraryItem | null = null;
      setAddPdfStatus(
        selectedPaths.length === 1
          ? `Indexing ${fileNameFromPath(selectedPaths[0])}`
          : `Indexing ${selectedPaths.length} PDFs`,
      );

      const importResponse = await importLibraryPdfs({ source_paths: selectedPaths });
      lastIndexedItem =
        importResponse.items[importResponse.items.length - 1]?.library_item || null;

      const response = await listLibraryItems({ limit: 100 });
      setItems(response.items);
      if (lastIndexedItem) {
        setSelectedItemId(lastIndexedItem.id);
      }
      setAddPdfStatus(
        selectedPaths.length === 1
          ? "PDF indexed successfully."
          : `${selectedPaths.length} PDFs indexed successfully.`,
      );
    } catch (error) {
      setAddPdfError(error instanceof Error ? error.message : "Could not add PDFs.");
      setAddPdfStatus("PDF indexing failed.");
      await loadLibrary();
    } finally {
      setAddingPdfs(false);
    }
  }

  return (
    <div className="workspace-page">
      <div className="ide-workspace repository-chat-workspace">
        <aside className="workspace-panel library-explorer">
          <div className="workspace-panel-header">
            <div>
              <h2>PDF Repository</h2>
              <p>{items.length} PDF books</p>
            </div>
            <div className="button-row">
              <button
                type="button"
                className="compact-button"
                disabled={addingPdfs}
                onClick={addPdfs}
              >
                {addingPdfs ? "Adding..." : "Add PDFs"}
              </button>
              <button
                type="button"
                className="secondary-button compact-button"
                disabled={loadingLibrary || addingPdfs}
                onClick={loadLibrary}
              >
                {loadingLibrary ? "Loading" : "Reload"}
              </button>
            </div>
          </div>

          {addPdfStatus && (
            <p className={addPdfError ? "error compact-error" : "success compact-success"}>
              {addPdfStatus}
            </p>
          )}
          {addPdfError && <p className="error compact-error">{addPdfError}</p>}
          {libraryError && <p className="error compact-error">{libraryError}</p>}

          {selectedItem ? (
            <div className="selected-context">
              <span className="field-label">Selected context</span>
              <strong>{selectedItem.title}</strong>
              <small>
                {pdfSupportLabel(selectedItem)} · {workspaceStatusLabel(selectedItem.status)} ·{" "}
                {workspaceFileLabel(selectedItem)}
              </small>
            </div>
          ) : null}

          {items.length === 0 ? (
            <p className="empty-state">
              {loadingLibrary ? "Loading PDF Repository..." : "No Library items found."}
            </p>
          ) : (
            <ul className="explorer-list" aria-label="PDF Repository items">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={
                      selectedItem?.id === item.id
                        ? "explorer-item selected"
                        : "explorer-item"
                    }
                    aria-pressed={selectedItem?.id === item.id}
                    onClick={() => setSelectedItemId(item.id)}
                  >
                    <span className="explorer-title">{item.title}</span>
                    <span className="explorer-meta">
                      {pdfSupportLabel(item)} · {workspaceStatusLabel(item.status)}
                    </span>
                    <span className="explorer-meta">{workspaceFileLabel(item)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <main className="workspace-panel agent-chat-dock" tabIndex={-1}>
          <RagQueryPanel workspaceSelectedItem={selectedItem} />
        </main>
      </div>
    </div>
  );
}

function workspaceFileLabel(item: LibraryItem): string {
  const title = item.title.trim();
  if (title) {
    return title.toLowerCase().endsWith(".pdf") ? title : `${title}.pdf`;
  }
  if (!item.file_path) {
    return "No PDF file path";
  }
  return fileNameFromPath(item.file_path) || item.file_path;
}
