import { useState } from "react";
import { Link, useParams } from "react-router";

import { getOperatorApiError } from "../../api/errors";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmationDialog,
  Spinner,
} from "../../ui";
import {
  useApproveMobileReview,
  useCancelMobileReview,
  useControlMobileWorkstream,
  useDecideEngineeringReview,
  useMobileReview,
  useMobileWorkstream,
} from "./hooks";
import {
  mobileEngineeringLabel,
  mobileEngineeringRelativeTime,
  mobileEngineeringTimestamp,
  shortExpectedHead,
  workstreamDisplayName,
} from "./presentation";
import type { MobileWorkstreamAction } from "./types";
import { useEngineeringRealtime } from "./realtime";

const pipeline = [
  "queued",
  "acknowledged",
  "running",
  "paused",
  "waiting_for_owner",
  "validating",
  "deploying_preview",
  "completed",
] as const;

function duration(milliseconds: number | null): string {
  if (milliseconds == null) return "Pending";
  if (milliseconds < 1000) return `${milliseconds} ms`;
  return `${(milliseconds / 1000).toFixed(1)} s`;
}

function stageStatus(status: string, milliseconds: number | null): string {
  if (!status) return "Pending";
  if (status === "completed" || status === "recorded") {
    return milliseconds == null
      ? "Completed"
      : `Completed · ${duration(milliseconds)}`;
  }
  if (status === "completed_from_immutable_evidence") {
    return "Completed · immutable provider evidence";
  }
  if (status === "not_performed") return "Not performed by this execution";
  if (status === "not_recorded") return "No deployment recorded";
  if (status === "incomplete") return "Incomplete";
  return mobileEngineeringLabel(status);
}

