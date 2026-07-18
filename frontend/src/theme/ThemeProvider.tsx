import { useEffect, useState, type ReactNode } from "react";

import type { Theme, ThemePreference } from "./types";

const systemThemeQuery = "(prefers-color-scheme: light)";

function resolveTheme(preference: ThemePreference): Theme {
  if (preference !== "system") {
    return preference;
  }
  return window.matchMedia(systemThemeQuery).matches ? "light" : "dark";
}

interface ThemeProviderProps {
  readonly children: ReactNode;
  readonly preference: ThemePreference;
}

export function ThemeProvider({
  children,
  preference,
}: ThemeProviderProps) {
  const [theme, setTheme] = useState<Theme>(() => resolveTheme(preference));

  useEffect(() => {
    const media = window.matchMedia(systemThemeQuery);
    const updateTheme = () => setTheme(resolveTheme(preference));
    updateTheme();

    if (preference !== "system") {
      return undefined;
    }
    media.addEventListener("change", updateTheme);
    return () => media.removeEventListener("change", updateTheme);
  }, [preference]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.dataset.themePreference = preference;
  }, [preference, theme]);

  return children;
}
