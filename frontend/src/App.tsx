import { useState } from "react";
import AppLayout, { type AppPage } from "./components/AppLayout";
import ChatPage from "./pages/ChatPage";
import LibraryPage from "./pages/LibraryPage";
import NotesPage from "./pages/NotesPage";
import ProgressPage from "./pages/ProgressPage";
import WorkspacePage from "./pages/WorkspacePage";

export default function App() {
  const [activePage, setActivePage] = useState<AppPage>("workspace");

  return (
    <AppLayout activePage={activePage} onNavigate={setActivePage}>
      {activePage === "workspace" && <WorkspacePage />}
      {activePage === "chat" && <ChatPage />}
      {activePage === "library" && <LibraryPage />}
      {activePage === "notes" && <NotesPage />}
      {activePage === "progress" && <ProgressPage />}
    </AppLayout>
  );
}
