import { useState } from "react";
import { Link, useParams } from "react-router";

import { getOperatorApiError } from "../../api/errors";
import { Alert, Badge, Button, Card, Select, Spinner } from "../../ui";
import { ConfirmationDialog } from "./ConfirmationDialog";
import {
  useApproveMobileReview,
  useCancelMobileReview,
  useMobileCommandStatus,
  useMobileReview,
} from "./hooks";
import {
  mobileEngineeringLabel,
  mobileEngineeringTimestamp,
  shortExpectedHead,
} from "./presentation";
import type { MobileCancellationReason } from "./types";
import { ExecutionMonitoringPanel } from "./execution/ExecutionMonitoringPanel";

export function MobileEngineeringDetailPage() {
  const { commandId } = useParams();
  const query = useMobileReview(commandId);
  const status = useMobileCommandStatus(commandId);
  const approve = useApproveMobileReview(commandId ?? "");
  const cancel = useCancelMobileReview(commandId ?? "");
  const [confirmation, setConfirmation] = useState<
    "approve" | "cancel" | null
  >(null);
  const [reason, setReason] =
    useState<MobileCancellationReason>("owner_requested");
  const [reviewAgain, setReviewAgain] = useState(false);

  if (query.isLoading) {
    return (
      <div className="flex min-h-48 items-center justify-center">
        <Spinner label="Loading engineering review" />
      </div>
    );
  }
  if (query.isError || !query.data) {
    const error = getOperatorApiError(query.error, "Engineering review");
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

  const review = query.data;
  const terminal = ["rejected", "canceled", "expired"].includes(
    review.approval_state,
  );
  const canApprove = review.can_approve;

  const approveNow = () => {
    setReviewAgain(false);
    approve.mutate(
      {
        expected_version: review.version,
        instruction_digest: review.instruction_digest,
        request_digest: review.request_digest,
        repository_key: review.repository_key,
        expected_branch: review.expected_branch,
        expected_head: review.expected_head,
        requested_code_changes: review.requested_code_changes,
      },
      {
        onSuccess: () => setConfirmation(null),
        onError: () => {
          setConfirmation(null);
          setReviewAgain(true);
        },
      },
    );
  };

  const cancelNow = () => {
    cancel.mutate(
      { expected_version: review.version, reason_code: reason },
      { onSuccess: () => setConfirmation(null) },
    );
  };

  return (
    <div className="mx-auto w-full max-w-5xl space-y-ui-5 overflow-x-hidden">
      <Link
        className="inline-flex min-h-11 items-center text-sm font-semibold text-blue-400 hover:underline"
        to="/engineering"
      >
        ← Pending reviews
      </Link>

      <header>
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-ui-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-blue-400">
              Engineering Control
            </p>
            <h1 className="mt-ui-1 break-all text-2xl font-bold sm:text-3xl">
              {review.ecid}
            </h1>
            <p className="mt-ui-2 text-content-muted">
              {mobileEngineeringLabel(review.command_type)}
            </p>
          </div>
          <div className="flex flex-wrap gap-ui-2">
            <Badge>{mobileEngineeringLabel(review.approval_state)}</Badge>
            <Badge>Execution not connected</Badge>
          </div>
        </div>
      </header>

      <Alert variant="warning" title="Approval does not start work">
        Approval authorizes this command record only. No worker, commit, push,
        merge, or deployment starts here.
      </Alert>
      {reviewAgain && (
        <Alert
          variant="danger"
          announcement="assertive"
          title="Review the updated command"
        >
          The command changed or its evidence did not match. It was not
          approved. Review the refreshed evidence and explicitly approve again.
        </Alert>
      )}

      <div className="grid gap-ui-4 lg:grid-cols-2">
        <Card className="min-w-0 p-ui-4 sm:p-ui-5">
          <h2 className="text-lg font-bold">Identity</h2>
          <dl className="mt-ui-4 grid min-w-0 gap-ui-3 text-sm">
            <div>
              <dt className="text-content-muted">Command ID</dt>
              <dd className="break-all">{review.id}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Repository</dt>
              <dd className="break-all">{review.repository_key}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Branch</dt>
              <dd className="break-all">{review.expected_branch}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Expected HEAD</dt>
              <dd className="break-all font-mono">{review.expected_head}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Change level</dt>
              <dd>
                {review.requested_code_changes
                  ? "Uncommitted code changes"
                  : "Inspection only"}
              </dd>
            </div>
          </dl>
        </Card>

        <Card className="min-w-0 p-ui-4 sm:p-ui-5">
          <h2 className="text-lg font-bold">Status</h2>
          <dl className="mt-ui-4 grid gap-ui-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-content-muted">Approval</dt>
              <dd>{mobileEngineeringLabel(review.approval_state)}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Execution</dt>
              <dd>
                {status.data?.execution_connected === false
                  ? "Execution not connected"
                  : mobileEngineeringLabel(review.execution_state)}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Created</dt>
              <dd>{mobileEngineeringTimestamp(review.created_at)}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Updated</dt>
              <dd>{mobileEngineeringTimestamp(review.updated_at)}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Expires</dt>
              <dd>{mobileEngineeringTimestamp(review.expires_at)}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Version</dt>
              <dd>{review.version}</dd>
            </div>
            {review.approved_at && (
              <div>
                <dt className="text-content-muted">Approved</dt>
                <dd>{mobileEngineeringTimestamp(review.approved_at)}</dd>
              </div>
            )}
            {review.canceled_at && (
              <div>
                <dt className="text-content-muted">Canceled</dt>
                <dd>
                  {mobileEngineeringTimestamp(review.canceled_at)} ·{" "}
                  {mobileEngineeringLabel(
                    review.cancellation_reason_code ?? "",
                  )}
                </dd>
              </div>
            )}
          </dl>
        </Card>
      </div>

      <Card className="min-w-0 p-ui-4 sm:p-ui-5">
        <h2 className="text-lg font-bold">Owner instruction</h2>
        <p className="mt-ui-4 whitespace-pre-wrap break-words text-sm">
          {review.owner_instruction}
        </p>
        <dl className="mt-ui-5 grid gap-ui-4 text-sm">
          <div>
            <dt className="text-content-muted">Instruction digest</dt>
            <dd className="break-all font-mono">
              {review.instruction_digest}
            </dd>
          </div>
          <div>
            <dt className="text-content-muted">Request digest</dt>
            <dd className="break-all font-mono">{review.request_digest}</dd>
          </div>
        </dl>
      </Card>

      <ExecutionMonitoringPanel commandId={review.id} />

      <section className="space-y-ui-5 border-t border-stroke pt-ui-5">
        {canApprove && (
          <div>
            <h2 className="font-bold">Approve reviewed command</h2>
            <p className="mt-ui-1 text-sm text-content-muted">
              Check the instruction and evidence before approving.
            </p>
            <Button
              className="mt-ui-3"
              fullWidth
              size="large"
              disabled={approve.isPending || cancel.isPending}
              onClick={() => setConfirmation("approve")}
            >
              Approve command
            </Button>
          </div>
        )}
        <Alert variant="information" title="Rejection is not available yet">
          The current Engineering Control service has no safe rejection
          transition. Cancel the command or request a backend-supported
          rejection workflow.
        </Alert>
        {!terminal && review.can_cancel && (
          <div>
            <label
              htmlFor="mobile-cancel-reason"
              className="block font-bold"
            >
              Cancellation reason
            </label>
            <Select
              id="mobile-cancel-reason"
              className="mt-ui-2"
              value={reason}
              disabled={approve.isPending || cancel.isPending}
              onChange={(event) =>
                setReason(event.target.value as MobileCancellationReason)
              }
            >
              <option value="owner_requested">Owner requested</option>
              <option value="scope_changed">Scope changed</option>
              <option value="no_longer_needed">No longer needed</option>
            </Select>
            <Button
              className="mt-ui-4"
              fullWidth
              variant="destructive"
              size="large"
              disabled={approve.isPending || cancel.isPending}
              onClick={() => setConfirmation("cancel")}
            >
              Cancel command
            </Button>
          </div>
        )}
      </section>

      {confirmation === "approve" && (
        <ConfirmationDialog
          title="Approve this command?"
          confirmLabel="Approve command"
          pending={approve.isPending}
          onCancel={() => setConfirmation(null)}
          onConfirm={approveNow}
        >
          <p>
            <strong>{review.ecid}</strong>
          </p>
          <p>Repository: {review.repository_key}</p>
          <p>Branch: {review.expected_branch}</p>
          <p>
            HEAD: <code>{shortExpectedHead(review.expected_head)}</code>
          </p>
          <p>
            Change level:{" "}
            {review.requested_code_changes
              ? "Uncommitted changes"
              : "Inspection only"}
          </p>
          <p>Expires: {mobileEngineeringTimestamp(review.expires_at)}</p>
          <Alert variant="warning">Execution remains disconnected.</Alert>
        </ConfirmationDialog>
      )}
      {confirmation === "cancel" && (
        <ConfirmationDialog
          title="Cancel this command?"
          confirmLabel="Cancel command"
          destructive
          pending={cancel.isPending}
          onCancel={() => setConfirmation(null)}
          onConfirm={cancelNow}
        >
          <p>
            <strong>{review.ecid}</strong> will be canceled for{" "}
            <strong>{mobileEngineeringLabel(reason)}</strong>.
          </p>
          <p>Existing lifecycle history remains available.</p>
        </ConfirmationDialog>
      )}
    </div>
  );
}
