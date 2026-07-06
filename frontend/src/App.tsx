import { useState } from "react";
import AppLayout, { type AppPage } from "./components/AppLayout";
import ChatPage from "./pages/ChatPage";
import LibraryPage from "./pages/LibraryPage";
import NotesPage from "./pages/NotesPage";
import ProgressPage from "./pages/ProgressPage";

export default function App() {
  const [activePage, setActivePage] = useState<AppPage>("chat");

  return (
    <AppLayout activePage={activePage} onNavigate={setActivePage}>
      {activePage === "chat" && <ChatPage />}
      {activePage === "library" && <LibraryPage />}
      {activePage === "notes" && <NotesPage />}
      {activePage === "progress" && <ProgressPage />}
    </AppLayout>
  );
}
