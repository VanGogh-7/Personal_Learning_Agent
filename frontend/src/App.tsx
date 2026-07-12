import { useState } from "react";
import AppLayout, { type AppPage } from "./components/AppLayout";
import WorkspacePage from "./pages/WorkspacePage";
import SettingsPage from "./pages/SettingsPage";
import { useThemePreference } from "./settings/theme";

export default function App() {
  const [activePage, setActivePage] = useState<AppPage>("workspace");
  const [theme, setTheme] = useThemePreference();

  return (
    <AppLayout activePage={activePage} onNavigate={setActivePage}>
      {activePage === "workspace" && <WorkspacePage />}
      {activePage === "settings" && (
        <SettingsPage theme={theme} onThemeChange={setTheme} />
      )}
    </AppLayout>
  );
}
