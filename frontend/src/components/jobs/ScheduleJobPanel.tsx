import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useScheduleExistingJob } from "../../hooks/useOperations";
import { zonedDateTimeInput, zonedDateTimeToIso } from "../dispatch/dispatchPresentation";
import { schedulingReturnPath } from "../../routing/paths";
import type { JobDetail } from "../../types/jobs";
import { Alert, Button, Field, Input } from "../../ui";
import { schedulingMutationRecovery } from "../scheduling/schedulingRecovery";

export function ScheduleJobPanel({ job, timeZone, returnTo }: {
  readonly job: JobDetail;
  readonly timeZone: string;
  readonly returnTo?: string;
}) {
  const schedule = useScheduleExistingJob(job.id);
  const [startAt, setStartAt] = useState(() => zonedDateTimeInput(new Date(Date.now() + 60 * 60 * 1000).toISOString(), timeZone));
  const [endAt, setEndAt] = useState(() => zonedDateTimeInput(new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString(), timeZone));
  const [duration, setDuration] = useState(120);
  const [lastAttempt, setLastAttempt] = useState<{ fingerprint: string; requestId: string } | null>(null);
  const book = () => {
    const start = zonedDateTimeToIso(startAt, timeZone);
    const end = zonedDateTimeToIso(endAt, timeZone);
    if (end <= start || duration < 15) return;
    const intent = {
      expected_job_version: job.concurrency_version,
      branch_id: job.branch_id,
      customer_id: job.customer.id,
      service_location_id: job.service_location.id,
      arrival_window_start_at: start,
      arrival_window_end_at: end,
      expected_duration_minutes: duration,
      capacity_units: "1.00",
      reserve_capacity: false,
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
      <Field label="Arrival window ends" required helperText={startAt && endAt && zonedDateTimeToIso(endAt, timeZone) <= zonedDateTimeToIso(startAt, timeZone) ? "Arrival window must end after it starts." : "Customer-facing arrival window; separate from expected work duration."}><Input type="datetime-local" value={endAt} onChange={(event) => setEndAt(event.target.value)} min={startAt || undefined} required /></Field>
      <Field label="Expected duration (minutes)" required><Input type="number" min={15} max={1440} value={duration} onChange={(event) => setDuration(Number(event.target.value))} required /></Field>
      <Alert className="sm:col-span-2" title="Technician assignment follows scheduling">The Appointment will enter Dispatch unassigned. Select a technician there using appointment-specific Branch, capability, availability, and conflict evidence.</Alert>
      <div className="sm:col-span-2 sm:flex sm:justify-end"><Button type="submit" loading={schedule.isPending} disabled={schedule.isPending || !startAt || !endAt || zonedDateTimeToIso(endAt, timeZone) <= zonedDateTimeToIso(startAt, timeZone) || duration < 15}>Book Appointment</Button></div>
    </form>
  </section>;
}
