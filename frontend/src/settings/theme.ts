import { useEffect, useState } from "react";

export type ThemePreference = "system" | "light" | "dark";

const THEME_KEY = "pla-theme";

export function readThemePreference(): ThemePreference {
  const value = localStorage.getItem(THEME_KEY);
  return value === "light" || value === "dark" ? value : "system";
}

export function applyTheme(preference: ThemePreference): void {
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const resolved =
    preference === "system" ? (systemDark ? "dark" : "light") : preference;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
}

export function useThemePreference(): [
  ThemePreference,
  (theme: ThemePreference) => void,
] {
  const [theme, setThemeState] = useState<ThemePreference>(readThemePreference);
  const setTheme = (value: ThemePreference) => {
    localStorage.setItem(THEME_KEY, value);
    setThemeState(value);
  };

  useEffect(() => {
    applyTheme(theme);
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = () => {
      if (theme === "system") applyTheme(theme);
    };
    media.addEventListener("change", handleChange);
    return () => media.removeEventListener("change", handleChange);
  }, [theme]);

  return [theme, setTheme];
}
