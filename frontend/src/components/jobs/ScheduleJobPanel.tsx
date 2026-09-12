import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useScheduleExistingJob } from "../../hooks/useOperations";
import { useWorkforceDirectory } from "../../hooks/useWorkforce";
import { schedulingReturnPath } from "../../routing/paths";
import type { JobDetail } from "../../types/jobs";
import { Alert, Button, Field, Input, Select } from "../../ui";
import { schedulingMutationRecovery } from "../scheduling/schedulingRecovery";

const localInput = (date: Date) => {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

export function ScheduleJobPanel({ job, canAssign, returnTo }: {
  readonly job: JobDetail;
  readonly canAssign: boolean;
  readonly returnTo?: string;
}) {
  const schedule = useScheduleExistingJob(job.id);
  const workforce = useWorkforceDirectory();
  const [startAt, setStartAt] = useState(() => localInput(new Date(Date.now() + 60 * 60 * 1000)));
  const [endAt, setEndAt] = useState(() => localInput(new Date(Date.now() + 3 * 60 * 60 * 1000)));
  const [duration, setDuration] = useState(120);
  const [employeeId, setEmployeeId] = useState("");
  const [lastAttempt, setLastAttempt] = useState<{ fingerprint: string; requestId: string } | null>(null);
  const technicians = useMemo(
    () => (workforce.data ?? []).filter((employee) =>
      employee.technician && employee.employee_status === "active" &&
      (!employee.home_branch_id || employee.home_branch_id === job.branch_id)),
    [job.branch_id, workforce.data],
  );
  const book = () => {
    const start = new Date(startAt);
    const end = new Date(endAt);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end <= start || duration < 15) return;
    const intent = {
      expected_job_version: job.concurrency_version,
      branch_id: job.branch_id,
      customer_id: job.customer.id,
      service_location_id: job.service_location.id,
      arrival_window_start_at: start.toISOString(),
      arrival_window_end_at: end.toISOString(),
      expected_duration_minutes: duration,
      capacity_units: "1.00",
      reserve_capacity: Boolean(employeeId),
      employee_id: employeeId || null,
    };
    const fingerprint = JSON.stringify(intent);
    const requestId = lastAttempt?.fingerprint === fingerprint ? lastAttempt.requestId : crypto.randomUUID();
    setLastAttempt({ fingerprint, requestId });
    schedule.mutate({ ...intent, request_id: requestId }, { onSuccess: () => setLastAttempt(null) });
  };
  const submit = (event: FormEvent) => { event.preventDefault(); book(); };
  const error = schedule.error ? schedulingMutationRecovery(schedule.error, "Job scheduling") : null;
  return <section className="rounded-xl border border-stroke bg-surface p-4 sm:p-6" aria-labelledby="schedule-job-heading">
    <h3 id="schedule-job-heading" className="text-xl font-semibold">Schedule Job</h3>
    <p className="mt-1 text-sm text-content-muted">Book an authoritative Appointment for this Job. Technician assignment is optional and remains human-confirmed.</p>
    {job.status === "in_progress" || job.status === "paused" ? <Alert className="mt-4" variant="warning" title="Unscheduled field work already began">ACP supports emergency work before scheduling. Add the service window now so office, Dispatch, and My Day share the same operating record.</Alert> : null}
    {error ? <Alert className="mt-4" variant="danger" title={error.title} action={error.retryLabel ? <Button variant="outline" onClick={book} disabled={schedule.isPending}>{error.retryLabel}</Button> : undefined}><strong>{error.state.replaceAll("_", " ")}</strong> — {error.message}</Alert> : null}
    {schedule.isSuccess ? <Alert className="mt-4" variant="success" title="Job scheduled">SUCCEEDED — The Appointment was linked to this Job and authoritative operating views were refreshed.{returnTo ? <div className="mt-2"><Link className="font-semibold underline" to={schedulingReturnPath(returnTo)}>Return to prior Schedule view</Link></div> : null}</Alert> : null}
    <form className="mt-5 grid gap-4 sm:grid-cols-2" onSubmit={submit}>
      <Field label="Arrival window starts" required><Input type="datetime-local" value={startAt} onChange={(event) => setStartAt(event.target.value)} required /></Field>
      <Field label="Arrival window ends" required helperText={startAt && endAt && new Date(endAt) <= new Date(startAt) ? "Arrival window must end after it starts." : "Customer-facing arrival window; separate from expected work duration."}><Input type="datetime-local" value={endAt} onChange={(event) => setEndAt(event.target.value)} min={startAt || undefined} required /></Field>
      <Field label="Expected duration (minutes)" required><Input type="number" min={15} max={1440} value={duration} onChange={(event) => setDuration(Number(event.target.value))} required /></Field>
      <Field label="Technician" helperText={canAssign ? "Leave Unassigned when Dispatch should decide later." : "Dispatch assignment requires additional authority."} className="sm:col-span-2">
        <Select value={employeeId} onChange={(event) => setEmployeeId(event.target.value)} disabled={!canAssign || workforce.isLoading}>
          <option value="">Unassigned / Needs Scheduling</option>
          {technicians.map((employee) => <option key={employee.employee_id} value={employee.employee_id}>{employee.display_name} — {employee.employee_number}</option>)}
        </Select>
      </Field>
      <div className="sm:col-span-2 sm:flex sm:justify-end"><Button type="submit" loading={schedule.isPending} disabled={schedule.isPending || !startAt || !endAt || new Date(endAt) <= new Date(startAt) || duration < 15}>Book Appointment</Button></div>
    </form>
  </section>;
}
