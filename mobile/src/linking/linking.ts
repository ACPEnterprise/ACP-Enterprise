export const linking = {
  prefixes: ["acpemployee://", "https://employee.acpenterprise.com"],
  config: { screens: { Activation: { path: "activate", parse: { token: (value: string) => value } }, SignIn: "sign-in", App: { screens: { Home: "home", Time: "time" } } } },
};
export function isActivationLink(url: string): boolean {
  try {
    const parsed = new URL(url);
    const trusted = (parsed.protocol === "https:" && parsed.hostname === "employee.acpenterprise.com") || parsed.protocol === "acpemployee:";
    const route = parsed.protocol === "acpemployee:" ? parsed.hostname === "activate" || parsed.pathname === "/activate" : parsed.pathname === "/activate";
    return trusted && route && Boolean(parsed.searchParams.get("token")?.trim());
  } catch { return false; }
}

/** Extracts an invitation only after host/path validation. The value must remain memory-only. */
export function activationTokenFromLink(url: string): string | null {
  if (!isActivationLink(url)) return null;
  try { return new URL(url).searchParams.get("token")?.trim() || null; } catch { return null; }
}
