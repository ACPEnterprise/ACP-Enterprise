import { useState } from "react";

import { getOperatorApiError } from "../../api/errors";
import { Alert, Badge, Button, Card, ConfirmationDialog, Spinner } from "../../ui";
import * as mobileApi from "./api";
import {
  useAllocationReconciliationMutation,
  useAllocationReleaseMutation,
  useCapacityMutation,
  useEngineeringCapacity,
  useExistingWorkerSetupMutation,
  useReservationMutation,
  useReservationReleaseMutation,
  useWorkerLimitMutation,
  useWorkerStateMutation,
} from "./hooks";
import { mobileEngineeringLabel } from "./presentation";
import type { CapacityQueueItem, EligibleCapacityWorker } from "./types";

function ExistingWorkerSetupCard({
  worker,
  maximum,
}: {
  worker: EligibleCapacityWorker;
  maximum: number;
}) {
  const mutation = useExistingWorkerSetupMutation();
  const [machineLabel, setMachineLabel] = useState(worker.worker_name);
  const [limit, setLimit] = useState(1);
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">{worker.worker_name}</h3>
          <p className="text-xs text-content-muted">Authenticated identity · {worker.provider_identifier}</p>
        </div>
        <div className="flex gap-2"><Badge>{mobileEngineeringLabel(worker.lifecycle_state)}</Badge><Badge>{mobileEngineeringLabel(worker.health_state)}</Badge></div>
      </div>
      <p className="mt-2 text-xs text-content-muted">Last heartbeat: {worker.last_heartbeat_at ? new Date(worker.last_heartbeat_at).toLocaleString() : "No recent heartbeat"}</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_8rem]">
        <label className="text-sm">Machine label<input aria-label={`${worker.worker_name} machine label`} className="mt-1 min-h-11 w-full rounded-md border border-stroke bg-surface px-3" value={machineLabel} onChange={(event) => setMachineLabel(event.target.value)} /></label>
        <label className="text-sm">Concurrency<input aria-label={`${worker.worker_name} initial concurrency`} className="mt-1 min-h-11 w-full rounded-md border border-stroke bg-surface px-3" type="number" min={1} max={maximum} value={limit} onChange={(event) => setLimit(Number(event.target.value))} /></label>
      </div>
      <Button className="mt-3 min-h-11 w-full sm:w-auto" disabled={!machineLabel.trim() || limit < 1 || limit > maximum || mutation.isPending} onClick={() => mutation.mutate({ worker, machineLabel: machineLabel.trim(), configuredLimit: limit })}>Add to capacity</Button>
      {mutation.isError && <Alert className="mt-3" variant="danger" title="Worker was not configured">{getOperatorApiError(mutation.error, "Worker capacity").message}</Alert>}
    </Card>
  );
}

