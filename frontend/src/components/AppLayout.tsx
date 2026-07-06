import { getBackendBaseUrl } from "../api/config";
import type { ReactNode } from "react";
import Sidebar from "./Sidebar";

export type AppPage = "chat" | "library" | "notes" | "progress";

const PAGE_TITLES: Record<AppPage, string> = {
  chat: "Chat",
  library: "Library",
  notes: "Notes",
  progress: "Progress",
};

export default function AppLayout({
  activePage,
  onNavigate,
  children,
}: {
  activePage: AppPage;
  onNavigate: (page: AppPage) => void;
  children: ReactNode;
}) {
  return (
    <div className="workspace-shell">
      <Sidebar activePage={activePage} onNavigate={onNavigate} />
      <main className="workspace-main">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">Stage 24</p>
            <h1>{PAGE_TITLES[activePage]}</h1>
          </div>
          <p className="backend-note">Backend: {getBackendBaseUrl()}</p>
        </header>
        {children}
      </main>
    </div>
  );
}
