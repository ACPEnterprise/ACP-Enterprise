import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router";

import { useTechnicianField } from "../hooks/useTechnicianField";
import { Alert, Button, Card, CardContent, CardHeader, CardTitle, Spinner } from "../ui";

export function TechnicianJobRoute() {
  const { jobId = "" } = useParams();
  const field = useTechnicianField(jobId, 1, 1);
  const job = field.state;
  return (
    <div className="mx-auto w-full max-w-3xl space-y-ui-5 pb-ui-8">
      <Link className="inline-flex min-h-11 items-center gap-ui-2 font-semibold text-action-primary" to="/technician/jobs">
        <ArrowLeft className="size-4" aria-hidden="true" /> Back to My Jobs
      </Link>
      {job.isLoading && <Spinner label="Loading your job" size="large" />}
      {job.isError && <Alert variant="danger" title="Job unavailable">This Job is not assigned to you, or the assignment is no longer available.</Alert>}
      {job.data && (
        <Card>
          <CardHeader><CardTitle>Assigned Job</CardTitle></CardHeader>
          <CardContent className="space-y-ui-2 text-body-s">
            <p>Assignment: {job.data.assignment_id}</p>
            <p>{job.data.completion_ready ? "Completion requirements satisfied" : "Work remains in progress"}</p>
            {job.data.missing_requirements.length > 0 && <p>Still needed: {job.data.missing_requirements.join(", ")}</p>}
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
