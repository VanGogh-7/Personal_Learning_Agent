import { useState } from "react";
import WorkspacePage from "./pages/WorkspacePage";
import SettingsPage from "./pages/SettingsPage";
import { useThemePreference } from "./settings/theme";
import { useDensityPreference } from "./settings/density";

type AppPage = "workspace" | "settings";

export default function App() {
  const [activePage, setActivePage] = useState<AppPage>("workspace");
  const [theme, setTheme] = useThemePreference();
  const [density, setDensity] = useDensityPreference();

  if (activePage === "settings") {
    return (
      <SettingsPage
        theme={theme}
        density={density}
        onThemeChange={setTheme}
        onDensityChange={setDensity}
        onBack={() => setActivePage("workspace")}
      />
    );
  }
  return <WorkspacePage onOpenSettings={() => setActivePage("settings")} />;
}
