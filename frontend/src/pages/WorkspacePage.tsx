import { type MouseEvent, useEffect, useMemo, useRef, useState } from "react";
import { importLibraryPdfs, listLibraryItems } from "../api/client";
import type { LibraryItem } from "../api/types";
import {
  pruneMissingLibraryItems,
  toggleSelectedLibraryItem,
  type ConversationState,
} from "../chat/conversationState";
import {
  activeConversation,
  persistConversationWorkspace,
  restoreConversationWorkspace,
  selectConversation,
  startNewConversation,
  updateActiveConversation,
  updateConversationEntry,
} from "../chat/conversationWorkspace";
import RagQueryPanel from "../components/RagQueryPanel";
import Sidebar from "../components/Sidebar";
import { selectLocalPdfFiles } from "../tauri/filePicker";
import { openManagedLibraryPdf } from "../tauri/pdfOpener";
import { fileNameFromPath } from "../utils/libraryFiles";

export default function WorkspacePage({
  onOpenSettings = () => undefined,
}: {
  onOpenSettings?: () => void;
}) {
  const [restored] = useState(restoreConversationWorkspace);
  const [workspace, setWorkspace] = useState(restored.workspace);
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [warning, setWarning] = useState<string | null>(restored.warning);
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [addingPdfs, setAddingPdfs] = useState(false);
  const [libraryNotice, setLibraryNotice] = useState<string | null>(null);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [providerReady, setProviderReady] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const clickTimerRef = useRef<number | null>(null);
  const current = activeConversation(workspace);

  const selectedItems = useMemo(
    () =>
      current.state.selectedLibraryItemIds
        .map((id) => items.find((item) => item.id === id))
        .filter((item): item is LibraryItem => Boolean(item)),
    [current.state.selectedLibraryItemIds, items],
  );

  useEffect(() => {
    void loadLibrary();
  }, []);

  useEffect(() => {
    const persistenceWarning = persistConversationWorkspace(workspace);
    if (persistenceWarning) setWarning(persistenceWarning);
  }, [workspace]);

  useEffect(
    () => () => {
      if (clickTimerRef.current !== null)
        window.clearTimeout(clickTimerRef.current);
    },
    [],
  );

  async function loadLibrary() {
    setLoadingLibrary(true);
    setLibraryError(null);
    try {
      const response = await listLibraryItems({ limit: 100 });
      setItems(response.items);
      setProviderReady(true);
      const availableIds = new Set(response.items.map((item) => item.id));
      setWorkspace((value) => ({
        ...value,
        conversations: value.conversations.map((entry) => ({
          ...entry,
          state: pruneMissingLibraryItems(entry.state, availableIds),
        })),
      }));
    } catch (error) {
      setItems([]);
      setProviderReady(false);
      setLibraryError(
        error instanceof Error
          ? error.message
          : "Could not load the PDF Repository.",
      );
    } finally {
      setLoadingLibrary(false);
    }
  }

  async function addPdfs() {
    setLibraryError(null);
    setLibraryNotice(null);
    setAddingPdfs(true);
    try {
      const selectedPaths = await selectLocalPdfFiles();
      if (!selectedPaths.length) return;
      setLibraryNotice(
        selectedPaths.length === 1
          ? `Indexing ${fileNameFromPath(selectedPaths[0])}`
          : `Indexing ${selectedPaths.length} PDFs`,
      );
      const imported = await importLibraryPdfs({ source_paths: selectedPaths });
      const response = await listLibraryItems({ limit: 100 });
      setItems(response.items);
      const last = imported.items[imported.items.length - 1]?.library_item;
      if (last) {
        setWorkspace((value) =>
          updateActiveConversation(value, (state) =>
            state.selectedLibraryItemIds.includes(last.id)
              ? state
              : {
                  ...state,
                  selectedLibraryItemIds: [
                    ...state.selectedLibraryItemIds,
                    last.id,
                  ],
                },
          ),
        );
      }
      setLibraryNotice(
        `${selectedPaths.length} PDF${selectedPaths.length === 1 ? "" : "s"} indexed successfully.`,
      );
    } catch (error) {
      setLibraryError(
        error instanceof Error ? error.message : "Could not add PDFs.",
      );
      await loadLibrary();
    } finally {
      setAddingPdfs(false);
    }
  }

  function updateConversation(
    update:
      ConversationState | ((state: ConversationState) => ConversationState),
  ) {
    const conversationKey = current.key;
    setWorkspace((value) =>
      updateConversationEntry(value, conversationKey, update),
    );
  }

  function handleRepositoryClick(event: MouseEvent, itemId: string) {
    if (event.detail > 1) {
      if (clickTimerRef.current !== null)
        window.clearTimeout(clickTimerRef.current);
      clickTimerRef.current = null;
      return;
    }
    clickTimerRef.current = window.setTimeout(() => {
      setWorkspace((value) =>
        updateActiveConversation(value, (state) =>
          toggleSelectedLibraryItem(state, itemId),
        ),
      );
      clickTimerRef.current = null;
    }, 220);
  }

  async function openPdf(item: LibraryItem) {
    if (clickTimerRef.current !== null)
      window.clearTimeout(clickTimerRef.current);
    clickTimerRef.current = null;
    setLibraryError(null);
    try {
      await openManagedLibraryPdf(item);
    } catch (error) {
      setLibraryError(
        error instanceof Error
          ? error.message
          : "The managed PDF could not be opened.",
      );
    }
  }

  function newChat() {
    setWorkspace((value) => startNewConversation(value));
    setMobileSidebarOpen(false);
  }

  return (
    <div className={`app-shell${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
      <Sidebar
        collapsed={sidebarCollapsed}
        mobileOpen={mobileSidebarOpen}
        conversations={workspace.conversations}
        activeConversationKey={workspace.activeKey}
        items={items}
        selectedItemIds={current.state.selectedLibraryItemIds}
        loadingLibrary={loadingLibrary}
        addingPdfs={addingPdfs}
        healthLabel={providerReady ? "Ready" : "Check settings"}
        onToggleCollapsed={() => setSidebarCollapsed((value) => !value)}
        onCloseMobile={() => setMobileSidebarOpen(false)}
        onNewChat={newChat}
        onSelectConversation={(key) => {
          setWorkspace((value) => selectConversation(value, key));
          setMobileSidebarOpen(false);
        }}
        onRepositoryClick={handleRepositoryClick}
        onRepositoryDoubleClick={(item) => void openPdf(item)}
        onAddPdfs={() => void addPdfs()}
        onReload={() => void loadLibrary()}
        onOpenSettings={onOpenSettings}
      />
      <div className="workspace-content">
        {(warning || libraryNotice || libraryError) && (
          <div
            className={`workspace-toast${libraryError ? " error" : ""}`}
            role="status"
          >
            {libraryError || warning || libraryNotice}
            <button
              type="button"
              aria-label="Dismiss notification"
              onClick={() => {
                setWarning(null);
                setLibraryNotice(null);
                setLibraryError(null);
              }}
            >
              ×
            </button>
          </div>
        )}
        <RagQueryPanel
          key={current.key}
          conversation={current.state}
          onConversationChange={updateConversation}
          workspaceSelectedItems={selectedItems}
          libraryItems={items}
          conversationTitle={current.title}
          currentModel="Configured in Settings"
          sidebarCollapsed={sidebarCollapsed}
          onNewChat={newChat}
          onOpenSidebar={() => setMobileSidebarOpen(true)}
        />
      </div>
    </div>
  );
}
