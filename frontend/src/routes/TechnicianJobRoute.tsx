import { ArrowLeft, Clock3, Mail, MapPin, Phone } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { useTechnicianField } from "../hooks/useTechnicianField";
import { Alert, Badge, Button, Card, CardContent, CardHeader, CardTitle, Field, Spinner, Textarea } from "../ui";

const appointmentTime = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

export function TechnicianJobRoute() {
  const { jobId = "" } = useParams();
  const field = useTechnicianField(jobId, 1, 1);
  const job = field.state;
  const [workSummary, setWorkSummary] = useState("");
  return (
    <div className="mx-auto w-full max-w-3xl space-y-ui-5 pb-ui-8">
      <Link className="inline-flex min-h-11 items-center gap-ui-2 font-semibold text-action-primary" to="/technician/jobs">
        <ArrowLeft className="size-4" aria-hidden="true" /> Back to My Jobs
      </Link>
      {job.isLoading && <Spinner label="Loading your job" size="large" />}
      {job.isError && <Alert variant="danger" title="Job unavailable">This Job is not assigned to you, or the assignment is no longer available.</Alert>}
      {job.data && (
        <Card>
          <CardHeader className="flex-row flex-wrap items-start justify-between gap-ui-3">
            <div className="min-w-0">
              <p className="text-caption font-semibold text-content-muted">{job.data.job_number}</p>
              <CardTitle className="mt-ui-1 break-words">{job.data.customer_display_name}</CardTitle>
            </div>
            <Badge>{job.data.job_status.replaceAll("_", " ")}</Badge>
          </CardHeader>
          <CardContent className="space-y-ui-4 text-body-s">
            {job.data.window_start_at && (
              <p className="flex gap-ui-2"><Clock3 className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <span>{appointmentTime.format(new Date(job.data.window_start_at))}</span>
              </p>
            )}
            <p className="flex gap-ui-2"><MapPin className="mt-0.5 size-4 shrink-0" aria-hidden="true" /><span>{job.data.service_location_label}</span></p>
            {job.data.contact_display_name && <div className="space-y-ui-2 border-t border-border-subtle pt-ui-3">
              <p className="font-semibold">{job.data.contact_display_name}</p>
              <div className="flex flex-wrap gap-ui-4">
                {job.data.contact_phone && <a className="inline-flex min-h-11 items-center gap-ui-2 font-semibold text-action-primary" href={`tel:${job.data.contact_phone}`}><Phone className="size-4" aria-hidden="true" />Call customer</a>}
                {job.data.contact_email && <a className="inline-flex min-h-11 items-center gap-ui-2 font-semibold text-action-primary" href={`mailto:${job.data.contact_email}`}><Mail className="size-4" aria-hidden="true" />Email customer</a>}
              </div>
            </div>}
            <dl className="grid gap-ui-3 sm:grid-cols-2">
              <div><dt className="font-semibold">Service</dt><dd>{job.data.job_type_code?.replaceAll("_", " ") ?? "Not specified"}</dd></div>
              <div><dt className="font-semibold">Priority</dt><dd>{job.data.priority}</dd></div>
              {job.data.customer_reported_problem && <div className="sm:col-span-2"><dt className="font-semibold">Customer request</dt><dd className="whitespace-pre-wrap break-words">{job.data.customer_reported_problem}</dd></div>}
              {job.data.internal_description && <div className="sm:col-span-2"><dt className="font-semibold">Job details</dt><dd className="whitespace-pre-wrap break-words">{job.data.internal_description}</dd></div>}
            </dl>
          </CardContent>
        </Card>
      )}
      {job.data && (
        <Card>
          <CardHeader><CardTitle>Work and completion</CardTitle></CardHeader>
          <CardContent className="space-y-ui-4">
            {!job.data.work_summary_recorded ? <Field label="Work performed" controlId="technician-work-summary">
              <Textarea id="technician-work-summary" rows={4} value={workSummary} onChange={(event) => setWorkSummary(event.target.value)} />
              <Button className="mt-ui-2" disabled={!workSummary.trim() || field.note.isPending} onClick={() => field.note.mutate(workSummary)}>Save work summary</Button>
            </Field> : <Alert variant="success" title="Work summary saved">The Job has authoritative work notes.</Alert>}
            <div className="space-y-ui-2 text-body-s">
              <p><span className="font-semibold">Estimate authorization:</span> {job.data.commercial_authorization.replaceAll("_", " ")}</p>
              <p><span className="font-semibold">Invoice:</span> {job.data.invoice_handoff_status?.replaceAll("_", " ") ?? "Not ready"}</p>
              <p>{job.data.completion_ready ? "Completion requirements satisfied" : "Work remains in progress"}</p>
              {job.data.missing_requirements.length > 0 && <p>Still needed: {job.data.missing_requirements.join(", ").replaceAll("_", " ")}</p>}
            </div>
            {field.note.isError && <Alert variant="danger" title="Work summary not saved">Refresh the Job and try again. No success was assumed.</Alert>}
          </CardContent>
        </Card>
      )}
      {job.data && (
        <Card>
          <CardHeader><CardTitle>Job activity</CardTitle></CardHeader>
          <CardContent className="space-y-ui-3">
            <p className="text-body-s text-content-muted">Activity classifies time on this assigned Job. It does not clock you in or out of your paid workday.</p>
            <p className="font-semibold">{job.data.visit_finished ? "Visit finished for today" : job.data.active_activity ? job.data.active_activity.replaceAll("_", " ") : "Not started"}</p>
            <div className="flex flex-wrap gap-ui-2">
              {!job.data.active_activity && !job.data.visit_finished && <Button onClick={() => field.activity.mutate({ action: "start", activity: "working", jobVersion: job.data.job_version, appointmentVersion: job.data.appointment_version })}>Start Job</Button>}
              {job.data.active_activity === "working" && <Button variant="outline" onClick={() => field.activity.mutate({ action: "change", activity: "parts_run", jobVersion: job.data.job_version, appointmentVersion: job.data.appointment_version })}>Parts Run</Button>}
              {job.data.active_activity === "parts_run" && <Button onClick={() => field.activity.mutate({ action: "change", activity: "working", jobVersion: job.data.job_version, appointmentVersion: job.data.appointment_version })}>Resume Job</Button>}
              {job.data.active_activity && <Button variant="outline" onClick={() => field.activity.mutate({ action: "finish_visit", activity: null, jobVersion: job.data.job_version, appointmentVersion: job.data.appointment_version })}>Finish for Today</Button>}
              {job.data.visit_finished && <Button onClick={() => field.continuation.mutate()}>Continue Job</Button>}
              {job.data.visit_finished && job.data.completion_ready && <Button variant="outline" onClick={() => field.lifecycle.mutate({ action: "complete", version: job.data.job_version })}>Complete Job</Button>}
            </div>
            {(field.activity.isError || field.continuation.isError || field.lifecycle.isError) && <Alert variant="danger" title="Activity not recorded">Authoritative Job or assignment state changed. Refresh My Day and review this visit before trying again.</Alert>}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
