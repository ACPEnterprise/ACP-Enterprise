import { useMemo, useState, type FormEvent } from "react";

import { getOperatorApiError } from "../../api/errors";
import { useScheduleExistingJob } from "../../hooks/useOperations";
import { useWorkforceDirectory } from "../../hooks/useWorkforce";
import type { JobDetail } from "../../types/jobs";
import { Alert, Button, Field, Input, Select } from "../../ui";

const localInput = (date: Date) => {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

export function ScheduleJobPanel({ job, canAssign }: {
  readonly job: JobDetail;
  readonly canAssign: boolean;
}) {
  const schedule = useScheduleExistingJob(job.id);
  const workforce = useWorkforceDirectory();
  const [startAt, setStartAt] = useState(() => localInput(new Date(Date.now() + 60 * 60 * 1000)));
  const [duration, setDuration] = useState(120);
  const [employeeId, setEmployeeId] = useState("");
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const technicians = useMemo(
    () => (workforce.data ?? []).filter((employee) =>
      employee.technician && employee.employee_status === "active" &&
      (!employee.home_branch_id || employee.home_branch_id === job.branch_id)),
    [job.branch_id, workforce.data],
  );
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const start = new Date(startAt);
    if (Number.isNaN(start.getTime()) || duration < 15) return;
    schedule.mutate({
      request_id: requestId,
      expected_job_version: job.concurrency_version,
      branch_id: job.branch_id,
      customer_id: job.customer.id,
      service_location_id: job.service_location.id,
      arrival_window_start_at: start.toISOString(),
      arrival_window_end_at: new Date(start.getTime() + duration * 60_000).toISOString(),
      expected_duration_minutes: duration,
      capacity_units: "1.00",
      employee_id: employeeId || null,
    }, { onSuccess: () => setRequestId(crypto.randomUUID()) });
  };
  const error = schedule.error ? getOperatorApiError(schedule.error, "Job scheduling") : null;
  return <section className="rounded-xl border border-stroke bg-surface p-4 sm:p-6" aria-labelledby="schedule-job-heading">
    <h3 id="schedule-job-heading" className="text-xl font-semibold">Schedule Job</h3>
    <p className="mt-1 text-sm text-content-muted">Book an authoritative Appointment for this Job. Technician assignment is optional and remains human-confirmed.</p>
    {job.status === "in_progress" || job.status === "paused" ? <Alert className="mt-4" variant="warning" title="Unscheduled field work already began">ACP supports emergency work before scheduling. Add the service window now so office, Dispatch, and My Day share the same operating record.</Alert> : null}
    {error ? <Alert className="mt-4" variant="danger" title={error.title}>{error.message}</Alert> : null}
    {schedule.isSuccess ? <Alert className="mt-4" variant="success" title="Job scheduled">The Appointment was linked to this Job and operating views are refreshing.</Alert> : null}
    <form className="mt-5 grid gap-4 sm:grid-cols-2" onSubmit={submit}>
      <Field label="Arrival window starts" required><Input type="datetime-local" value={startAt} onChange={(event) => setStartAt(event.target.value)} required /></Field>
      <Field label="Expected duration (minutes)" required><Input type="number" min={15} max={1440} value={duration} onChange={(event) => setDuration(Number(event.target.value))} required /></Field>
      <Field label="Technician" helperText={canAssign ? "Leave Unassigned when Dispatch should decide later." : "Dispatch assignment requires additional authority."} className="sm:col-span-2">
        <Select value={employeeId} onChange={(event) => setEmployeeId(event.target.value)} disabled={!canAssign || workforce.isLoading}>
          <option value="">Unassigned / Needs Scheduling</option>
          {technicians.map((employee) => <option key={employee.employee_id} value={employee.employee_id}>{employee.display_name} — {employee.employee_number}</option>)}
        </Select>
      </Field>
      <div className="sm:col-span-2 sm:flex sm:justify-end"><Button type="submit" loading={schedule.isPending} disabled={schedule.isPending || !startAt || duration < 15}>Book Appointment</Button></div>
    </form>
  </section>;
}
