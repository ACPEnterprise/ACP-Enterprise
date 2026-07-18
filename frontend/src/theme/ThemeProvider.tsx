import {
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { Theme, ThemePreference } from "./types";
import { ThemeContext } from "./useTheme";

const systemThemeQuery = "(prefers-color-scheme: light)";
const storageKey = "acp-theme-preference";

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

function savedPreference(fallback: ThemePreference): ThemePreference {
  const saved = window.localStorage.getItem(storageKey);
  return saved === "light" || saved === "dark" || saved === "system"
    ? saved
    : fallback;
}

export function ThemeProvider({
  children,
  preference,
}: ThemeProviderProps) {
  const [activePreference, setPreference] = useState<ThemePreference>(() =>
    savedPreference(preference),
  );
  const [theme, setTheme] = useState<Theme>(() => resolveTheme(activePreference));

  useEffect(() => {
    const media = window.matchMedia(systemThemeQuery);
    const updateTheme = () => setTheme(resolveTheme(activePreference));
    updateTheme();

    if (activePreference !== "system") {
      return undefined;
    }
    media.addEventListener("change", updateTheme);
    return () => media.removeEventListener("change", updateTheme);
  }, [activePreference]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.dataset.themePreference = activePreference;
    window.localStorage.setItem(storageKey, activePreference);
  }, [activePreference, theme]);

  const value = useMemo(
    () => ({ preference: activePreference, theme, setPreference }),
    [activePreference, theme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
