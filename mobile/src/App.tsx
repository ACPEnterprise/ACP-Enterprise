import { useCallback, useEffect, useMemo, useState } from "react";
import { StatusBar } from "expo-status-bar";
import { Text } from "react-native";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Screen } from "./components/Screen";
import { readEnvironment } from "./config/environment";
import { AppNavigator } from "./navigation/AppNavigator";
import { INITIAL_CAPABILITIES } from "./permissions/capabilities";
import type { Capability } from "./permissions/capabilities";
import { SessionRepository } from "./auth/sessionRepository";
import { deviceProtectedStorage } from "./storage/secureStorage";
import { ApiClient } from "./api/client";
import { createTimekeepingService } from "./api/timekeeping";
import { getCapabilities } from "./api/authorization";
import { deviceNetworkMonitor } from "./network/networkMonitor";
import { safeLogger } from "./diagnostics/safeLogger";
import type { AppEnvironment } from "./config/environment";

export default function App() {
  const sessions = useMemo(() => new SessionRepository(deviceProtectedStorage), []);
  const [state, setState] = useState<"restoring" | "anonymous" | "authenticated" | "configuration_error">("restoring");
  const [environment, setEnvironment] = useState<AppEnvironment | null>(null);
  const expire = useCallback(() => setState("anonymous"), []);
  useEffect(() => { Promise.resolve().then(() => { const next = readEnvironment(); setEnvironment(next); return sessions.load(); }).then((session) => setState(session ? "authenticated" : "anonymous")).catch(() => setState("configuration_error")); }, [sessions]);
  if (state === "restoring") return <Screen><Text>Starting ACP Employee…</Text></Screen>;
  if (state === "configuration_error") return <Screen><Text accessibilityRole="alert">ACP Employee is not configured. Contact support.</Text></Screen>;
  if (!environment) return <Screen><Text>Starting ACP Employee…</Text></Screen>;
  return <RuntimeApp authenticated={state === "authenticated"} environment={environment} sessions={sessions} onExpired={expire} />;
}

function RuntimeApp({ authenticated, environment, sessions, onExpired }: { authenticated: boolean; environment: AppEnvironment; sessions: SessionRepository; onExpired(): void }) {
  const [capabilities, setCapabilities] = useState<readonly Capability[]>(INITIAL_CAPABILITIES);
  const client = useMemo(() => new ApiClient(environment.apiBaseUrl, sessions, deviceNetworkMonitor, safeLogger, onExpired), [environment.apiBaseUrl, onExpired, sessions]);
  const timekeeping = useMemo(() => createTimekeepingService(client), [client]);
  useEffect(() => { if (authenticated) void getCapabilities(client).then(setCapabilities).catch(() => setCapabilities(["home.view"])); }, [authenticated, client]);
  return <ErrorBoundary><StatusBar style="auto" /><AppNavigator authenticated={authenticated} capabilities={capabilities} timekeeping={timekeeping} network={deviceNetworkMonitor} /></ErrorBoundary>;
}
