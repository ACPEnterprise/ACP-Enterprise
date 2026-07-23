import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { getOperatorApiError } from "../../api/errors";
import { useCreateJobFromAppointment } from "../../hooks/useJobs";
import { jobDetailPath } from "../../routing/paths";
import type { JobPriority } from "../../types/jobs";
import type { AppointmentDetail } from "../../types/scheduling";
import { Alert, Button, Field, Input, Select, Textarea } from "../../ui";

export function CreateJobFromAppointmentPanel({ appointment, onCancel }: { readonly appointment: AppointmentDetail; readonly onCancel: () => void }) {
  const navigate = useNavigate();
  const create = useCreateJobFromAppointment(appointment.id);
  const [jobType, setJobType] = useState("");
  const [priority, setPriority] = useState<JobPriority>("normal");
  const [problem, setProblem] = useState("");
  const [description, setDescription] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate({
      job_type_code: jobType.trim() || null,
      priority,
      customer_reported_problem: problem.trim() || null,
      internal_description: description.trim() || null,
    }, { onSuccess: (job) => void navigate(jobDetailPath(job.id)) });
  };
  const error = create.error ? getOperatorApiError(create.error, "Appointment-to-Job") : null;
  return <section className="rounded-xl border border-stroke bg-surface p-ui-6" aria-labelledby="create-appointment-job-heading">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 id="create-appointment-job-heading" className="text-xl font-semibold">Create Job from {appointment.appointment_number}</h3><p className="mt-1 text-sm text-content-muted">Branch, Customer, and Service Location are taken from the Appointment and validated by Jobs.</p></div><Button variant="ghost" onClick={onCancel}>Close</Button></div>
    {error && <Alert className="mt-4" variant="danger" title={error.title}>{error.message}</Alert>}
    <form className="mt-5 grid gap-4 md:grid-cols-2" onSubmit={submit}>
      <Field label="Priority"><Select value={priority} onChange={(event) => setPriority(event.target.value as JobPriority)}>{["low", "normal", "high", "urgent", "emergency"].map((value) => <option key={value} value={value}>{value}</option>)}</Select></Field>
      <Field label="Job type code" helperText="Optional operational code, such as repair or maintenance."><Input value={jobType} maxLength={64} pattern="[a-z][a-z0-9_]*" onChange={(event) => setJobType(event.target.value)} /></Field>
      <Field label="Customer-reported problem" className="md:col-span-2"><Textarea value={problem} onChange={(event) => setProblem(event.target.value)} /></Field>
      <Field label="Internal description" className="md:col-span-2"><Textarea value={description} onChange={(event) => setDescription(event.target.value)} /></Field>
      <div className="flex justify-end gap-2 md:col-span-2"><Button variant="outline" onClick={onCancel}>Cancel</Button><Button type="submit" loading={create.isPending} loadingLabel="Creating Job">Create Job</Button></div>
    </form>
  </section>;
}
