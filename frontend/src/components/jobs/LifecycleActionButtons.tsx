import { useState } from "react";

import { getApiErrorMessage } from "../../api/errors";
import {
  useActivateJob, useCancelJob, useCompleteJob, usePauseJob,
  useReopenJob, useResumeJob, useStartJob,
} from "../../hooks/useJobs";
import type { JobDetail } from "../../types/jobs";
import { Alert, Button } from "../../ui";

interface MutationAction { mutate: (input: never, options: { onError: (value: unknown) => void }) => void; }

export function LifecycleActionButtons({ job }: { readonly job: JobDetail }) {
  const [error, setError] = useState<unknown>();
  const activate = useActivateJob(job.id); const start = useStartJob(job.id);
  const pause = usePauseJob(job.id); const resume = useResumeJob(job.id);
  const complete = useCompleteJob(job.id); const cancel = useCancelJob(job.id);
  const reopen = useReopenJob(job.id);
  const run = (action: MutationAction, input: object) => {
    setError(undefined); action.mutate(input as never, { onError: setError });
  };
  const version = { expected_version: job.concurrency_version };
  return <div>
    <div className="flex flex-wrap gap-2">
      {job.status === "draft" && <Button onClick={() => run(activate, version)}>Activate</Button>}
      {job.status === "ready" && <Button onClick={() => run(start, version)}>Start</Button>}
      {job.status === "in_progress" && <>
        <Button onClick={() => run(pause, { ...version, reason_code: "operational_hold" })}>Pause</Button>
        <Button onClick={() => run(complete, version)}>Complete</Button>
      </>}
      {job.status === "paused" && <Button onClick={() => run(resume, version)}>Resume</Button>}
      {(job.status === "draft" || job.status === "ready") && <Button variant="destructive" onClick={() => run(cancel, { ...version, reason_code: "customer_cancelled" })}>Cancel</Button>}
      {(job.status === "completed" || job.status === "cancelled") && <Button onClick={() => run(reopen, { ...version, reason_code: "additional_work_required" })}>Reopen</Button>}
    </div>
    {error !== undefined && <Alert className="mt-3" variant="danger">{getApiErrorMessage(error)}</Alert>}
  </div>;
}
