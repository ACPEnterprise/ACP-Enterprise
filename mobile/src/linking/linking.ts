export const linking = {
  prefixes: ["acpemployee://", "https://employee.acpenterprise.com"],
  config: { screens: { Activation: { path: "activate", parse: { token: (value: string) => value } }, SignIn: "sign-in", App: { screens: { Home: "home", Time: "time" } } } },
};
export function isActivationLink(url: string): boolean { try { const parsed = new URL(url); return parsed.pathname === "/activate" && parsed.searchParams.has("token"); } catch { return false; } }
