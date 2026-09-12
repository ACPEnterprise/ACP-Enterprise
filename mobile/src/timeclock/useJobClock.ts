import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";
import * as Crypto from "expo-crypto";
import type { ActiveJobClock, JobClockAction, TimekeepingService } from "../api/timekeeping";
import { ApiFailure } from "../api/types";
import type { NetworkMonitor } from "../network/networkMonitor";

type JobClockStatus = "loading" | "ready" | "submitting" | "recovering" | "offline" | "forbidden" | "session_expired" | "error";
type Retry = { action: JobClockAction; jobId: string; appointmentId: string | null; key: string; priorEventId: string | null };

export function useJobClock(service: TimekeepingService, network: NetworkMonitor, enabled: boolean) {
  const [status, setStatus] = useState<JobClockStatus>(enabled ? "loading" : "ready");
  const [state, setState] = useState<ActiveJobClock | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const retry = useRef<Retry | null>(null);
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (!enabled) return null;
    if (!(await network.isConnected())) { setStatus("offline"); setMessage("You're offline. Job clock actions are unavailable."); return null; }
    try {
      const next = await service.jobClockState();
      setState(next); setStatus("ready"); setMessage(null); return next;
    } catch (error) {
      const kind = error instanceof ApiFailure ? error.kind : "unavailable";
      if (kind === "unauthenticated") { setState(null); setStatus("session_expired"); setMessage("Your session has expired. Please sign in again."); }
      else if (kind === "forbidden" || kind === "not_ready") { setState(null); setStatus("forbidden"); setMessage("Job clock access is not available for your account."); }
      else if (kind === "offline") { setStatus("offline"); setMessage("You're offline. Any displayed Job clock is last confirmed."); }
      else { setStatus("error"); setMessage("Unable to refresh the Job clock. Any displayed state is last confirmed."); }
      return null;
    }
  }, [enabled, network, service]);

  useEffect(() => { if (enabled) void Promise.resolve().then(refresh); }, [enabled, refresh]);
  useEffect(() => enabled ? network.subscribe((connected) => { if (connected) void refresh(); else { setStatus("offline"); setMessage("You're offline. Any displayed Job clock is last confirmed."); } }) : undefined, [enabled, network, refresh]);
  useEffect(() => enabled ? AppState.addEventListener("change", (next) => { if (next === "active") void refresh(); }).remove : undefined, [enabled, refresh]);

  const mutate = useCallback(async (action: JobClockAction, jobId: string, appointmentId: string | null) => {
    if (!enabled || inFlight.current || !state) return false;
    inFlight.current = true;
    if (!(await network.isConnected())) { inFlight.current = false; setStatus("offline"); setMessage("You're offline. The Job clock action was not sent."); return false; }
    const pending = retry.current?.action === action && retry.current.jobId === jobId && retry.current.appointmentId === appointmentId
      ? retry.current : { action, jobId, appointmentId, key: Crypto.randomUUID(), priorEventId: state.event_id };
    retry.current = pending; setStatus("submitting"); setMessage(action === "start" ? "Clocking onto this Job with ACP…" : "Clocking off this Job with ACP…");
    try {
      const result = await service.jobClock(action, jobId, appointmentId, pending.key);
      retry.current = null; setState(result.state); setStatus("ready"); setMessage(action === "start" ? "Job clock-on confirmed by ACP." : "Job clock-off confirmed by ACP."); return true;
    } catch (error) {
      const kind = error instanceof ApiFailure ? error.kind : "unavailable";
      if (["conflict", "timeout", "unavailable", "malformed_response"].includes(kind)) {
        setStatus("recovering"); setMessage("Confirming the authoritative Job clock…");
        const recovered = await refresh();
        const committed = action === "start"
          ? recovered?.active === true && recovered.job_id === jobId && recovered.event_id !== pending.priorEventId
          : recovered?.active === false
            && recovered.latest_action === "stop"
            && recovered.latest_event_id !== null
            && recovered.latest_event_id !== pending.priorEventId
            && recovered.latest_completed_interval_id !== null;
        if (committed) { retry.current = null; setStatus("ready"); setMessage("The latest Job clock confirms the action."); return true; }
        if (kind === "conflict") { retry.current = null; setStatus("ready"); setMessage("The Job clock changed. Review the latest state before acting."); }
        else { setStatus("ready"); setMessage("The Job clock action was not confirmed. Retry uses the same request identity."); }
      } else if (kind === "unauthenticated") { setState(null); setStatus("session_expired"); setMessage("Your session has expired. Please sign in again."); }
      else if (kind === "forbidden" || kind === "not_ready") { setState(null); setStatus("forbidden"); setMessage("Your Job assignment or permission changed."); }
      else { setStatus("error"); setMessage("Unable to complete the Job clock action. Refresh before trying again."); }
      return false;
    } finally { inFlight.current = false; }
  }, [enabled, network, refresh, service, state]);

  return { state, status, message, busy: status === "submitting" || status === "recovering", refresh, mutate };
}
