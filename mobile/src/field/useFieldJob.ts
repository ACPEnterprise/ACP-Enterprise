import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";
import type { FieldJobState, FieldService, ItineraryItem, JobAction } from "../api/fieldService";
import { fieldIdempotencyKey } from "../api/fieldService";
import { ApiFailure } from "../api/types";
import type { NetworkMonitor } from "../network/networkMonitor";

export type FieldStatus = "loading" | "live" | "offline" | "stale" | "denied" | "reauth" | "not_available" | "mutation_uncertain" | "error";

export function useFieldJob(service: FieldService, network: NetworkMonitor, businessDate: string, appointmentId: string, jobId: string | null) {
  const [status, setStatus] = useState<FieldStatus>("loading");
  const [item, setItem] = useState<ItineraryItem | null>(null);
  const [field, setField] = useState<FieldJobState | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const pendingArrival = useRef<{ state: "en_route" | "arrived"; key: string } | null>(null);
  const itemRef = useRef<ItineraryItem | null>(null);

  const fail = useCallback((error: unknown, cached: boolean) => {
    const kind = error instanceof ApiFailure ? error.kind : "unavailable";
    if (kind === "unauthenticated") { setStatus("reauth"); setMessage("Your session must be verified again."); }
    else if (kind === "forbidden") { setStatus("denied"); setMessage("Your current permissions do not allow this Job workspace."); }
    else if (kind === "offline") { setStatus(cached ? "stale" : "offline"); setMessage("You're offline. Field actions are unavailable."); }
    else { setStatus(cached ? "stale" : "error"); setMessage("ACP could not confirm current field status. Actions are disabled."); }
  }, []);

  const refresh = useCallback(async () => {
    if (!(await network.isConnected())) { setStatus(itemRef.current ? "stale" : "offline"); setMessage("You're offline. Field actions are unavailable."); return null; }
    try {
      const itinerary = await service.itinerary(businessDate);
      const next = itinerary.items.find((value) => value.appointment_id === appointmentId) ?? null;
      if (!next) { itemRef.current = null; setStatus("not_available"); setItem(null); setField(null); setMessage("This assignment is no longer in your authoritative itinerary."); return null; }
      if (jobId && next.job_id !== jobId) { itemRef.current = null; setStatus("not_available"); setItem(null); setField(null); setMessage("The authoritative Job assignment changed. Return to My Day and reopen it."); return null; }
      const nextField = next.job_id ? await service.state(next.job_id) : null;
      itemRef.current = next; setItem(next); setField(nextField); setStatus("live"); setMessage(null); return next;
    } catch (error) { fail(error, itemRef.current !== null); return null; }
  }, [appointmentId, businessDate, fail, jobId, network, service]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => network.subscribe((connected) => { if (connected) void refresh(); else { setStatus(itemRef.current ? "stale" : "offline"); setMessage("You're offline. Field actions are unavailable."); } }), [network, refresh]);
  useEffect(() => AppState.addEventListener("change", (next) => { if (next === "active") void refresh(); }).remove, [refresh]);

  const arrival = useCallback(async (nextState: "en_route" | "arrived") => {
    if (status !== "live" || !item) return;
    const pending = pendingArrival.current?.state === nextState ? pendingArrival.current : { state: nextState, key: fieldIdempotencyKey(nextState) };
    pendingArrival.current = pending; setStatus("loading"); setMessage("Waiting for server confirmation…");
    try { await service.arrival(item.appointment_id, nextState, item.assignment_version, pending.key); pendingArrival.current = null; await refresh(); }
    catch (error) {
      const kind = error instanceof ApiFailure ? error.kind : "unavailable";
      if (["timeout", "unavailable", "malformed_response"].includes(kind)) { setStatus("mutation_uncertain"); setMessage("Outcome uncertain. Refresh before taking another action."); await refresh(); }
      else { pendingArrival.current = null; fail(error, true); }
    }
  }, [fail, item, refresh, service, status]);

  const transition = useCallback(async (action: JobAction) => {
    if (status !== "live" || !item?.job_id || !item.job_version) return;
    const before = item.job_status; setStatus("loading"); setMessage("Waiting for server confirmation…");
    try { await service.transition(item.job_id, action, item.job_version); await refresh(); }
    catch (error) {
      const kind = error instanceof ApiFailure ? error.kind : "unavailable";
      if (["timeout", "unavailable", "malformed_response"].includes(kind)) {
        setStatus("mutation_uncertain"); setMessage("Outcome uncertain. ACP will reconcile server state; do not repeat this action.");
        const recovered = await refresh();
        if (recovered?.job_status === before) { setStatus("mutation_uncertain"); setMessage("The outcome is still uncertain. Do not retry until an operator confirms it."); }
      } else fail(error, true);
    }
  }, [fail, item, refresh, service, status]);

  const workSummary = useCallback(async (content: string) => {
    if (status !== "live" || !item?.job_id || !item.job_version || !content.trim()) return;
    setStatus("loading"); setMessage("Recording work summary…");
    try { setField(await service.workSummary(item.job_id, content.trim(), item.job_version, item.assignment_version, fieldIdempotencyKey("work-summary"))); setStatus("live"); setMessage("Work summary confirmed by ACP Enterprise."); }
    catch (error) { const kind = error instanceof ApiFailure ? error.kind : "unavailable"; if (["timeout", "unavailable", "malformed_response"].includes(kind)) { setStatus("mutation_uncertain"); setMessage("Work summary outcome is uncertain. Do not submit it again until refresh confirms state."); try { const confirmed = await service.state(item.job_id); setField(confirmed); if (confirmed.work_summary_recorded) { setStatus("live"); setMessage("Work summary was committed and is now confirmed."); } } catch { /* Preserve uncertain state. */ } } else fail(error, true); }
  }, [fail, item, service, status]);

  const customerDisposition = useCallback(async (disposition: "approved" | "unavailable" | "refused", customerName: string | null, reason: string | null) => {
    if (status !== "live" || !item?.job_id || !item.job_version) return;
    setStatus("loading"); setMessage("Recording customer disposition…");
    try { setField(await service.customerDisposition(item.job_id, disposition, customerName, reason, item.job_version, item.assignment_version, fieldIdempotencyKey("customer-disposition"))); setStatus("live"); setMessage("Customer disposition confirmed by ACP Enterprise."); }
    catch (error) { const kind = error instanceof ApiFailure ? error.kind : "unavailable"; if (["timeout", "unavailable", "malformed_response"].includes(kind)) { setStatus("mutation_uncertain"); setMessage("Customer disposition outcome is uncertain. Do not submit it again until refresh confirms state."); try { const confirmed = await service.state(item.job_id); setField(confirmed); if (confirmed.customer_disposition === disposition) { setStatus("live"); setMessage("Customer disposition was committed and is now confirmed."); } } catch { /* Preserve uncertain state. */ } } else fail(error, true); }
  }, [fail, item, service, status]);

  return { status, item, field, message, refresh, arrival, transition, workSummary, customerDisposition, mutationsAllowed: status === "live" && item?.field_execution_enabled === true && item.assignment_status !== "reconciliation_required" };
}