export function EngineeringCapacityPanel() {
  const query = useEngineeringCapacity();
  const policyMutation = useCapacityMutation(mobileApi.updateCapacityPolicy);
  const workerLimitMutation = useWorkerLimitMutation();
  const workerStateMutation = useWorkerStateMutation();
  const reserveMutation = useReservationMutation();
  const releaseReservationMutation = useReservationReleaseMutation();
  const reconcileMutation = useAllocationReconciliationMutation();
  const releaseAllocationMutation = useAllocationReleaseMutation();
  const [totalLimit, setTotalLimit] = useState<number | null>(null);
  const [workerLimit, setWorkerLimit] = useState<number | null>(null);
  const [reserved, setReserved] = useState<number | null>(null);
  const [showFullQueue, setShowFullQueue] = useState(false);
  const [confirmingReservation, setConfirmingReservation] = useState<CapacityQueueItem | null>(null);

  if (query.isLoading) return <Card><Spinner label="Loading engineering capacity" /></Card>;
  if (query.isError) {
    const error = getOperatorApiError(query.error, "Engineering capacity");
    return <Alert variant="danger" title={error.title}>{error.message}</Alert>;
  }
  if (!query.data) return null;
  const data = query.data;
  const effectiveTotalLimit = totalLimit ?? data.policy?.maximum_concurrent_workstreams ?? 1;
  const effectiveWorkerLimit = workerLimit ?? data.policy?.maximum_per_worker ?? 1;
  const effectiveReserved = reserved ?? data.policy?.reserved_capacity ?? 0;

  return (
    <section aria-labelledby="engineering-capacity-heading" className="space-y-ui-4">
      <header>
        <p className="text-sm font-semibold text-blue-400">Engineering capacity</p>
        <h2 id="engineering-capacity-heading" className="mt-1 text-xl font-bold">Machines and assignments</h2>
        <p className="mt-1 text-sm text-content-muted">Capacity controls assignment readiness only. Starting engineering work still requires its existing explicit owner action.</p>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Configured", data.configured_capacity],
          ["In use", data.allocated_capacity],
          ["Reserved", data.reserved_capacity],
          ["Available", data.available_capacity],
        ].map(([label, value]) => <Card key={label}><p className="text-xs text-content-muted">{label}</p><p className="mt-1 text-2xl font-bold">{value}</p></Card>)}
      </div>

      <Card>
        <h3 className="font-semibold">Company limits</h3>
        {!data.policy && <Alert variant="warning" title="Capacity is not configured">Assignments fail closed until an authorized owner saves a policy.</Alert>}
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <label className="text-sm">Concurrent workstreams<input aria-label="Maximum concurrent workstreams" className="mt-1 min-h-11 w-full rounded-md border border-stroke bg-surface px-3" type="number" min={1} value={effectiveTotalLimit} onChange={(event) => setTotalLimit(Number(event.target.value))} /></label>
          <label className="text-sm">Per machine<input aria-label="Maximum per worker" className="mt-1 min-h-11 w-full rounded-md border border-stroke bg-surface px-3" type="number" min={1} value={effectiveWorkerLimit} onChange={(event) => setWorkerLimit(Number(event.target.value))} /></label>
          <label className="text-sm">Held in reserve<input aria-label="Reserved capacity" className="mt-1 min-h-11 w-full rounded-md border border-stroke bg-surface px-3" type="number" min={0} value={effectiveReserved} onChange={(event) => setReserved(Number(event.target.value))} /></label>
        </div>
        <Button className="mt-4 min-h-11 w-full sm:w-auto" disabled={policyMutation.isPending} onClick={() => policyMutation.mutate({ maximum_concurrent_workstreams: effectiveTotalLimit, maximum_per_worker: effectiveWorkerLimit, reserved_capacity: effectiveReserved, auto_allocate_released_capacity: false, expected_version: data.policy?.version ?? null })}>Save capacity limits</Button>
      </Card>

      <section aria-labelledby="capacity-workers-heading" className="space-y-3">
        <div><h3 id="capacity-workers-heading" className="font-semibold">Workers and machines</h3><p className="text-sm text-content-muted">Only previously enrolled, authenticated workers can be associated with an owner-visible machine label.</p></div>
        {data.eligible_workers.filter((worker) => !worker.capacity_configured).map((worker) => <ExistingWorkerSetupCard key={worker.worker_id} worker={worker} maximum={Math.max(1, Math.min(effectiveTotalLimit, effectiveWorkerLimit))} />)}
        {data.workers.map((worker) => (
          <Card key={worker.id}>
            <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-semibold">{worker.machine_label}</h3><p className="text-xs text-content-muted">{worker.allocated_capacity} running · {worker.reserved_capacity} reserved · {worker.available_capacity} available</p></div><div className="flex gap-2"><Badge>{mobileEngineeringLabel(worker.operational_state)}</Badge><Badge>{mobileEngineeringLabel(worker.health_state)}</Badge></div></div>
            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
              <label className="flex-1 text-sm">Concurrency limit<input aria-label={`${worker.machine_label} concurrency limit`} className="mt-1 min-h-11 w-full rounded-md border border-stroke bg-surface px-3" type="number" min={1} defaultValue={worker.configured_limit} onBlur={(event) => { const limit = Number(event.target.value); if (limit !== worker.configured_limit) workerLimitMutation.mutate({ worker, limit }); }} /></label>
              <Button className="min-h-11 self-end" variant="outline" onClick={() => workerStateMutation.mutate({ worker, action: worker.operational_state === "paused" ? "restore" : "pause" })}>{worker.operational_state === "paused" ? "Restore capacity" : "Pause capacity"}</Button>
            </div>
          </Card>
        ))}
        {data.machines.filter((machine) => machine.enrollment_state === "unenrolled").map((machine) => <Card key={machine.id}><div className="flex justify-between gap-2"><div><h3 className="font-semibold">{machine.machine_label}</h3><p className="text-sm text-content-muted">Not enrolled{machine.expected_available_on ? ` · Expected ${new Date(machine.expected_available_on).toLocaleDateString()}` : ""}</p></div><Badge>Offline</Badge></div></Card>)}
        {data.eligible_workers.length === 0 && data.workers.length === 0 && <Alert variant="warning" title="No enrolled workers available">Enroll and authenticate an engineering worker through the existing trusted-worker workflow before configuring capacity.</Alert>}
      </section>

      {data.active_allocations.filter((item) => item.status === "active").length > 0 && <Card><h3 className="font-semibold">Active allocations</h3>{data.active_allocations.filter((item) => item.status === "active").map((item) => <div key={item.id} className="mt-3 flex flex-col gap-2 rounded-lg border border-stroke p-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-medium">{item.milestone_title ?? "Reconciliation Required"}</p><p className="text-sm text-content-muted">{item.workstream}{item.milestone_position ? ` · Roadmap step ${item.milestone_position}` : ""}</p><p className="text-xs text-content-muted">{item.machine_label} · {item.ecid ?? "Milestone identity unavailable"}</p><p className="text-xs text-content-muted">Running · capacity allocated</p></div><Button className="min-h-11" variant="outline" disabled={!item.milestone_title} onClick={() => releaseAllocationMutation.mutate(item)}>Release capacity</Button></div>)}</Card>}

      {data.active_reservations.length > 0 && <Card><h3 className="font-semibold">Reservations</h3>{data.active_reservations.map((item) => <div key={item.id} className="mt-3 flex flex-col gap-2 rounded-lg border border-stroke p-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-medium">{item.milestone_title ?? "Reconciliation Required"}</p><p className="text-sm text-content-muted">{item.workstream}{item.milestone_position ? ` · Roadmap step ${item.milestone_position}` : ""}</p><p className="text-xs text-content-muted">{item.machine_label} · {item.ecid ?? "Milestone identity unavailable"}</p><p className="text-xs text-content-muted">{mobileEngineeringLabel(item.status)}</p></div>{item.status === "active" && <Button className="min-h-11" variant="outline" disabled={!item.milestone_title} onClick={() => releaseReservationMutation.mutate(item)}>Release reservation</Button>}</div>)}</Card>}

      {data.active_allocations.filter((item) => item.status === "reconciliation_required").map((allocation) => <Alert key={allocation.id} variant="warning" title="Reconciliation required"><p className="font-semibold">{allocation.milestone_title ?? "Milestone identity unavailable"}</p><p>{allocation.workstream}{allocation.milestone_position ? ` · Roadmap step ${allocation.milestone_position}` : ""}</p><p>{allocation.owning_branch ? `Branch: ${allocation.owning_branch} · ` : ""}{allocation.ecid ?? "Engineering Command identity unavailable"}</p><p>{allocation.machine_label} has an ambiguous assignment. Capacity remains held.</p><div className="mt-3 grid gap-2 sm:grid-cols-2"><Button className="min-h-11" disabled={!allocation.milestone_title} onClick={() => reconcileMutation.mutate({ allocation, resolution: "confirmed_active" })}>Still active</Button><Button className="min-h-11" variant="outline" disabled={!allocation.milestone_title} onClick={() => reconcileMutation.mutate({ allocation, resolution: "confirmed_released" })}>Confirmed released</Button></div></Alert>)}

      {data.waiting_workstreams.length > 0 && <Card><div className="flex items-center justify-between gap-2"><h3 className="font-semibold">Waiting for capacity</h3><Badge>{data.waiting_workstreams.length}</Badge></div><div className="mt-3 space-y-3">{data.waiting_workstreams.slice(0, showFullQueue ? undefined : 5).map((item) => <div key={item.command_id} className="rounded-lg border border-stroke p-3">{item.identity_state === "resolved" && item.milestone_title ? <><p className="font-semibold">{item.milestone_title}</p><p className="mt-1 text-sm text-content-muted">{item.workstream ?? item.roadmap_title}{item.milestone_position ? ` · Roadmap step ${item.milestone_position}` : ""}</p><p className="text-sm text-content-muted">Branch: {item.owning_branch ?? item.expected_branch}</p></> : <><Badge>Reconciliation Required</Badge><p className="mt-2 font-semibold">Milestone identity unavailable</p></>}<p className="mt-2 text-xs text-content-muted">Engineering Command: {item.ecid}</p><p className="mt-2 text-sm text-content-muted">{item.reason}</p><Button className="mt-2 min-h-11 w-full sm:w-auto" variant="outline" disabled={item.identity_state !== "resolved" || item.decision !== "capacity_available" || !item.assigned_worker_id || reserveMutation.isPending} onClick={() => setConfirmingReservation(item)}>Reserve capacity</Button></div>)}</div>{data.waiting_workstreams.length > 5 && <Button className="mt-3 min-h-11 w-full" variant="ghost" onClick={() => setShowFullQueue((value) => !value)}>{showFullQueue ? "Show fewer waiting workstreams" : `Show all ${data.waiting_workstreams.length} waiting workstreams`}</Button>}</Card>}

      {confirmingReservation && <ConfirmationDialog title={`Reserve capacity for ${confirmingReservation.milestone_title}?`} confirmLabel="Reserve capacity" pending={reserveMutation.isPending} onCancel={() => setConfirmingReservation(null)} onConfirm={() => reserveMutation.mutate(confirmingReservation, { onSuccess: () => setConfirmingReservation(null) })}><div className="space-y-2 text-sm"><p><strong>Milestone:</strong> {confirmingReservation.milestone_title}</p><p><strong>Workstream:</strong> {confirmingReservation.workstream ?? confirmingReservation.roadmap_title}</p><p><strong>Branch:</strong> {confirmingReservation.owning_branch ?? confirmingReservation.expected_branch}</p><p><strong>Engineering Command:</strong> {confirmingReservation.ecid}</p><p><strong>Assigned worker:</strong> {confirmingReservation.assigned_worker_name}</p><p><strong>Machine:</strong> {confirmingReservation.machine_label}</p><p><strong>Capacity:</strong> {confirmingReservation.capacity_amount} assignment</p><Alert variant="warning" title="Reservation does not start execution">This holds capacity for the milestone. It does not allocate the worker or begin execution.</Alert></div></ConfirmationDialog>}
    </section>
  );
}
