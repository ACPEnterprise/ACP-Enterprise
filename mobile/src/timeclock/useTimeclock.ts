import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";
import * as Crypto from "expo-crypto";
import type { PunchAction, PunchState, Timecard, TimekeepingService } from "../api/timekeeping";
import { ApiFailure } from "../api/types";
import type { NetworkMonitor } from "../network/networkMonitor";

export type TimeclockStatus = "loading" | "ready" | "submitting" | "recovering" | "offline" | "not_ready" | "forbidden" | "session_expired" | "error";
type Retry = { action: PunchAction; key: string; priorState: PunchState["state"] };

export function useTimeclock(service: TimekeepingService, network: NetworkMonitor) {
  const [status, setStatus] = useState<TimeclockStatus>("loading");
  const [punchState, setPunchState] = useState<PunchState | null>(null);
  const [timecard, setTimecard] = useState<Timecard | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const retry = useRef<Retry | null>(null);
  const busy = status === "submitting" || status === "recovering";

  const applyFailure = useCallback((error: unknown) => {
    const kind = error instanceof ApiFailure ? error.kind : "unavailable";
    if (kind === "unauthenticated") { setStatus("session_expired"); setMessage("Your session has expired. Please sign in again."); }
    else if (kind === "forbidden") { setStatus("forbidden"); setMessage("You do not have permission to use employee timekeeping."); }
    else if (kind === "not_ready") { setStatus("not_ready"); setMessage("Your employee account is not ready for timekeeping."); }
    else if (kind === "offline") { setStatus("offline"); setMessage("You're offline. Punch actions are unavailable."); }
    else { setStatus("error"); setMessage("Unable to load your time status. Check your connection and try again."); }
  }, []);

  const refresh = useCallback(async () => {
    if (!(await network.isConnected())) { setStatus("offline"); setMessage("You're offline. Showing the last confirmed server state."); return null; }
    try {
      const [nextState, nextCard] = await Promise.all([service.state(), service.timecard()]);
      setPunchState(nextState); setTimecard(nextCard); setStatus("ready"); setMessage(null); return nextState;
    } catch (error) { applyFailure(error); return null; }
  }, [applyFailure, network, service]);

  useEffect(() => { void Promise.resolve().then(refresh); }, [refresh]);
  useEffect(() => network.subscribe((connected) => { if (connected) void refresh(); else { setStatus("offline"); setMessage("You're offline. Showing the last confirmed server state."); } }), [network, refresh]);
  useEffect(() => AppState.addEventListener("change", (next) => { if (next === "active") void refresh(); }).remove, [refresh]);

  const punch = useCallback(async (action: PunchAction) => {
    if (busy || !punchState || !(await network.isConnected())) { if (!busy) { setStatus("offline"); setMessage("You're offline. Punch actions are unavailable."); } return; }
    const attempt = retry.current?.action === action ? retry.current : { action, key: Crypto.randomUUID(), priorState: punchState.state };
    retry.current = attempt; setStatus("submitting"); setMessage(`Submitting ${action.replaceAll("_", " ")}…`);
    try {
      const result = await service.punch(action, attempt.key);
      retry.current = null; setPunchState(result.state); setStatus("ready"); setMessage("Time status confirmed by ACP Enterprise.");
      try { setTimecard(await service.timecard()); } catch { /* Punch response remains authoritative; later refresh can recover the card. */ }
    } catch (error) {
      const kind = error instanceof ApiFailure ? error.kind : "unavailable";
      if (kind === "conflict" || kind === "timeout" || kind === "unavailable" || kind === "malformed_response") {
        setStatus("recovering"); setMessage("Confirming your authoritative time status…");
        const recovered = await refresh();
        if (recovered?.state !== attempt.priorState) { retry.current = null; setMessage("Your authoritative time status was refreshed."); }
        else if (kind === "conflict") { retry.current = null; setMessage("Your time status changed. We've refreshed it."); }
        else { setStatus("ready"); setMessage("The punch was not confirmed. Try again to safely retry the same request."); }
      } else applyFailure(error);
    }
  }, [applyFailure, busy, network, punchState, refresh, service]);

  return { status, punchState, timecard, message, busy, refresh, punch };
}
