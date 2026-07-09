import { useState } from "react";
import AppLayout, { type AppPage } from "./components/AppLayout";
import WorkspacePage from "./pages/WorkspacePage";

export default function App() {
  const [activePage, setActivePage] = useState<AppPage>("workspace");

  return (
    <AppLayout activePage={activePage} onNavigate={setActivePage}>
      {activePage === "workspace" && <WorkspacePage />}
    </AppLayout>
  );
}
