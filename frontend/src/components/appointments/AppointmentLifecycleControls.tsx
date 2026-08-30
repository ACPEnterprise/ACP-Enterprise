import { useState, type FormEvent } from "react";

import { getOperatorApiError } from "../../api/errors";
import { useSchedulingMutations } from "../../hooks/useScheduling";
import type { AppointmentDetail } from "../../types/scheduling";
import { Alert, Button, Field, Input, Select } from "../../ui";

const localInput = (value: string | null) => value ? new Date(value).toISOString().slice(0, 16) : "";

export function AppointmentLifecycleControls({ appointment }: { readonly appointment: AppointmentDetail }) {
  const mutations = useSchedulingMutations();
  const [mode, setMode] = useState<"reschedule" | "cancel" | null>(null);
  const [start, setStart] = useState(() => localInput(appointment.arrival_window_start_at));
  const [end, setEnd] = useState(() => localInput(appointment.arrival_window_end_at));
  const [reason, setReason] = useState("customer_request");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (mode === "cancel") mutations.cancel.mutate({ id: appointment.id, input: { expected_version: appointment.concurrency_version, reason_code: reason as "customer_request" } });
    if (mode === "reschedule") mutations.reschedule.mutate({ id: appointment.id, input: { expected_version: appointment.concurrency_version, arrival_window_start_at: new Date(start).toISOString(), arrival_window_end_at: new Date(end).toISOString(), expected_duration_minutes: appointment.expected_duration_minutes ?? 60, capacity_units: appointment.capacity_units ?? "1.00", reason_code: reason as "customer_request" } });
  };
  const error = mutations.cancel.error ?? mutations.reschedule.error;
  return <section className="space-y-3 rounded-xl border border-stroke bg-surface p-ui-4 sm:p-ui-6" aria-label="Appointment actions"><h3 className="font-semibold">Schedule actions</h3><p className="text-sm text-content-muted">Changes use Scheduling authority and the currently observed version.</p><div className="flex flex-wrap gap-2"><Button onClick={() => setMode("reschedule")}>Reschedule</Button><Button variant="outline" onClick={() => setMode("cancel")}>Cancel Appointment</Button></div>{mode && <form className="grid gap-3 rounded-lg bg-surface-subtle p-4 sm:grid-cols-2" onSubmit={submit}>{mode === "reschedule" && <><Field label="New window start"><Input type="datetime-local" value={start} onChange={(event) => setStart(event.target.value)} required /></Field><Field label="New window end"><Input type="datetime-local" value={end} onChange={(event) => setEnd(event.target.value)} required /></Field></>}<Field label="Controlled reason"><Select value={reason} onChange={(event) => setReason(event.target.value)}><option value="customer_request">Customer request</option>{mode === "reschedule" ? <><option value="technician_unavailable">Technician unavailable</option><option value="weather">Weather</option><option value="operational_conflict">Operational conflict</option><option value="scope_change">Scope change</option></> : <><option value="duplicate">Duplicate</option><option value="created_in_error">Created in error</option><option value="unable_to_service">Unable to service</option><option value="weather">Weather</option></>}</Select></Field><div className="flex items-end gap-2"><Button type="submit" loading={mutations.cancel.isPending || mutations.reschedule.isPending}>Confirm {mode}</Button><Button type="button" variant="ghost" onClick={() => setMode(null)}>Close</Button></div></form>}{error && (() => { const safe = getOperatorApiError(error, "Appointment"); return <Alert variant="danger" title={safe.title}>{safe.message}</Alert>; })()}</section>;
}
