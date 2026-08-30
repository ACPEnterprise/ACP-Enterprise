import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useAuth, useHasPermission } from "../auth";
import { CreateAppointmentPanel } from "../components/appointments/CreateAppointmentPanel";
import { dayRange, localDateValue } from "../components/dispatch/dispatchPresentation";
import { getOperatorApiError } from "../api/errors";
import { useAppointments } from "../hooks/useScheduling";
import { appointmentDetailPath } from "../routing/paths";
import type { AppointmentStatus } from "../types/scheduling";
import { Alert, Button, Card, Input, Select } from "../ui";

const pageSize = 50;
const statuses: readonly AppointmentStatus[] = [
  "draft",
  "scheduled",
  "confirmed",
  "completed",
  "cancelled",
  "no_show",
];

const displayStatus = (value: string) => value.replaceAll("_", " ");
const displayTime = (value: string | null) =>
  value ? new Date(value).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "Unscheduled";

export function SchedulingRoute() {
  const { activeCompany } = useAuth();
  const canManage = useHasPermission("COMPANY_SCHEDULING_MANAGE");
  const [creating, setCreating] = useState(false);
  const [date, setDate] = useState(() => localDateValue(new Date()));
  const [branchId, setBranchId] = useState("");
  const [status, setStatus] = useState<AppointmentStatus | "">("");
  const [viewDays, setViewDays] = useState<1 | 3 | 7>(1);
  const [page, setPage] = useState(1);
  const range = dayRange(date);
  const end = new Date(range.startAt);
  end.setDate(end.getDate() + viewDays);
  const query = useAppointments({
    startAt: range.startAt,
    endAt: end.toISOString(),
    branchId: branchId || undefined,
    status: status ? [status] : undefined,
    page,
    pageSize,
  }, Boolean(activeCompany));
  const totalPages = Math.max(1, Math.ceil((query.data?.total_count ?? 0) / pageSize));

  if (!activeCompany) {
    return <Alert variant="danger" title="Company scope unavailable">Select an accessible Company before opening Scheduling.</Alert>;
  }

  return <div className="min-w-0 space-y-6">
    <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div>
      <p className="text-sm font-medium text-action-primary">Operations</p>
      <h2 className="mt-1 text-2xl font-bold sm:text-3xl">Scheduling</h2>
      <p className="mt-2 text-content-muted">Review the authoritative daily appointment schedule and open work details.</p>
    </div>{canManage && <Button onClick={() => setCreating(true)}>Create Appointment</Button>}</header>
    {creating && <CreateAppointmentPanel onClose={() => setCreating(false)} />}
    <Card className="grid gap-3 p-ui-4 md:grid-cols-4">
      <label><span className="mb-1 block text-sm font-medium">Service date</span><Input aria-label="Service date" type="date" value={date} onChange={(event) => { setDate(event.target.value); setPage(1); }} /></label>
      <label><span className="mb-1 block text-sm font-medium">Branch</span><Select aria-label="Branch" value={branchId} onChange={(event) => { setBranchId(event.target.value); setPage(1); }}><option value="">All accessible Branches</option>{activeCompany.branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</Select></label>
      <label><span className="mb-1 block text-sm font-medium">Status</span><Select aria-label="Appointment status" value={status} onChange={(event) => { setStatus(event.target.value as AppointmentStatus | ""); setPage(1); }}><option value="">All statuses</option>{statuses.map((value) => <option key={value} value={value}>{displayStatus(value)}</option>)}</Select></label>
      <label><span className="mb-1 block text-sm font-medium">Calendar span</span><Select aria-label="Calendar span" value={viewDays} onChange={(event) => { setViewDays(Number(event.target.value) as 1 | 3 | 7); setPage(1); }}><option value={1}>Day</option><option value={3}>3 days</option><option value={7}>Week</option></Select></label>
    </Card>
    {query.isLoading && <Card className="p-ui-6"><p>Loading the schedule…</p></Card>}
    {query.isError && (() => { const error = getOperatorApiError(query.error, "Schedule"); return <Alert variant="danger" title={error.title} action={error.retryable ? <Button onClick={() => void query.refetch()}>Retry</Button> : undefined}>{error.message}</Alert>; })()}
    {query.data && query.data.items.length === 0 && <Card className="p-ui-6"><h3 className="font-semibold">No appointments found</h3><p className="mt-2 text-sm text-content-muted">No accessible appointments overlap the selected day and filters.</p></Card>}
    {query.data && query.data.items.length > 0 && <section aria-label="Appointments" className="grid gap-3">
      {query.data.items.map((appointment) => <Link key={appointment.id} to={appointmentDetailPath(appointment.id)} className="block rounded-xl border border-stroke bg-surface p-ui-4 transition hover:border-action-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action-primary">
        <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><h3 className="break-all font-semibold">{appointment.appointment_number}</h3><p className="mt-1 text-sm text-content-muted">{viewDays > 1 && appointment.arrival_window_start_at ? `${new Date(appointment.arrival_window_start_at).toLocaleDateString()} · ` : ""}{displayTime(appointment.arrival_window_start_at)}–{displayTime(appointment.arrival_window_end_at)}</p></div><span className="w-fit rounded-full bg-status-information/15 px-3 py-1 text-sm capitalize text-status-information">{displayStatus(appointment.status)}</span></div>
      </Link>)}
    </section>}
    {query.data && query.data.total_count > 0 && <footer className="flex flex-col gap-3 text-sm text-content-muted sm:flex-row sm:items-center sm:justify-between"><span>Page {page} of {totalPages} · {query.data.total_count} appointments</span><div className="grid grid-cols-2 gap-2"><Button variant="outline" aria-label="Previous page" disabled={page === 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={17} /></Button><Button variant="outline" aria-label="Next page" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}><ChevronRight size={17} /></Button></div></footer>}
  </div>;
}
