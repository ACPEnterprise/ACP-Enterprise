import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router";

import { useFieldJobState } from "../hooks/useTechnicianField";
import { Alert, Card, CardContent, CardHeader, CardTitle, Spinner } from "../ui";

export function TechnicianJobRoute() {
  const { jobId = "" } = useParams();
  const job = useFieldJobState(jobId);
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
    </div>
  );
}
