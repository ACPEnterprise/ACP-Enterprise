import { useCallback, useEffect, useRef, useState } from "react";
import type { FieldJobState, FieldService, ItineraryItem } from "../api/fieldService";
import { ApiFailure } from "../api/types";
import type { NetworkMonitor } from "../network/networkMonitor";

export function useFieldWorkspace(service: FieldService, network: NetworkMonitor, appointmentId: string, jobId: string | null, serviceDate: string, enabled: boolean) {
  const [item, setItem] = useState<ItineraryItem | null>(null); const [job, setJob] = useState<FieldJobState | null>(null); const [status, setStatus] = useState<"idle" | "loading" | "ready" | "offline" | "forbidden" | "conflict" | "error">("idle");
  const mutationInFlight = useRef(false);
  const refresh = useCallback(async () => { if (!enabled || !jobId) return; if (!(await network.isConnected())) { setStatus("offline"); return; } setStatus("loading"); try { const [itinerary, state] = await Promise.all([service.itinerary(serviceDate), service.state(jobId)]); const match = itinerary.items.find((value) => value.appointment_id === appointmentId) ?? null; if (!match) throw new ApiFailure("forbidden", "Assignment unavailable"); setItem(match); setJob(state); setStatus("ready"); } catch (error) { const kind = error instanceof ApiFailure ? error.kind : "unavailable"; setStatus(kind === "offline" ? "offline" : kind === "forbidden" ? "forbidden" : kind === "conflict" ? "conflict" : "error"); } }, [appointmentId, enabled, jobId, network, service, serviceDate]);
  useEffect(() => { if (enabled) void Promise.resolve().then(refresh); }, [enabled, refresh]);
  useEffect(() => { if (!enabled) return undefined; return network.subscribe((connected) => { if (connected) void refresh(); else setStatus("offline"); }); }, [enabled, network, refresh]);
  const mutate = useCallback(async (operation: () => Promise<unknown>) => { if (mutationInFlight.current) return false; mutationInFlight.current = true; try { if (!(await network.isConnected())) { setStatus("offline"); return false; } setStatus("loading"); try { await operation(); await refresh(); return true; } catch (error) { setStatus(error instanceof ApiFailure && error.kind === "conflict" ? "conflict" : "error"); await refresh(); return false; } } finally { mutationInFlight.current = false; } }, [network, refresh]);
  return { item, job, status, refresh, mutate };
}
