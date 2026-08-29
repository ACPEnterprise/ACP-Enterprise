import { useEffect, useMemo, useState } from "react";
import { StatusBar } from "expo-status-bar";
import { Text } from "react-native";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Screen } from "./components/Screen";
import { readEnvironment } from "./config/environment";
import { AppNavigator } from "./navigation/AppNavigator";
import { INITIAL_CAPABILITIES } from "./permissions/capabilities";
import { SessionRepository } from "./auth/sessionRepository";
import { deviceProtectedStorage } from "./storage/secureStorage";

export default function App() {
  const sessions = useMemo(() => new SessionRepository(deviceProtectedStorage), []);
  const [state, setState] = useState<"restoring" | "anonymous" | "authenticated" | "configuration_error">("restoring");
  useEffect(() => { Promise.resolve().then(() => { readEnvironment(); return sessions.load(); }).then((session) => setState(session ? "authenticated" : "anonymous")).catch(() => setState("configuration_error")); }, [sessions]);
  if (state === "restoring") return <Screen><Text>Starting ACP Employee…</Text></Screen>;
  if (state === "configuration_error") return <Screen><Text accessibilityRole="alert">ACP Employee is not configured. Contact support.</Text></Screen>;
  return <ErrorBoundary><StatusBar style="auto" /><AppNavigator authenticated={state === "authenticated"} capabilities={INITIAL_CAPABILITIES} /></ErrorBoundary>;
}
