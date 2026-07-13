import { getBackendBaseUrl } from "../api/config";
import type { ReactNode } from "react";
import Sidebar from "./Sidebar";

export type AppPage = "workspace" | "settings";

const PAGE_TITLES: Record<AppPage, string> = {
  workspace: "Repository + Chat",
  settings: "Settings",
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
      <main
        className={
          activePage === "workspace"
            ? "workspace-main workspace-main-wide"
            : "workspace-main"
        }
      >
        <header className="workspace-header">
          <div>
            <p className="eyebrow">Stage 64E</p>
            <h1>{PAGE_TITLES[activePage]}</h1>
          </div>
          <p className="backend-note">Backend: {getBackendBaseUrl()}</p>
        </header>
        {children}
      </main>
    </div>
  );
}
