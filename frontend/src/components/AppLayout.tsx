import { getBackendBaseUrl } from "../api/config";
import type { ReactNode } from "react";
import Sidebar from "./Sidebar";

export type AppPage = "chat" | "library" | "notes";

const PAGE_TITLES: Record<AppPage, string> = {
  chat: "Chat",
  library: "Library",
  notes: "Notes",
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
            <p className="eyebrow">Stage 19</p>
            <h1>{PAGE_TITLES[activePage]}</h1>
          </div>
          <p className="backend-note">Backend: {getBackendBaseUrl()}</p>
        </header>
        {children}
      </main>
    </div>
  );
}
