import { MouseEvent, useEffect, useMemo, useRef, useState } from "react";
import { importLibraryPdfs, listLibraryItems } from "../api/client";
import type { LibraryItem } from "../api/types";
import {
  persistConversationState,
  pruneMissingLibraryItems,
  restoreConversationState,
  toggleSelectedLibraryItem,
} from "../chat/conversationState";
import RagQueryPanel from "../components/RagQueryPanel";
import { selectLocalPdfFiles } from "../tauri/filePicker";
import { openManagedLibraryPdf } from "../tauri/pdfOpener";
import {
  fileNameFromPath,
  pdfSupportLabel,
  workspaceStatusLabel,
} from "../utils/libraryFiles";

export default function WorkspacePage() {
  const [restoredConversation] = useState(restoreConversationState);
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [conversation, setConversation] = useState(restoredConversation.state);
  const [conversationWarning, setConversationWarning] = useState<string | null>(
    restoredConversation.warning,
  );
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [addingPdfs, setAddingPdfs] = useState(false);
  const [addPdfStatus, setAddPdfStatus] = useState<string | null>(null);
  const [addPdfError, setAddPdfError] = useState<string | null>(null);
  const [openPdfError, setOpenPdfError] = useState<string | null>(null);
  const clickTimerRef = useRef<number | null>(null);

  const selectedItems = useMemo(
    () =>
      conversation.selectedLibraryItemIds
        .map((id) => items.find((item) => item.id === id))
        .filter((item): item is LibraryItem => Boolean(item)),
    [conversation.selectedLibraryItemIds, items],
  );

  useEffect(() => {
    void loadLibrary();
  }, []);

  useEffect(() => {
    const warning = persistConversationState(conversation);
    if (warning) {
      setConversationWarning(warning);
    }
  }, [conversation]);

  useEffect(
    () => () => {
      if (clickTimerRef.current !== null) {
        window.clearTimeout(clickTimerRef.current);
      }
    },
    [],
  );

  async function loadLibrary() {
    setLoadingLibrary(true);
    setLibraryError(null);
    try {
      const response = await listLibraryItems({ limit: 100 });
      setItems(response.items);
      const availableIds = new Set(response.items.map((item) => item.id));
      setConversation((current) => {
        const pruned = pruneMissingLibraryItems(current, availableIds);
        if (pruned !== current) {
          setConversationWarning(
            "One or more selected PDFs no longer exist and were removed from context.",
          );
        }
        return pruned;
      });
    } catch (error) {
      setItems([]);
      setLibraryError(
        error instanceof Error
          ? error.message
          : "Could not load PDF Library items.",
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

      const importResponse = await importLibraryPdfs({
        source_paths: selectedPaths,
      });
      lastIndexedItem =
        importResponse.items[importResponse.items.length - 1]?.library_item ||
        null;

      const response = await listLibraryItems({ limit: 100 });
      setItems(response.items);
      if (lastIndexedItem) {
        setConversation((current) =>
          current.selectedLibraryItemIds.includes(lastIndexedItem.id)
            ? current
            : {
                ...current,
                selectedLibraryItemIds: [
                  ...current.selectedLibraryItemIds,
                  lastIndexedItem.id,
                ],
              },
        );
      }
      setAddPdfStatus(
        selectedPaths.length === 1
          ? "PDF indexed successfully."
          : `${selectedPaths.length} PDFs indexed successfully.`,
      );
    } catch (error) {
      setAddPdfError(
        error instanceof Error ? error.message : "Could not add PDFs.",
      );
      setAddPdfStatus("PDF indexing failed.");
      await loadLibrary();
    } finally {
      setAddingPdfs(false);
    }
  }

  function handleRepositoryClick(event: MouseEvent, itemId: string) {
    if (event.detail > 1) {
      if (clickTimerRef.current !== null) {
        window.clearTimeout(clickTimerRef.current);
        clickTimerRef.current = null;
      }
      return;
    }
    clickTimerRef.current = window.setTimeout(() => {
      setConversation((current) => toggleSelectedLibraryItem(current, itemId));
      clickTimerRef.current = null;
    }, 220);
  }

  async function handleRepositoryDoubleClick(item: LibraryItem) {
    if (clickTimerRef.current !== null) {
      window.clearTimeout(clickTimerRef.current);
      clickTimerRef.current = null;
    }
    setOpenPdfError(null);
    try {
      await openManagedLibraryPdf(item);
    } catch (error) {
      setOpenPdfError(
        error instanceof Error
          ? error.message
          : "The managed PDF could not be opened.",
      );
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
            <p
              className={
                addPdfError ? "error compact-error" : "success compact-success"
              }
            >
              {addPdfStatus}
            </p>
          )}
          {addPdfError && <p className="error compact-error">{addPdfError}</p>}
          {libraryError && (
            <p className="error compact-error">{libraryError}</p>
          )}
          {openPdfError && (
            <p className="error compact-error">{openPdfError}</p>
          )}
          {conversationWarning && (
            <p className="error compact-error">{conversationWarning}</p>
          )}

          {selectedItems.length > 0 ? (
            <div className="selected-context">
              <span className="field-label">
                Selected context ({selectedItems.length})
              </span>
              <div className="selected-book-list">
                {selectedItems.map((item) => (
                  <span className="selected-book-chip" key={item.id}>
                    {item.title}
                  </span>
                ))}
              </div>
              <small>
                Click a selected book again to remove it. Double-click to open.
              </small>
            </div>
          ) : null}

          {items.length === 0 ? (
            <p className="empty-state">
              {loadingLibrary
                ? "Loading PDF Repository..."
                : "No Library items found."}
            </p>
          ) : (
            <ul className="explorer-list" aria-label="PDF Repository items">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={
                      conversation.selectedLibraryItemIds.includes(item.id)
                        ? "explorer-item selected"
                        : "explorer-item"
                    }
                    aria-pressed={conversation.selectedLibraryItemIds.includes(
                      item.id,
                    )}
                    onClick={(event) => handleRepositoryClick(event, item.id)}
                    onDoubleClick={() => void handleRepositoryDoubleClick(item)}
                    title="Click to toggle Agent context; double-click to open PDF"
                  >
                    <span className="explorer-title">{item.title}</span>
                    <span className="explorer-meta">
                      {pdfSupportLabel(item)} ·{" "}
                      {workspaceStatusLabel(item.status)}
                    </span>
                    <span className="explorer-meta">
                      {workspaceFileLabel(item)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <main className="workspace-panel agent-chat-dock" tabIndex={-1}>
          <RagQueryPanel
            conversation={conversation}
            onConversationChange={setConversation}
            workspaceSelectedItems={selectedItems}
            libraryItems={items}
          />
        </main>
      </div>
    </div>
  );
}

function workspaceFileLabel(item: LibraryItem): string {
  const title = item.title.trim();
  return title.toLowerCase().endsWith(".pdf") ? title : `${title}.pdf`;
}
