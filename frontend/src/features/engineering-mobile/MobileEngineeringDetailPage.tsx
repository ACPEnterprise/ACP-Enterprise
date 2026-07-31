import { useState } from "react";
import { Link, useParams } from "react-router";

import { getOperatorApiError } from "../../api/errors";
import { Alert, Badge, Button, Card, ConfirmationDialog, Spinner } from "../../ui";
import { useControlMobileWorkstream, useMobileWorkstream } from "./hooks";
import { mobileEngineeringLabel, mobileEngineeringTimestamp, shortExpectedHead } from "./presentation";
import type { MobileWorkstreamAction } from "./types";

const pipeline = ["queued", "running", "waiting_for_owner", "validating", "deploying_preview", "completed"] as const;

export function MobileEngineeringDetailPage() {
  const { commandId } = useParams();
  const query = useMobileWorkstream(commandId);
  const control = useControlMobileWorkstream(commandId ?? "");
  const [confirmation, setConfirmation] = useState<MobileWorkstreamAction | null>(null);

  if (query.isLoading) return <div className="flex min-h-48 items-center justify-center"><Spinner label="Loading engineering workstream" /></div>;
  if (query.isError || !query.data) {
    const error = getOperatorApiError(query.error, "Engineering workstream");
    return <Alert variant="danger" announcement="assertive" title={error.title} action={error.retryable ? <Button variant="outline" onClick={() => void query.refetch()}>Retry</Button> : undefined}>{error.message}</Alert>;
  }
  const workstream = query.data;
  const act = (action: MobileWorkstreamAction) => {
    if (action === "refresh") { void query.refetch(); return; }
    control.mutate({ action }, { onSuccess: () => setConfirmation(null) });
  };

  return <div className="mx-auto w-full max-w-5xl space-y-ui-5 overflow-x-hidden pb-24">
    <Link className="inline-flex min-h-11 items-center text-sm font-semibold text-blue-400 hover:underline" to="/engineering">← Workstreams</Link>
    <header className="flex min-w-0 flex-wrap items-start justify-between gap-ui-3">
      <div className="min-w-0"><p className="text-sm font-semibold text-blue-400">Engineering Control</p><h1 className="mt-ui-1 break-all text-2xl font-bold sm:text-3xl">{workstream.ecid}</h1><p className="mt-ui-2 break-words text-content-muted">{workstream.repository_key} · {workstream.expected_branch}</p></div>
      <div className="flex flex-wrap gap-ui-2"><Badge>{mobileEngineeringLabel(workstream.pipeline_status)}</Badge>{workstream.owner_attention_required && <Badge>Owner attention</Badge>}</div>
    </header>

    <Card className="p-ui-4">
      <h2 className="font-bold">Status pipeline</h2>
      <ol className="mt-ui-4 grid grid-cols-2 gap-ui-2 text-xs sm:grid-cols-3 lg:grid-cols-6">
        {pipeline.map((step) => <li key={step} aria-current={workstream.pipeline_status === step ? "step" : undefined} className={`rounded-lg border p-ui-2 ${workstream.pipeline_status === step ? "border-blue-400 bg-blue-400/10 font-bold" : "border-stroke text-content-muted"}`}>{mobileEngineeringLabel(step)}</li>)}
      </ol>
      {["failed", "cancelled"].includes(workstream.pipeline_status) && <Alert className="mt-ui-4" variant={workstream.pipeline_status === "failed" ? "danger" : "warning"} title={mobileEngineeringLabel(workstream.pipeline_status)}>This workstream exited the standard completion pipeline.</Alert>}
    </Card>

    {workstream.control_pending && <Alert variant="warning" title="Control request pending">The owner intent is saved. Observed worker state remains authoritative until acknowledgement.</Alert>}
    {control.isError && <Alert variant="danger" announcement="assertive" title="Action not accepted">{getOperatorApiError(control.error, "Workstream action").message}</Alert>}

    <div className="grid gap-ui-4 lg:grid-cols-2">
      <Card className="min-w-0 p-ui-4"><h2 className="font-bold">Current work</h2><p className="mt-ui-3 whitespace-pre-wrap break-words text-sm">{workstream.owner_instruction}</p><dl className="mt-ui-4 grid gap-ui-3 text-sm"><div><dt className="text-content-muted">Progress</dt><dd>{workstream.progress_summary}</dd></div><div><dt className="text-content-muted">Worker</dt><dd className="break-all">{workstream.assigned_worker_id ?? "Not assigned"}</dd></div><div><dt className="text-content-muted">Last heartbeat</dt><dd>{mobileEngineeringTimestamp(workstream.heartbeat_at)}</dd></div></dl></Card>
      <Card className="min-w-0 p-ui-4"><h2 className="font-bold">Delivery</h2><dl className="mt-ui-3 grid gap-ui-3 text-sm"><div><dt className="text-content-muted">Expected HEAD</dt><dd className="break-all font-mono">{shortExpectedHead(workstream.expected_head)}</dd></div><div><dt className="text-content-muted">Change level</dt><dd>{workstream.requested_code_changes ? "Code changes" : "Inspection only"}</dd></div><div><dt className="text-content-muted">Preview operation</dt><dd>{mobileEngineeringLabel(workstream.repository_operation_status ?? "not_started")}</dd></div><div><dt className="text-content-muted">Result commit</dt><dd className="break-all font-mono">{workstream.resulting_commit_sha ?? "Not available"}</dd></div></dl></Card>
    </div>

    <Card className="p-ui-4"><h2 className="font-bold">Activity</h2>{workstream.timeline.length === 0 ? <p className="mt-ui-3 text-sm text-content-muted">No activity recorded.</p> : <ol className="mt-ui-3 space-y-ui-3">{[...workstream.timeline].reverse().map((item) => <li key={`${item.event}-${item.occurred_at}`} className="border-l-2 border-stroke pl-ui-3 text-sm"><p className="font-semibold">{mobileEngineeringLabel(item.event)}</p><time className="text-content-muted">{mobileEngineeringTimestamp(item.occurred_at)}</time></li>)}</ol>}</Card>

    <section className="fixed inset-x-0 bottom-0 z-20 border-t border-stroke bg-surface/95 p-ui-3 backdrop-blur sm:static sm:rounded-xl sm:border" aria-label="Owner actions">
      <div className="mx-auto flex max-w-5xl flex-wrap gap-ui-2">
        {workstream.available_actions.map((action) => <Button key={action} className="min-w-24 flex-1 sm:flex-none" variant={action === "cancel" ? "destructive" : action === "refresh" ? "outline" : "primary"} disabled={control.isPending} onClick={() => action === "refresh" ? act(action) : setConfirmation(action)}>{mobileEngineeringLabel(action)}</Button>)}
      </div>
    </section>

    {confirmation && confirmation !== "refresh" && <ConfirmationDialog title={`${mobileEngineeringLabel(confirmation)} this workstream?`} confirmLabel={mobileEngineeringLabel(confirmation)} destructive={confirmation === "cancel"} pending={control.isPending} onCancel={() => setConfirmation(null)} onConfirm={() => act(confirmation)}><p><strong>{workstream.ecid}</strong></p><p>{confirmation === "start" ? "This requests execution through the existing controlled execution service." : "The owner intent is persisted; runtime status changes only after worker acknowledgement."}</p></ConfirmationDialog>}
  </div>;
}
