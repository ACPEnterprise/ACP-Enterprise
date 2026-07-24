import { useState } from "react";
import { Link, useParams } from "react-router";

import {
  useApproveEngineeringCommand,
  useCancelEngineeringCommand,
  useEngineeringCommand,
} from "../features/engineering-control/useEngineeringCommands";
import { engineeringLabel, shortHead, timestamp } from "../features/engineering-control/presentation";
import type { EngineeringCancellationReason } from "../types/engineeringControl";
import { Alert, Badge, Button, Card, Select, Spinner } from "../ui";

function Confirmation({
  title,
  children,
  confirmLabel,
  destructive = false,
  busy,
  onCancel,
  onConfirm,
}: {
  title: string;
  children: React.ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return <div role="dialog" aria-modal="true" aria-labelledby="confirmation-title" className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4"><Card className="max-h-[90vh] w-full max-w-lg overflow-y-auto p-ui-6"><h3 id="confirmation-title" className="text-xl font-bold">{title}</h3><div className="mt-4 space-y-3 text-sm">{children}</div><div className="mt-6 grid gap-3 sm:grid-cols-2"><Button variant="outline" onClick={onCancel}>Go back</Button><Button variant={destructive ? "destructive" : "primary"} loading={busy} onClick={onConfirm}>{confirmLabel}</Button></div></Card></div>;
}

export function EngineeringCommandDetailRoute() {
  const { commandId } = useParams();
  const query = useEngineeringCommand(commandId);
  const approve = useApproveEngineeringCommand(commandId ?? "");
  const cancel = useCancelEngineeringCommand(commandId ?? "");
  const [confirmation, setConfirmation] = useState<"approve" | "cancel" | null>(null);
  const [reason, setReason] = useState<EngineeringCancellationReason>("owner_requested");
  const [reviewAgain, setReviewAgain] = useState(false);

  if (query.isLoading) return <div className="flex min-h-48 items-center justify-center"><Spinner label="Loading Engineering Command" /></div>;
  if (query.isError || !query.data) return <Alert variant="danger" announcement="assertive" title="Engineering Command unavailable" action={<Button variant="outline" onClick={() => void query.refetch()}>Retry</Button>}>The command may be unavailable or outside your Company.</Alert>;
  const command = query.data;
  const terminal = ["rejected", "canceled", "expired"].includes(command.approval_state);
  const canApprove = command.approval_state === "awaiting_approval";

  const approveNow = () => {
    setReviewAgain(false);
    approve.mutate({
      expected_version: command.version,
      instruction_digest: command.instruction_digest,
      request_digest: command.request_digest,
      repository_key: command.repository_key,
      expected_branch: command.expected_branch,
      expected_head: command.expected_head,
      requested_code_changes: command.requested_code_changes,
    }, {
      onSuccess: () => setConfirmation(null),
      onError: () => {
        setConfirmation(null);
        setReviewAgain(true);
      },
    });
  };
  const cancelNow = () => cancel.mutate(
    { expected_version: command.version, reason_code: reason },
    { onSuccess: () => setConfirmation(null) },
  );

  return <div className="space-y-6">
    <Link className="text-sm font-semibold text-blue-400 hover:underline" to="/engineering">← Engineering Commands</Link>
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm font-medium text-blue-400">Engineering Control</p><h2 className="mt-1 break-all text-3xl font-bold">{command.ecid}</h2><p className="mt-2 text-content-muted">{engineeringLabel(command.command_type)}</p></div><div className="flex flex-wrap gap-2"><Badge>{engineeringLabel(command.approval_state)}</Badge><Badge>{engineeringLabel(command.execution_state)}</Badge></div></header>
    <Alert variant="warning" title="Approval does not start work">Approval authorizes this command record only. Codex and worker execution remain disconnected. No commit, push, merge, or deployment occurs.</Alert>
    {reviewAgain && <Alert variant="danger" announcement="assertive" title="Review required">The command changed or its evidence did not match. The latest command has been refreshed; review it again before approving.</Alert>}
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="min-w-0 p-ui-5"><h3 className="text-lg font-bold">Identity</h3><dl className="mt-4 grid gap-3 text-sm">
        <div><dt className="text-content-muted">Command ID</dt><dd className="break-all">{command.id}</dd></div>
        <div><dt className="text-content-muted">Repository</dt><dd>{command.repository_key}</dd></div>
        <div><dt className="text-content-muted">Branch</dt><dd className="break-all">{command.expected_branch}</dd></div>
        <div><dt className="text-content-muted">Expected HEAD</dt><dd className="break-all font-mono">{command.expected_head}</dd></div>
        <div><dt className="text-content-muted">Change level</dt><dd>{command.requested_code_changes ? "Uncommitted code changes" : "Inspection only"}</dd></div>
      </dl></Card>
      <Card className="min-w-0 p-ui-5"><h3 className="text-lg font-bold">Lifecycle</h3><dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <div><dt className="text-content-muted">Approval</dt><dd>{engineeringLabel(command.approval_state)}</dd></div>
        <div><dt className="text-content-muted">Execution</dt><dd>Execution not connected</dd></div>
        <div><dt className="text-content-muted">Created</dt><dd>{timestamp(command.created_at)}</dd></div>
        <div><dt className="text-content-muted">Updated</dt><dd>{timestamp(command.updated_at)}</dd></div>
        <div><dt className="text-content-muted">Expires</dt><dd>{timestamp(command.expires_at)}</dd></div>
        <div><dt className="text-content-muted">Version</dt><dd>{command.version}</dd></div>
        {command.approved_at && <div><dt className="text-content-muted">Approved</dt><dd>{timestamp(command.approved_at)}{command.approved_by_user_id ? ` by ${command.approved_by_user_id}` : ""}</dd></div>}
        {command.canceled_at && <div><dt className="text-content-muted">Canceled</dt><dd>{timestamp(command.canceled_at)} · {engineeringLabel(command.cancellation_reason_code ?? "")}</dd></div>}
      </dl></Card>
    </div>
    <Card className="min-w-0 p-ui-5"><h3 className="text-lg font-bold">Owner instruction</h3><p className="mt-4 whitespace-pre-wrap break-words text-sm">{command.owner_instruction}</p><dl className="mt-6 grid gap-4 text-sm"><div><dt className="text-content-muted">Instruction digest</dt><dd className="break-all font-mono">{command.instruction_digest}</dd></div><div><dt className="text-content-muted">Request digest</dt><dd className="break-all font-mono">{command.request_digest}</dd></div></dl></Card>
    <section className="grid gap-5 border-t border-stroke pt-6 sm:grid-cols-2">
      {canApprove && <div><h3 className="font-bold">Approve reviewed command</h3><p className="mt-1 text-sm text-content-muted">Approve only after checking the instruction and evidence above.</p><Button className="mt-4 w-full sm:w-auto" size="large" onClick={() => setConfirmation("approve")}>Approve command</Button></div>}
      {!terminal && <div className="sm:justify-self-end"><label htmlFor="cancel-reason" className="block font-bold">Cancel command</label><Select id="cancel-reason" className="mt-2 min-w-56" value={reason} onChange={(event) => setReason(event.target.value as EngineeringCancellationReason)}><option value="owner_requested">Owner requested</option><option value="scope_changed">Scope changed</option><option value="no_longer_needed">No longer needed</option></Select><Button className="mt-4 w-full sm:w-auto" variant="destructive" onClick={() => setConfirmation("cancel")}>Cancel command</Button></div>}
    </section>
    {confirmation === "approve" && <Confirmation title="Approve this Engineering Command?" confirmLabel="Approve command" busy={approve.isPending} onCancel={() => setConfirmation(null)} onConfirm={approveNow}><p><strong>{command.ecid}</strong></p><p>Repository: {command.repository_key}</p><p>Branch: {command.expected_branch}</p><p>HEAD: <code>{shortHead(command.expected_head)}</code></p><p>Change level: {command.requested_code_changes ? "Uncommitted code changes" : "Inspection only"}</p><p>Expires: {timestamp(command.expires_at)}</p><Alert variant="warning">Execution remains disconnected.</Alert></Confirmation>}
    {confirmation === "cancel" && <Confirmation title="Cancel this Engineering Command?" confirmLabel="Cancel command" destructive busy={cancel.isPending} onCancel={() => setConfirmation(null)} onConfirm={cancelNow}><p>{command.ecid} will be canceled for: <strong>{engineeringLabel(reason)}</strong>.</p><p>Existing evidence is preserved. No workspace is cleaned up.</p></Confirmation>}
  </div>;
}
