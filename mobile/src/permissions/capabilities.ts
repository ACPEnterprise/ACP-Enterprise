export type Capability = "home.view" | "time.self.view" | "my_day.view" | "jobs.view" | "notifications.view" | "team_time.view";
export const INITIAL_CAPABILITIES: readonly Capability[] = ["home.view", "time.self.view"];
export function can(capabilities: readonly Capability[], capability: Capability): boolean { return capabilities.includes(capability); }