function ReadableInstruction({ value }: { value: string }) {
  const lines = value.split("\n");
  return (
    <div className="mt-ui-3 space-y-ui-2 text-sm leading-6">
      {lines.map((line, index) => {
        const heading = line.match(/^#{1,4}\s+(.+)$/);
        const bullet = line.match(/^[-*]\s+(.+)$/);
        if (!line.trim()) return <div key={index} className="h-ui-1" />;
        if (heading)
          return (
            <h3 key={index} className="pt-ui-2 font-bold">
              {heading[1]}
            </h3>
          );
        if (bullet)
          return (
            <p
              key={index}
              className="pl-ui-4 before:mr-ui-2 before:content-['•']"
            >
              {bullet[1]}
            </p>
          );
        return <p key={index}>{line}</p>;
      })}
    </div>
  );
}

export function MobileEngineeringDetailPage() {
  const { commandId } = useParams();
  const query = useMobileWorkstream(commandId);
  const control = useControlMobileWorkstream(commandId ?? "");
  const review = useMobileReview(commandId);
  const approve = useApproveMobileReview(commandId ?? "");
  const cancelReview = useCancelMobileReview(commandId ?? "");
  const decideResult = useDecideEngineeringReview(
    commandId ?? "",
    query.data?.review_id ?? null,
  );
  const realtime = useEngineeringRealtime();
  const [observedAt] = useState(() => Date.now());
  const [confirmation, setConfirmation] =
    useState<MobileWorkstreamAction | null>(null);
  const [reviewDecision, setReviewDecision] = useState<
    "reject" | "revision" | null
  >(null);
  const [acceptResult, setAcceptResult] = useState(false);

  if (query.isLoading)
    return (
      <div className="flex min-h-48 items-center justify-center">
        <Spinner label="Loading engineering workstream" />
      </div>
    );
  if (query.isError || !query.data) {
    const error = getOperatorApiError(query.error, "Engineering workstream");
    return (
      <Alert
        variant="danger"
        announcement="assertive"
        title={error.title}
        action={
          error.retryable ? (
            <Button variant="outline" onClick={() => void query.refetch()}>
              Retry
            </Button>
          ) : undefined
        }
      >
        {error.message}
      </Alert>
    );
  }
  const workstream = query.data;
  const act = (action: MobileWorkstreamAction) => {
    control.mutate({ action }, { onSuccess: () => setConfirmation(null) });
  };
  const approveCommand = () => {
    if (!review.data) return;
    approve.mutate({
      expected_version: review.data.version,
      instruction_digest: review.data.instruction_digest,
      request_digest: review.data.request_digest,
      repository_key: review.data.repository_key,
      expected_branch: review.data.expected_branch,
      expected_head: review.data.expected_head,
      requested_code_changes: review.data.requested_code_changes,
    });
  };
  const declineCommand = () => {
    if (!review.data || !reviewDecision) return;
    cancelReview.mutate(
      {
        expected_version: review.data.version,
        reason_code:
          reviewDecision === "revision" ? "scope_changed" : "owner_requested",
      },
      { onSuccess: () => setReviewDecision(null) },
    );
  };

  return (
    <div className="mx-auto w-full max-w-5xl space-y-ui-5 overflow-x-hidden pb-24">
      <Link
        className="inline-flex min-h-11 items-center text-sm font-semibold text-blue-400 hover:underline"
        to="/engineering"
      >
        ← Workstreams
      </Link>
      <header className="flex min-w-0 flex-wrap items-start justify-between gap-ui-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-blue-400">
            Engineering Control · Live {realtime}
          </p>
          <h1 className="mt-ui-1 text-2xl font-bold leading-tight sm:text-3xl">
            {workstreamDisplayName(workstream.display_name, workstream.ecid)}
          </h1>
          <p className="mt-ui-2 break-words text-sm text-content-muted">
            {workstream.ecid} · {workstream.repository_key} ·{" "}
            {workstream.expected_branch}
          </p>
        </div>
        <div className="flex flex-wrap gap-ui-2">
          <Badge>{mobileEngineeringLabel(workstream.pipeline_status)}</Badge>
          {workstream.owner_attention_required && (
            <Badge>Owner attention</Badge>
          )}
        </div>
      </header>

      <Card className="p-ui-4">
        <h2 className="font-bold">Status pipeline</h2>
        <ol className="mt-ui-4 grid grid-cols-2 gap-ui-2 text-xs sm:grid-cols-3 lg:grid-cols-6">
          {pipeline.map((step) => (
            <li
              key={step}
              aria-current={
                workstream.pipeline_status === step ? "step" : undefined
              }
              className={`rounded-lg border p-ui-2 ${workstream.pipeline_status === step ? "border-blue-400 bg-blue-400/10 font-bold" : "border-stroke text-content-muted"}`}
            >
              {mobileEngineeringLabel(step)}
            </li>
          ))}
        </ol>
        {["failed", "cancelled"].includes(workstream.pipeline_status) && (
          <Alert
            className="mt-ui-4"
            variant={
              workstream.pipeline_status === "failed" ? "danger" : "warning"
            }
            title={mobileEngineeringLabel(workstream.pipeline_status)}
          >
            This workstream exited the standard completion pipeline.
          </Alert>
        )}
      </Card>

      {workstream.control_pending && (
        <Alert variant="warning" title="Control request pending">
          The owner intent is saved. Observed worker state remains authoritative
          until acknowledgement.
        </Alert>
      )}
      {workstream.runtime_state === "recovering" && (
        <Alert variant="warning" title="Worker recovering">
          The last acknowledgement expired. The reconnected worker must
          acknowledge the current owner request before execution continues.
        </Alert>
      )}
      {control.isError && (
        <Alert
          variant="danger"
          announcement="assertive"
          title="Action not accepted"
        >
          {getOperatorApiError(control.error, "Workstream action").message}
        </Alert>
      )}
      {review.data?.can_approve && (
        <Alert variant="warning" title="Your decision is needed">
          <p>
            Review the requested outcome, destination, and change authority
            below.
          </p>
          <div className="mt-ui-3 flex flex-wrap gap-ui-2">
            <Button
              className="min-h-11"
              disabled={approve.isPending}
              onClick={approveCommand}
            >
              {approve.isPending ? "Approving…" : "Approve"}
            </Button>
            <Button
              className="min-h-11"
              variant="outline"
              onClick={() => setReviewDecision("revision")}
            >
              Request revision
            </Button>
            <Button
              className="min-h-11"
              variant="destructive"
              onClick={() => setReviewDecision("reject")}
            >
              Reject
            </Button>
          </div>
        </Alert>
      )}
      {workstream.owner_review_action_available && (
        <Alert variant="warning" title="Owner review prepared">
          <p>
            The published result and its immutable validation evidence are ready
            for your decision.
          </p>
          <div className="mt-ui-3">
            <Button
              className="min-h-11"
              disabled={decideResult.isPending}
              onClick={() => setAcceptResult(true)}
            >
              Review and accept published result
            </Button>
          </div>
        </Alert>
      )}
      {approve.isError && (
        <Alert
          variant="danger"
          announcement="assertive"
          title="Approval not accepted"
        >
          {getOperatorApiError(approve.error, "Owner approval").message}
        </Alert>
      )}
      {decideResult.isError && (
        <Alert
          variant="danger"
          announcement="assertive"
          title="Review decision not accepted"
        >
          {getOperatorApiError(decideResult.error, "Owner review").message}
        </Alert>
      )}

      <div className="grid gap-ui-4 lg:grid-cols-2">
        <Card className="min-w-0 p-ui-4">
          <h2 className="font-bold">Current work</h2>
          <ReadableInstruction value={workstream.owner_instruction} />
          <dl className="mt-ui-4 grid gap-ui-3 text-sm">
            <div>
              <dt className="text-content-muted">Progress</dt>
              <dd>
                {workstream.progress_percent == null
                  ? workstream.progress_summary
                  : `${workstream.progress_percent}% · ${workstream.current_activity ?? workstream.progress_summary}`}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Worker status</dt>
              <dd className="font-semibold">
                {mobileEngineeringLabel(
                  workstream.worker_health ?? "not_available",
                )}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Last signal</dt>
              <dd>
                {mobileEngineeringRelativeTime(
                  workstream.heartbeat_at,
                  observedAt,
                )}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Request acknowledged</dt>
              <dd>
                {mobileEngineeringRelativeTime(
                  workstream.acknowledged_at,
                  observedAt,
                )}
              </dd>
            </div>
          </dl>
        </Card>
        <Card className="min-w-0 p-ui-4">
          <h2 className="font-bold">Delivery</h2>
          <dl className="mt-ui-3 grid gap-ui-3 text-sm">
            <div>
              <dt className="text-content-muted">Starting HEAD</dt>
              <dd className="break-all font-mono">
                {shortExpectedHead(workstream.expected_head)}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Change level</dt>
              <dd>
                {workstream.requested_code_changes
                  ? "Code changes"
                  : "Inspection only"}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Result publication</dt>
              <dd>{stageStatus(workstream.result_publication_status, null)}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Adoption</dt>
              <dd>
                {mobileEngineeringLabel(
                  workstream.result_adoption_status ?? "not_adopted",
                )}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Preview deployment</dt>
              <dd>
                {stageStatus(
                  workstream.preview_deployment_status,
                  workstream.deployment_latency_ms,
                )}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Published result commit</dt>
              <dd className="break-all font-mono">
                {workstream.result_commit_sha ?? "Not available"}
              </dd>
            </div>
          </dl>
        </Card>
      </div>

      <Card className="p-ui-4">
        <h2 className="font-bold">Engineering metrics</h2>
        <dl className="mt-ui-3 grid grid-cols-2 gap-ui-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-content-muted">Acknowledgement</dt>
            <dd>
              {stageStatus(
                workstream.acknowledgement_status,
                workstream.acknowledgement_latency_ms,
              )}
            </dd>
          </div>
          <div>
            <dt className="text-content-muted">Execution</dt>
            <dd>
              {stageStatus(
                workstream.execution_status,
                workstream.execution_latency_ms,
              )}
            </dd>
          </div>
          <div>
            <dt className="text-content-muted">Validation</dt>
            <dd>
              {stageStatus(
                workstream.validation_status,
                workstream.validation_latency_ms,
              )}
            </dd>
          </div>
          <div>
            <dt className="text-content-muted">Deployment</dt>
            <dd>
              {stageStatus(
                workstream.preview_deployment_status,
                workstream.deployment_latency_ms,
              )}
            </dd>
          </div>
          <div>
            <dt className="text-content-muted">Worker uptime</dt>
            <dd>
              {workstream.worker_uptime_seconds == null
                ? "Not recorded"
                : `${workstream.worker_uptime_seconds} s`}
            </dd>
          </div>
          <div>
            <dt className="text-content-muted">Reconnects</dt>
            <dd>{workstream.reconnect_count}</dd>
          </div>
        </dl>
      </Card>

      {(workstream.historical_recovery_context?.length ?? 0) > 0 && (
        <Card className="p-ui-4">
          <h2 className="font-bold">Historical recovery context</h2>
          <p className="mt-ui-2 text-sm text-content-muted">
            These preserved events are not the current result under review.
          </p>
          {workstream.historical_recovery_context?.map((item) => (
            <Alert
              key={`${item.classification}-${item.reason_code ?? "none"}`}
              className="mt-ui-3"
              variant="warning"
              title="Historical transport recovery"
            >
              {item.summary}
            </Alert>
          ))}
        </Card>
      )}

      <Card className="p-ui-4">
        <h2 className="text-lg font-bold">Journey</h2>
        <p className="mt-1 text-sm text-content-muted">
          A clear timeline of progress, validation, and delivery.
        </p>
        {workstream.timeline.length === 0 ? (
          <p className="mt-ui-3 text-sm text-content-muted">
            No activity recorded.
          </p>
        ) : (
          <ol className="relative mt-ui-5 space-y-0">
            {[...workstream.timeline].map((item, index, timeline) => {
              const previous = timeline[index - 1];
              const elapsed = previous
                ? Math.max(
                    0,
                    new Date(item.occurred_at).getTime() -
                      new Date(previous.occurred_at).getTime(),
                  )
                : null;
              return (
                <li
                  key={`${item.event}-${item.occurred_at}`}
                  className="relative grid grid-cols-[2rem_1fr] gap-ui-3 pb-ui-5 last:pb-0"
                >
                  <div className="flex flex-col items-center">
                    <span className="z-10 mt-1 h-3 w-3 rounded-full border-2 border-blue-400 bg-surface" />
                    {index < timeline.length - 1 && (
                      <span className="absolute bottom-0 top-4 w-px bg-stroke" />
                    )}
                  </div>
                  <div>
                    <div className="flex flex-wrap items-baseline justify-between gap-ui-2">
                      <p className="font-semibold">
                        {mobileEngineeringLabel(item.event)}
                      </p>
                      {elapsed != null && (
                        <span className="text-xs text-content-muted">
                          +{duration(elapsed)}
                        </span>
                      )}
                    </div>
                    <time className="text-sm text-content-muted">
                      {mobileEngineeringTimestamp(item.occurred_at)}
                    </time>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </Card>

      <section
        className="fixed inset-x-0 bottom-0 z-20 border-t border-stroke bg-surface/95 p-ui-3 backdrop-blur sm:static sm:rounded-xl sm:border"
        aria-label="Owner actions"
      >
        <div className="mx-auto flex max-w-5xl flex-wrap gap-ui-2">
          {workstream.available_actions.map((action) => (
            <Button
              key={action}
              className="min-w-24 flex-1 sm:flex-none"
              variant={action === "cancel" ? "destructive" : "primary"}
              disabled={control.isPending}
              onClick={() => setConfirmation(action)}
            >
              {mobileEngineeringLabel(action)}
            </Button>
          ))}
        </div>
      </section>

      {confirmation && (
        <ConfirmationDialog
          title={`${mobileEngineeringLabel(confirmation)} this workstream?`}
          confirmLabel={mobileEngineeringLabel(confirmation)}
          destructive={confirmation === "cancel"}
          pending={control.isPending}
          onCancel={() => setConfirmation(null)}
          onConfirm={() => act(confirmation)}
        >
          <p>
            <strong>{workstream.ecid}</strong>
          </p>
          <p>
            {confirmation === "start"
              ? "This requests execution through the existing controlled execution service."
              : "The owner intent is persisted; runtime status changes only after worker acknowledgement."}
          </p>
        </ConfirmationDialog>
      )}
      {reviewDecision && (
        <ConfirmationDialog
          title={
            reviewDecision === "revision"
              ? "Request a revised command?"
              : "Reject this command?"
          }
          confirmLabel={
            reviewDecision === "revision" ? "Request revision" : "Reject"
          }
          destructive={reviewDecision === "reject"}
          pending={cancelReview.isPending}
          onCancel={() => setReviewDecision(null)}
          onConfirm={declineCommand}
        >
          <p>
            {reviewDecision === "revision"
              ? "This closes the current approval request because its scope must change. A revised command can then be submitted with fresh evidence."
              : "This closes the approval request without starting execution."}
          </p>
        </ConfirmationDialog>
      )}
      {acceptResult &&
        workstream.owner_review_digest &&
        workstream.owner_review_version && (
          <ConfirmationDialog
            title="Accept this published result?"
            confirmLabel="Accept published result"
            pending={decideResult.isPending}
            onCancel={() => setAcceptResult(false)}
            onConfirm={() =>
              decideResult.mutate(
                {
                  expected_version: workstream.owner_review_version!,
                  review_digest: workstream.owner_review_digest!,
                  decision: "accept",
                },
                { onSuccess: () => setAcceptResult(false) },
              )
            }
          >
            <p>
              This records your decision for the immutable result commit shown
              on this page. It does not start another execution.
            </p>
          </ConfirmationDialog>
        )}
    </div>
  );
}
