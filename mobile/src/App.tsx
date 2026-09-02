import { useCallback, useEffect, useMemo, useState } from "react";
import { StatusBar } from "expo-status-bar";
import { AppState, Text } from "react-native";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { PrimaryButton } from "./components/PrimaryButton";
import { Screen } from "./components/Screen";
import { readEnvironment } from "./config/environment";
import { AppNavigator } from "./navigation/AppNavigator";
import type { Capability } from "./permissions/capabilities";
import { SessionRepository } from "./auth/sessionRepository";
import { AuthenticationCoordinator } from "./auth/authenticationCoordinator";
import type { EstablishedState } from "./auth/authenticationCoordinator";
import { deviceProtectedStorage } from "./storage/secureStorage";
import { ApiClient } from "./api/client";
import { createTimekeepingService } from "./api/timekeeping";
import { createEmployeeOperationsService } from "./api/employeeOperations";
import { createFieldService } from "./api/fieldService";
import { deviceNetworkMonitor } from "./network/networkMonitor";
import { safeLogger } from "./diagnostics/safeLogger";
import { RestrictedStateScreen } from "./screens/RestrictedStateScreen";
import type { AppEnvironment } from "./config/environment";
import { PrivacyShield } from "./components/PrivacyShield";

export default function App() {
  const [configuration] = useState<{ environment: AppEnvironment | null; error: boolean }>(() => { try { return { environment: readEnvironment(), error: false }; } catch { return { environment: null, error: true }; } });
  if (configuration.error || !configuration.environment) return <Screen><Text accessibilityRole="alert">ACP Employee is not configured. Contact support.</Text></Screen>;
  return <PrivacyShield><RuntimeApp environment={configuration.environment} /></PrivacyShield>;
}

type RuntimeState = "boot" | "restore_error" | "anonymous" | "authenticated" | "onboarding_incomplete" | "access_limited";

function RuntimeApp({ environment }: { environment: AppEnvironment }) {
  const sessions = useMemo(() => new SessionRepository(deviceProtectedStorage), []);
  const [state, setState] = useState<RuntimeState>("boot"); const [capabilities, setCapabilities] = useState<readonly Capability[]>([]);
  const expire = useCallback(() => { setCapabilities([]); setState("anonymous"); }, []);
  const client = useMemo(() => new ApiClient(environment.apiBaseUrl, sessions, deviceNetworkMonitor, safeLogger, expire), [environment.apiBaseUrl, expire, sessions]);
  const timekeeping = useMemo(() => createTimekeepingService(client), [client]); const employeeOperations = useMemo(() => createEmployeeOperationsService(client), [client]);
  const fieldService = useMemo(() => createFieldService(client), [client]);
  const coordinator = useMemo(() => new AuthenticationCoordinator(client, sessions, async (allowed) => { if (allowed.includes("time.self.view")) await timekeeping.state(); else if (allowed.includes("my_day.view")) await employeeOperations.day(); }), [client, employeeOperations, sessions, timekeeping]);
  const apply = useCallback((result: EstablishedState | { kind: "anonymous" }) => { if (result.kind === "authenticated") { setCapabilities(result.capabilities); setState("authenticated"); } else { setCapabilities([]); setState(result.kind); } }, []);
  const restore = useCallback(async () => { setState("boot"); try { apply(await coordinator.restore()); } catch { setState("restore_error"); } }, [apply, coordinator]);
  const reconcileAuthority = useCallback(async () => { try { apply(await coordinator.restore()); } catch { /* Surface hooks retain explicitly stale data during transient recovery. */ } }, [apply, coordinator]);
  useEffect(() => { void coordinator.restore().then(apply).catch(() => setState("restore_error")); }, [apply, coordinator]);
  useEffect(() => AppState.addEventListener("change", (next) => { if (next === "active") void reconcileAuthority(); }).remove, [reconcileAuthority]);
  useEffect(() => deviceNetworkMonitor.subscribe((connected) => { if (connected) void reconcileAuthority(); }), [reconcileAuthority]);
  const signIn = useCallback(async (email: string, password: string) => { apply(await coordinator.signIn(email, password)); }, [apply, coordinator]);
  const activate = useCallback(async (token: string, password: string) => { await coordinator.activate(token, password); }, [coordinator]);
  const signOut = useCallback(async () => { await coordinator.signOut(); setCapabilities([]); setState("anonymous"); }, [coordinator]);
  if (state === "boot") return <Screen><Text accessibilityLabel="Verifying protected ACP session">Verifying your ACP session…</Text></Screen>;
  if (state === "restore_error") return <Screen><Text accessibilityRole="alert">ACP could not verify this device session. Connect to the internet and try again.</Text><PrimaryButton label="Retry Session Verification" onPress={() => void restore()} /><PrimaryButton label="Clear Session and Sign In" onPress={() => void signOut()} /></Screen>;
  if (state === "onboarding_incomplete" || state === "access_limited") return <RestrictedStateScreen kind={state} onLogout={signOut} />;
  return <ErrorBoundary><StatusBar style="auto" /><AppNavigator authenticated={state === "authenticated"} capabilities={capabilities} timekeeping={timekeeping} employeeOperations={employeeOperations} fieldService={fieldService} network={deviceNetworkMonitor} environment={environment} onSignIn={signIn} onActivate={activate} onLogout={signOut} /></ErrorBoundary>;
}
