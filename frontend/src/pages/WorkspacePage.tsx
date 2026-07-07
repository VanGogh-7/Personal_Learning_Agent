import { useEffect, useMemo, useState, type PointerEvent } from "react";
import { listLibraryItems } from "../api/client";
import type { LibraryItem } from "../api/types";
import PdfViewerPanel from "../components/PdfViewerPanel";
import RagQueryPanel from "../components/RagQueryPanel";
import { openLocalFile } from "../tauri/localFiles";
import {
  fileNameFromPath,
  pdfSupportLabel,
  workspaceStatusLabel,
} from "../utils/libraryFiles";

const LAYOUT_STORAGE_KEY = "pla.workspace.layout";
const MIN_LEFT_WIDTH = 220;
const MAX_LEFT_WIDTH = 420;
const MIN_RIGHT_WIDTH = 320;
const MAX_RIGHT_WIDTH = 620;

type WorkspaceLayoutState = {
  libraryVisible: boolean;
  chatVisible: boolean;
  libraryWidth: number;
  chatWidth: number;
};

const DEFAULT_LAYOUT: WorkspaceLayoutState = {
  libraryVisible: true,
  chatVisible: true,
  libraryWidth: 280,
  chatWidth: 420,
};

export default function WorkspacePage() {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [layout, setLayout] = useState<WorkspaceLayoutState>(() => loadLayoutState());
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);

  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedItemId) || null,
    [items, selectedItemId],
  );

  const gridTemplateColumns = [
    layout.libraryVisible ? `${layout.libraryWidth}px` : "",
    layout.libraryVisible ? "6px" : "",
    "minmax(0, 1fr)",
    layout.chatVisible ? "6px" : "",
    layout.chatVisible ? `${layout.chatWidth}px` : "",
  ]
    .filter(Boolean)
    .join(" ");

  useEffect(() => {
    void loadLibrary();
  }, []);

  useEffect(() => {
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layout));
  }, [layout]);

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

  async function openSelectedItem() {
    if (!selectedItem) {
      return;
    }

    setOpenError(null);
    setOpening(true);
    try {
      await openLocalFile(selectedItem.file_path || "");
    } catch (error) {
      setOpenError(error instanceof Error ? error.message : "Could not open local file.");
    } finally {
      setOpening(false);
    }
  }

  function toggleLibraryPanel() {
    setLayout((current) => ({ ...current, libraryVisible: !current.libraryVisible }));
  }

  function toggleChatPanel() {
    setLayout((current) => ({ ...current, chatVisible: !current.chatVisible }));
  }

  function startResize(side: "left" | "right", event: PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = side === "left" ? layout.libraryWidth : layout.chatWidth;

    function handlePointerMove(moveEvent: globalThis.PointerEvent) {
      const delta = moveEvent.clientX - startX;
      setLayout((current) => {
        if (side === "left") {
          return {
            ...current,
            libraryWidth: clamp(startWidth + delta, MIN_LEFT_WIDTH, MAX_LEFT_WIDTH),
          };
        }

        return {
          ...current,
          chatWidth: clamp(startWidth - delta, MIN_RIGHT_WIDTH, MAX_RIGHT_WIDTH),
        };
      });
    }

    function handlePointerUp() {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    }

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
  }

  return (
    <div className="workspace-page">
      <div className="workspace-toolbar" aria-label="Workspace panels">
        <button type="button" className="secondary-button" onClick={toggleLibraryPanel}>
          {layout.libraryVisible ? "Hide PDF Library" : "Show PDF Library"}
        </button>
        <button type="button" className="secondary-button" onClick={toggleChatPanel}>
          {layout.chatVisible ? "Hide Agent Chat" : "Show Agent Chat"}
        </button>
      </div>

      <div className="ide-workspace" style={{ gridTemplateColumns }}>
        {layout.libraryVisible && (
          <aside className="workspace-panel library-explorer">
            <div className="workspace-panel-header">
              <div>
                <h2>PDF Library</h2>
                <p>{items.length} PDF books</p>
              </div>
              <button
                type="button"
                className="secondary-button compact-button"
                disabled={loadingLibrary}
                onClick={loadLibrary}
              >
                {loadingLibrary ? "Loading" : "Reload"}
              </button>
            </div>

            {libraryError && <p className="error compact-error">{libraryError}</p>}

            {items.length === 0 ? (
              <p className="empty-state">
                {loadingLibrary ? "Loading PDF Library..." : "No Library items found."}
              </p>
            ) : (
              <ul className="explorer-list" aria-label="PDF Library items">
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={
                        selectedItem?.id === item.id
                          ? "explorer-item selected"
                          : "explorer-item"
                      }
                      onClick={() => {
                        setSelectedItemId(item.id);
                        setOpenError(null);
                      }}
                    >
                      <span className="explorer-title">{item.title}</span>
                      <span className="explorer-meta">
                        {pdfSupportLabel(item)} · {workspaceStatusLabel(item.status)}
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
        )}

        {layout.libraryVisible && (
          <div
            className="resize-handle"
            role="separator"
            aria-label="Resize PDF Library panel"
            aria-orientation="vertical"
            onPointerDown={(event) => startResize("left", event)}
          />
        )}

        <main className="workspace-panel pdf-workspace" tabIndex={-1}>
          <div className="workspace-panel-header">
            <div>
              <h2>PDF Workspace</h2>
              <p>{selectedItem ? "Selected PDF" : "No PDF selected"}</p>
            </div>
            {selectedItem?.file_path && (
              <button
                type="button"
                className="secondary-button"
                disabled={opening}
                onClick={openSelectedItem}
              >
                {opening ? "Opening..." : "Open in system PDF reader"}
              </button>
            )}
          </div>

          {selectedItem ? (
            <div className="pdf-placeholder selected">
              <h3>Selected PDF: {selectedItem.title}</h3>
              <dl className="detail-grid workspace-detail-grid">
                <div className="detail-row wide">
                  <dt>File</dt>
                  <dd className="mono-value">
                    {selectedItem.file_path || "No PDF file path"}
                  </dd>
                </div>
                <div className="detail-row">
                  <dt>Status</dt>
                  <dd>{workspaceStatusLabel(selectedItem.status)}</dd>
                </div>
                <div className="detail-row">
                  <dt>PDF support</dt>
                  <dd>{pdfSupportLabel(selectedItem)}</dd>
                </div>
              </dl>
              {openError && <p className="error compact-error">{openError}</p>}
              <PdfViewerPanel title={selectedItem.title} filePath={selectedItem.file_path} />
            </div>
          ) : (
            <div className="pdf-placeholder">
              <h3>No PDF selected.</h3>
              <p>Select a PDF from the Library Explorer.</p>
            </div>
          )}
        </main>

        {layout.chatVisible && (
          <div
            className="resize-handle"
            role="separator"
            aria-label="Resize Agent Chat panel"
            aria-orientation="vertical"
            onPointerDown={(event) => startResize("right", event)}
          />
        )}

        {layout.chatVisible && (
          <aside className="workspace-panel agent-chat-dock">
            <RagQueryPanel workspaceSelectedItem={selectedItem} />
          </aside>
        )}
      </div>
    </div>
  );
}

function loadLayoutState(): WorkspaceLayoutState {
  try {
    const stored = localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (!stored) {
      return DEFAULT_LAYOUT;
    }

    const parsed = JSON.parse(stored) as Partial<WorkspaceLayoutState>;
    return {
      libraryVisible: parsed.libraryVisible ?? DEFAULT_LAYOUT.libraryVisible,
      chatVisible: parsed.chatVisible ?? DEFAULT_LAYOUT.chatVisible,
      libraryWidth: clamp(
        parsed.libraryWidth ?? DEFAULT_LAYOUT.libraryWidth,
        MIN_LEFT_WIDTH,
        MAX_LEFT_WIDTH,
      ),
      chatWidth: clamp(
        parsed.chatWidth ?? DEFAULT_LAYOUT.chatWidth,
        MIN_RIGHT_WIDTH,
        MAX_RIGHT_WIDTH,
      ),
    };
  } catch {
    return DEFAULT_LAYOUT;
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function workspaceFileLabel(item: LibraryItem): string {
  if (!item.file_path) {
    return "No PDF file path";
  }
  return fileNameFromPath(item.file_path) || item.file_path;
}
