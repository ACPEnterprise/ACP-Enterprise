import { useState } from "react";

import { getOperatorApiError } from "../../api/errors";
import {
  useActivateJob, useCancelJob, useCompleteJob, usePauseJob,
  useReopenJob, useResumeJob, useStartJob,
} from "../../hooks/useJobs";
import type { JobCancellationReason, JobDetail, JobPauseReason, JobReopeningReason } from "../../types/jobs";
import { Alert, Button, Select } from "../../ui";
import { actionLabels, actionsByStatus, type JobAction } from "./jobPresentation";

const pauseReasons: readonly JobPauseReason[] = ["customer_unavailable", "awaiting_approval", "awaiting_material", "safety_condition", "weather", "operational_hold"];
const cancellationReasons: readonly JobCancellationReason[] = ["customer_cancelled", "duplicate", "created_in_error", "scope_declined", "unable_to_perform"];
const reopeningReasons: readonly JobReopeningReason[] = ["additional_work_required", "incomplete_work", "correction_required", "customer_callback", "administrative_correction"];
const label = (value: string) => value.replaceAll("_", " ");

export function LifecycleActionButtons({ job }: { readonly job: JobDetail }) {
  const [pauseReason, setPauseReason] = useState<JobPauseReason>("operational_hold");
  const [cancelReason, setCancelReason] = useState<JobCancellationReason>("customer_cancelled");
  const [reopenReason, setReopenReason] = useState<JobReopeningReason>("additional_work_required");
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; title: string; message: string }>();
  const activate = useActivateJob(job.id); const start = useStartJob(job.id); const pause = usePauseJob(job.id);
  const resume = useResumeJob(job.id); const complete = useCompleteJob(job.id); const cancel = useCancelJob(job.id); const reopen = useReopenJob(job.id);
  const pending = activate.isPending || start.isPending || pause.isPending || resume.isPending || complete.isPending || cancel.isPending || reopen.isPending;
  const version = { expected_version: job.concurrency_version };
  const success = (action: JobAction) => setFeedback({ kind: "success", title: `${actionLabels[action]} requested`, message: "The refreshed Job state is now shown." });
  const failure = (error: unknown) => { const value = getOperatorApiError(error); setFeedback({ kind: "error", title: value.title, message: value.message }); };
  const execute = (action: JobAction) => {
    setFeedback(undefined);
    if (["complete", "cancel", "reopen"].includes(action) && !window.confirm(`${actionLabels[action]} ${job.job_number}?`)) return;
    const options = { onSuccess: () => success(action), onError: failure };
    if (action === "activate") activate.mutate(version, options);
    if (action === "start") start.mutate(version, options);
    if (action === "pause") pause.mutate({ ...version, reason_code: pauseReason }, options);
    if (action === "resume") resume.mutate(version, options);
    if (action === "complete") complete.mutate(version, options);
    if (action === "cancel") cancel.mutate({ ...version, reason_code: cancelReason }, options);
    if (action === "reopen") reopen.mutate({ ...version, reason_code: reopenReason }, options);
  };
  const actions = actionsByStatus[job.status];
  return <div className="max-w-xl space-y-3">
    {actions.includes("pause") && <label className="flex items-center gap-2 text-sm"><span>Pause reason</span><Select aria-label="Pause reason" value={pauseReason} onChange={(event) => setPauseReason(event.target.value as JobPauseReason)}>{pauseReasons.map((reason) => <option key={reason} value={reason}>{label(reason)}</option>)}</Select></label>}
    {actions.includes("cancel") && <label className="flex items-center gap-2 text-sm"><span>Cancellation reason</span><Select aria-label="Cancellation reason" value={cancelReason} onChange={(event) => setCancelReason(event.target.value as JobCancellationReason)}>{cancellationReasons.map((reason) => <option key={reason} value={reason}>{label(reason)}</option>)}</Select></label>}
    {actions.includes("reopen") && <label className="flex items-center gap-2 text-sm"><span>Reopening reason</span><Select aria-label="Reopening reason" value={reopenReason} onChange={(event) => setReopenReason(event.target.value as JobReopeningReason)}>{reopeningReasons.map((reason) => <option key={reason} value={reason}>{label(reason)}</option>)}</Select></label>}
    <div className="flex flex-wrap justify-end gap-2">{actions.map((action) => <Button key={action} variant={action === "cancel" ? "destructive" : "primary"} disabled={pending} onClick={() => execute(action)}>{actionLabels[action]}</Button>)}</div>
    {feedback && <Alert variant={feedback.kind === "error" ? "danger" : "success"} title={feedback.title}>{feedback.message}</Alert>}
  </div>;
}
