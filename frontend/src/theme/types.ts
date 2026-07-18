export type Theme = "light" | "dark";
export type ThemePreference = Theme | "system";

export interface ResolvedTheme {
  readonly preference: ThemePreference;
  readonly theme: Theme;
}
