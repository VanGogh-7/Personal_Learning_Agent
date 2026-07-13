import { useState, type MouseEvent } from "react";
import type { LibraryItem } from "../api/types";
import type { ConversationEntry } from "../chat/conversationWorkspace";
import { pdfSupportLabel, workspaceStatusLabel } from "../utils/libraryFiles";

export default function Sidebar({
  collapsed,
  mobileOpen,
  conversations,
  activeConversationKey,
  items,
  selectedItemIds,
  loadingLibrary,
  addingPdfs,
  healthLabel,
  onToggleCollapsed,
  onCloseMobile,
  onNewChat,
  onSelectConversation,
  onRepositoryClick,
  onRepositoryDoubleClick,
  onAddPdfs,
  onReload,
  onOpenSettings,
}: {
  collapsed: boolean;
  mobileOpen: boolean;
  conversations: ConversationEntry[];
  activeConversationKey: string;
  items: LibraryItem[];
  selectedItemIds: string[];
  loadingLibrary: boolean;
  addingPdfs: boolean;
  healthLabel: string;
  onToggleCollapsed: () => void;
  onCloseMobile: () => void;
  onNewChat: () => void;
  onSelectConversation: (key: string) => void;
  onRepositoryClick: (event: MouseEvent, itemId: string) => void;
  onRepositoryDoubleClick: (item: LibraryItem) => void;
  onAddPdfs: () => void;
  onReload: () => void;
  onOpenSettings: () => void;
}) {
  const [conversationsOpen, setConversationsOpen] = useState(true);
  const [repositoryOpen, setRepositoryOpen] = useState(true);
  const selectedItems = items.filter((item) =>
    selectedItemIds.includes(item.id),
  );

  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={onCloseMobile}
        />
      )}
      <aside
        className={`app-sidebar${collapsed ? " collapsed" : ""}${mobileOpen ? " mobile-open" : ""}`}
        aria-label="Workspace navigation"
      >
        <div className="sidebar-brand-row">
          <button
            type="button"
            className="brand-button"
            aria-label="Personal Learning Agent"
            onClick={onCloseMobile}
          >
            <span className="brand-mark">PLA</span>
            <span className="brand-copy">
              <strong>Personal Learning Agent</strong>
              <small>Academic workspace</small>
            </span>
          </button>
          <button
            type="button"
            className="icon-button sidebar-collapse-button"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
            onClick={onToggleCollapsed}
          >
            <span aria-hidden="true">{collapsed ? "›" : "‹"}</span>
          </button>
        </div>

        <button type="button" className="new-chat-button" onClick={onNewChat}>
          <span aria-hidden="true">＋</span>
          <span className="sidebar-label">New Chat</span>
        </button>

        <div className="sidebar-scroll">
          <SidebarSection
            label="Conversations"
            count={conversations.length}
            open={conversationsOpen}
            collapsed={collapsed}
            onToggle={() => setConversationsOpen((value) => !value)}
          >
            <ul className="sidebar-list conversation-list">
              {conversations.map((conversation) => (
                <li key={conversation.key}>
                  <button
                    type="button"
                    className={
                      conversation.key === activeConversationKey
                        ? "sidebar-list-item active"
                        : "sidebar-list-item"
                    }
                    aria-current={
                      conversation.key === activeConversationKey
                        ? "true"
                        : undefined
                    }
                    onClick={() => onSelectConversation(conversation.key)}
                    title={conversation.title}
                  >
                    <span className="item-glyph" aria-hidden="true">
                      ◫
                    </span>
                    <span className="sidebar-item-copy">
                      <strong>{conversation.title}</strong>
                      <small>
                        {conversation.state.messages.length} turn
                        {conversation.state.messages.length === 1 ? "" : "s"}
                      </small>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </SidebarSection>

          <SidebarSection
            label="Repository"
            count={items.length}
            open={repositoryOpen}
            collapsed={collapsed}
            actions={
              <>
                <button
                  type="button"
                  className="section-action"
                  disabled={addingPdfs}
                  aria-label="Add PDFs"
                  onClick={onAddPdfs}
                >
                  ＋
                </button>
                <button
                  type="button"
                  className="section-action"
                  disabled={loadingLibrary || addingPdfs}
                  aria-label="Reload Repository"
                  onClick={onReload}
                >
                  ↻
                </button>
              </>
            }
            onToggle={() => setRepositoryOpen((value) => !value)}
          >
            {items.length ? (
              <ul
                className="sidebar-list repository-list"
                aria-label="PDF Repository items"
              >
                {items.map((item) => {
                  const selected = selectedItemIds.includes(item.id);
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        className={
                          selected
                            ? "sidebar-list-item repository-item selected"
                            : "sidebar-list-item repository-item"
                        }
                        aria-pressed={selected}
                        onClick={(event) => onRepositoryClick(event, item.id)}
                        onDoubleClick={() => onRepositoryDoubleClick(item)}
                        title="Click to toggle context; double-click to open PDF"
                      >
                        <span className="item-glyph" aria-hidden="true">
                          ▤
                        </span>
                        <span className="sidebar-item-copy">
                          <strong>{item.title}</strong>
                          <small>
                            {pdfSupportLabel(item)} ·{" "}
                            {workspaceStatusLabel(item.status)}
                          </small>
                        </span>
                        {selected && (
                          <span className="selection-mark" aria-hidden="true">
                            ✓
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="sidebar-empty">
                {loadingLibrary ? "Loading Repository…" : "No PDFs imported"}
              </p>
            )}
          </SidebarSection>

          <SidebarSection
            label="Selected Books"
            count={selectedItems.length}
            open
            collapsed={collapsed}
          >
            {selectedItems.length ? (
              <div className="sidebar-selected-books">
                {selectedItems.map((item) => (
                  <span
                    className="selected-book-chip"
                    title={item.title}
                    key={item.id}
                  >
                    <span>{item.title}</span>
                  </span>
                ))}
              </div>
            ) : (
              <p className="sidebar-empty">No books selected</p>
            )}
          </SidebarSection>
        </div>

        <div className="sidebar-footer">
          <button
            type="button"
            className="sidebar-footer-button"
            onClick={onOpenSettings}
          >
            <span className="item-glyph" aria-hidden="true">
              ⚙
            </span>
            <span className="sidebar-label">Settings</span>
          </button>
          <div
            className="health-row"
            title={`Backend ${healthLabel}; Provider and MCP tools are backend managed`}
          >
            <span
              className={`health-dot ${healthLabel === "Ready" ? "ready" : "warning"}`}
            />
            <span className="sidebar-label">Provider / MCP · Managed</span>
          </div>
          <div className="version-row">
            <span className="sidebar-label">PLA Desktop</span>
            <small>v0.1.0</small>
          </div>
        </div>
      </aside>
    </>
  );
}

function SidebarSection({
  label,
  count,
  open,
  collapsed,
  actions,
  onToggle,
  children,
}: {
  label: string;
  count: number;
  open: boolean;
  collapsed: boolean;
  actions?: React.ReactNode;
  onToggle?: () => void;
  children: React.ReactNode;
}) {
  if (collapsed) return null;
  return (
    <section className="sidebar-section">
      <div className="sidebar-section-heading">
        <button
          type="button"
          className="section-toggle"
          aria-expanded={open}
          onClick={onToggle}
          disabled={!onToggle}
        >
          <span aria-hidden="true">{open ? "▾" : "▸"}</span>
          <span>{label}</span>
          <span className="section-count">{count}</span>
        </button>
        {actions && <div className="section-actions">{actions}</div>}
      </div>
      {open && children}
    </section>
  );
}
