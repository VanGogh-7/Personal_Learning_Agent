import type { LibraryItem } from "../api/types";

export default function ChatHeader({
  title,
  status,
  selectedItems,
  sidebarCollapsed,
  onOpenSidebar,
  onNewChat,
  onToggleContext,
}: {
  title: string;
  status: string;
  selectedItems: LibraryItem[];
  sidebarCollapsed: boolean;
  onOpenSidebar: () => void;
  onNewChat: () => void;
  onToggleContext: () => void;
}) {
  return (
    <>
      <header className="chat-header">
        <div className="chat-header-leading">
          <button
            type="button"
            className="icon-button mobile-menu-button"
            aria-label="Open navigation"
            onClick={onOpenSidebar}
          >
            ☰
          </button>
          {sidebarCollapsed && <span className="desktop-sidebar-spacer" />}
          <div>
            <h1>{title}</h1>
            <p>
              <span className="live-status-dot" aria-hidden="true" />
              {status}
            </p>
          </div>
        </div>
        <div className="chat-header-actions">
          <button
            type="button"
            className="secondary-button header-button"
            aria-label="New conversation from header"
            onClick={onNewChat}
          >
            New Chat
          </button>
          <button
            type="button"
            className="secondary-button header-button"
            aria-label="Toggle context panel"
            onClick={onToggleContext}
          >
            Context
          </button>
        </div>
      </header>
      <div className="selected-context-bar" aria-label="Selected context">
        <span className="context-label">Context</span>
        {selectedItems.length ? (
          selectedItems.map((item) => (
            <span className="context-chip" key={item.id}>
              {item.title}
            </span>
          ))
        ) : (
          <span className="context-empty-label">No books selected</span>
        )}
      </div>
    </>
  );
}
