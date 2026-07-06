import type { AppPage } from "./AppLayout";

const NAV_ITEMS: Array<{ id: AppPage; label: string; description: string }> = [
  { id: "chat", label: "Chat", description: "RAG and memory tools" },
  { id: "library", label: "Library", description: "Book metadata" },
  { id: "notes", label: "Notes", description: "LaTeX workspace later" },
  { id: "progress", label: "Progress", description: "Learning timeline" },
];

export default function Sidebar({
  activePage,
  onNavigate,
}: {
  activePage: AppPage;
  onNavigate: (page: AppPage) => void;
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-mark">PLA</span>
        <div>
          <p>Personal Learning</p>
          <strong>Agent</strong>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Main workspace">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={item.id === activePage ? "nav-item active" : "nav-item"}
            aria-current={item.id === activePage ? "page" : undefined}
            onClick={() => onNavigate(item.id)}
          >
            <span>{item.label}</span>
            <small>{item.description}</small>
          </button>
        ))}
      </nav>
    </aside>
  );
}
