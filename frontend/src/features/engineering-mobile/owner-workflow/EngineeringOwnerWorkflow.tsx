import { useMemo, useState } from "react";

import { getOperatorApiError } from "../../../api/errors";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmationDialog,
  Input,
  Spinner,
} from "../../../ui";
import type { MobileExecutionStatus } from "../execution/types";
import {
  mobileEngineeringLabel,
  mobileEngineeringTimestamp,
} from "../presentation";
import {
  useDecideEngineeringReview,
  useEngineeringOwnerReview,
  useExecuteRepositoryCommit,
  usePrepareEngineeringReview,
  useRepositoryAuthorization,
  useRepositoryOperation,
  useRequestRepositoryAuthorization,
} from "./hooks";
import type {
  EngineeringReviewDecision,
  EngineeringReviewPackage,
  RepositoryAuthorizationDetail,
} from "./types";

const AUTHORIZATION_LIFETIME_MS = 30 * 60 * 1_000;
const COMMIT_SUBJECT_MAX_LENGTH = 120;

type Confirmation =
  | "accept-review"
  | "reject-review"
  | "authorize"
  | "commit"
  | null;

function fileBoundary(review: EngineeringReviewPackage): readonly string[] | null {
  const value = review.validation_summary.file_boundary;
  if (
    !Array.isArray(value) ||
    value.length === 0 ||
    !value.every((item) => typeof item === "string" && item.length > 0)
  ) {
    return null;
  }
  return [...value].sort();
}

function summaryValue(value: unknown): string {
  if (value === null || value === undefined) return "Unavailable";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "Structured evidence available";
}

function hasControlCharacters(value: string): boolean {
  return Array.from(value).some((character) => {
    const code = character.charCodeAt(0);
    return code < 32 || code === 127;
  });
}

function SummaryList({
  title,
  values,
}: {
  title: string;
  values: Readonly<Record<string, unknown>>;
}) {
  const entries = Object.entries(values);
  return (
    <div>
      <h4 className="font-semibold">{title}</h4>
      {entries.length === 0 ? (
        <p className="mt-ui-2 text-sm text-content-muted">No data available</p>
      ) : (
        <dl className="mt-ui-2 grid gap-ui-2 text-sm">
          {entries.map(([key, value]) => (
            <div key={key} className="min-w-0">
              <dt className="text-content-muted">
                {mobileEngineeringLabel(key)}
              </dt>
              <dd className="break-words">{summaryValue(value)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function WorkflowError({
  error,
  title,
}: {
  error: unknown;
  title: string;
}) {
  const detail = getOperatorApiError(error, title);
  return (
    <Alert variant="danger" announcement="assertive" title={detail.title}>
      {detail.message}
    </Alert>
  );
}

export function EngineeringOwnerWorkflow({
  commandId,
  status,
}: {
  commandId: string;
  status: MobileExecutionStatus;
}) {
  const [confirmation, setConfirmation] = useState<Confirmation>(null);
  const [commitSubject, setCommitSubject] = useState("");
  const prepare = usePrepareEngineeringReview(commandId);
  const reviewQuery = useEngineeringOwnerReview(status.review_id ?? undefined);
  const review = reviewQuery.data;
  const decide = useDecideEngineeringReview(
    commandId,
    review?.review.id ?? status.review_id ?? "",
  );
  const requestAuthorization = useRequestRepositoryAuthorization(commandId);
  const authorizationQuery = useRepositoryAuthorization(
    status.authorization_id ?? undefined,
  );
  const authorization = authorizationQuery.data;
  const execute = useExecuteRepositoryCommit(commandId);
  const operationQuery = useRepositoryOperation(
    status.repository_operation_id ?? undefined,
  );
  const operation = operationQuery.data;
  const boundary = useMemo(() => (review ? fileBoundary(review) : null), [review]);

  const pending =
    prepare.isPending ||
    decide.isPending ||
    requestAuthorization.isPending ||
    execute.isPending;
  const commitSubjectValid =
    commitSubject.length > 0 &&
    commitSubject.length <= COMMIT_SUBJECT_MAX_LENGTH &&
    commitSubject === commitSubject.trim() &&
    !hasControlCharacters(commitSubject);

  const decideReview = (decision: EngineeringReviewDecision) => {
    if (!review) return;
    decide.mutate(
      {
        expected_version: review.review.version,
        review_digest: review.review.review_digest,
        decision,
        reason_code: decision === "reject" ? "owner_rejected" : null,
      },
      { onSuccess: () => setConfirmation(null) },
    );
  };

  const authorize = () => {
    if (!review || !review.decision || !boundary) return;
    requestAuthorization.mutate(
      {
        review_id: review.review.id,
        review_digest: review.review.review_digest,
        operation_type: "create_commit",
        file_boundary: boundary,
        expected_branch: review.expected_branch,
        expected_base_commit: review.expected_head,
        expires_at: new Date(Date.now() + AUTHORIZATION_LIFETIME_MS).toISOString(),
        idempotency_key: `mobile-authorization-${review.decision.id}`,
      },
      { onSuccess: () => setConfirmation(null) },
    );
  };

  const executeCommit = (record: RepositoryAuthorizationDetail) => {
    execute.mutate(
      {
        authorization_id: record.id,
        capability_id: record.capability_id,
        authorization_digest: record.authorization_digest,
        commit_subject: commitSubject,
        idempotency_key: `mobile-operation-${record.id}`,
      },
      { onSuccess: () => setConfirmation(null) },
    );
  };

  const resultReady =
    status.result.availability === "available" &&
    status.result.status !== null &&
    status.terminal;

  return (
    <section className="space-y-ui-4" aria-labelledby="owner-workflow-title">
      <div>
        <h2 id="owner-workflow-title" className="text-xl font-bold">
          Owner review and repository completion
        </h2>
        <p className="mt-ui-1 text-sm text-content-muted">
          Review, authorization, and commit remain separate owner-controlled
          steps.
        </p>
      </div>

      {!resultReady && !status.review_available && (
        <Alert variant="information" title="Awaiting a completed result">
          Owner review becomes available only after a provider-neutral execution
          result is durably accepted.
        </Alert>
      )}

      {resultReady && !status.review_available && (
        <Card className="min-w-0 p-ui-4">
          <h3 className="font-bold">Prepare owner review</h3>
          <p className="mt-ui-2 text-sm text-content-muted">
            Build an immutable review package from the authoritative completed
            result. This does not authorize or modify the repository.
          </p>
          <Button
            className="mt-ui-3 w-full sm:w-auto"
            disabled={pending}
            loading={prepare.isPending}
            onClick={() => prepare.mutate()}
          >
            Prepare review package
          </Button>
        </Card>
      )}

      {status.review_available && reviewQuery.isLoading && (
        <Card className="p-ui-4">
          <Spinner label="Loading owner review package" />
        </Card>
      )}
      {reviewQuery.isError && (
        <WorkflowError error={reviewQuery.error} title="Owner review" />
      )}
      {prepare.isError && (
        <WorkflowError error={prepare.error} title="Prepare owner review" />
      )}

      {review && (
        <Card className="min-w-0 p-ui-4 sm:p-ui-5">
          <div className="flex min-w-0 flex-wrap items-start justify-between gap-ui-3">
            <div>
              <h3 className="font-bold">Structured review package</h3>
              <p className="mt-ui-1 text-sm text-content-muted">
                Received {mobileEngineeringTimestamp(review.result_received_at)}
              </p>
            </div>
            <Badge>{mobileEngineeringLabel(review.review.state)}</Badge>
          </div>
          <dl className="mt-ui-4 grid gap-ui-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-content-muted">Provider</dt>
              <dd className="break-words">{review.review.provider_identifier}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Result</dt>
              <dd>{mobileEngineeringLabel(review.result_status)}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Disposition</dt>
              <dd>{mobileEngineeringLabel(review.result_disposition)}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Repository mutated</dt>
              <dd>{review.repository_mutated ? "Yes" : "No"}</dd>
            </div>
          </dl>
          <div className="mt-ui-5 grid gap-ui-5 md:grid-cols-2">
            <SummaryList title="Evidence summary" values={review.evidence_summary} />
            <SummaryList
              title="Validation summary"
              values={review.validation_summary}
            />
          </div>
          <div className="mt-ui-5">
            <h4 className="font-semibold">Reviewed file boundary</h4>
            {boundary ? (
              <ul className="mt-ui-2 space-y-ui-1 text-sm">
                {boundary.map((path) => (
                  <li key={path} className="break-all font-mono">
                    {path}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-ui-2 text-sm text-content-muted">
                No authoritative file boundary is available.
              </p>
            )}
          </div>

          {review.review.state === "pending" && (
            <div className="mt-ui-5 flex flex-col gap-ui-3 sm:flex-row">
              <Button
                disabled={pending}
                onClick={() => setConfirmation("accept-review")}
              >
                Accept result
              </Button>
              <Button
                variant="destructive"
                disabled={pending}
                onClick={() => setConfirmation("reject-review")}
              >
                Reject result
              </Button>
            </div>
          )}
        </Card>
      )}

      {decide.isError && (
        <WorkflowError error={decide.error} title="Owner decision" />
      )}

      {review?.review.state === "accepted" &&
        review.requested_code_changes &&
        !status.authorization_id && (
          <Card className="min-w-0 p-ui-4">
            <h3 className="font-bold">Repository authorization</h3>
            <p className="mt-ui-2 text-sm text-content-muted">
              Issue one expiring authorization bound to this accepted review,
              branch, base commit, and exact file boundary.
            </p>
            {!boundary && (
              <Alert variant="danger" title="Authorization unavailable">
                The accepted review has no valid file boundary.
              </Alert>
            )}
            <Button
              className="mt-ui-3 w-full sm:w-auto"
              disabled={pending || !boundary || !review.decision}
              onClick={() => setConfirmation("authorize")}
            >
              Authorize one commit
            </Button>
          </Card>
        )}

      {review?.review.state === "accepted" &&
        !review.requested_code_changes && (
          <Alert variant="information" title="No repository operation required">
            The reviewed execution did not request code changes.
          </Alert>
        )}

      {requestAuthorization.isError && (
        <WorkflowError
          error={requestAuthorization.error}
          title="Repository authorization"
        />
      )}
      {status.authorization_id && authorizationQuery.isLoading && (
        <Card className="p-ui-4">
          <Spinner label="Loading repository authorization" />
        </Card>
      )}
      {authorizationQuery.isError && (
        <WorkflowError
          error={authorizationQuery.error}
          title="Repository authorization"
        />
      )}

      {authorization && (
        <Card className="min-w-0 p-ui-4">
          <div className="flex flex-wrap items-start justify-between gap-ui-3">
            <h3 className="font-bold">Bounded commit authorization</h3>
            <Badge>{mobileEngineeringLabel(authorization.state)}</Badge>
          </div>
          <dl className="mt-ui-3 grid gap-ui-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-content-muted">Branch</dt>
              <dd className="break-all">{authorization.expected_branch}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Expires</dt>
              <dd>{mobileEngineeringTimestamp(authorization.expires_at)}</dd>
            </div>
          </dl>

          {authorization.authorization_eligible &&
            !status.repository_operation_id && (
              <div className="mt-ui-5">
                <label htmlFor="repository-commit-subject" className="font-semibold">
                  Approved commit subject
                </label>
                <Input
                  id="repository-commit-subject"
                  className="mt-ui-2"
                  value={commitSubject}
                  maxLength={COMMIT_SUBJECT_MAX_LENGTH}
                  disabled={pending}
                  onChange={(event) => setCommitSubject(event.target.value)}
                />
                <p className="mt-ui-2 text-xs text-content-muted">
                  Subject only, up to {COMMIT_SUBJECT_MAX_LENGTH} characters.
                </p>
                <Button
                  className="mt-ui-3 w-full sm:w-auto"
                  disabled={pending || !commitSubjectValid}
                  onClick={() => setConfirmation("commit")}
                >
                  Create authorized commit
                </Button>
              </div>
            )}
        </Card>
      )}

      {execute.isError && (
        <WorkflowError error={execute.error} title="Repository operation" />
      )}
      {status.repository_operation_id && operationQuery.isLoading && (
        <Card className="p-ui-4">
          <Spinner label="Loading repository operation" />
        </Card>
      )}
      {operationQuery.isError && (
        <WorkflowError error={operationQuery.error} title="Repository operation" />
      )}

      {(operation || status.repository_operation_status) && (
        <Alert
          variant={
            (operation?.state ?? status.repository_operation_status) ===
            "succeeded"
              ? "information"
              : (operation?.owner_attention_required ??
                  status.repository_operation_owner_attention_required)
                ? "danger"
                : "warning"
          }
          title={`Repository operation: ${mobileEngineeringLabel(
            operation?.state ?? status.repository_operation_status ?? "unknown",
          )}`}
        >
          {(operation?.state ?? status.repository_operation_status) ===
          "succeeded"
            ? `Commit ${operation?.resulting_commit_sha ?? status.repository_operation_resulting_commit_sha ?? "recorded"} was created and the authorization was consumed.`
            : (operation?.state ?? status.repository_operation_status) ===
                "reconciliation_required"
              ? "The commit outcome requires bounded operator reconciliation. No automatic retry will run."
              : "The repository operation state is reported from durable backend evidence."}
        </Alert>
      )}

      {confirmation === "accept-review" && review && (
        <ConfirmationDialog
          title="Accept this execution result?"
          confirmLabel="Accept result"
          pending={decide.isPending}
          onCancel={() => setConfirmation(null)}
          onConfirm={() => decideReview("accept")}
        >
          Acceptance approves this exact immutable evidence package for a
          separate repository-authorization decision. It does not create a
          commit.
        </ConfirmationDialog>
      )}
      {confirmation === "reject-review" && review && (
        <ConfirmationDialog
          title="Reject this execution result?"
          confirmLabel="Reject result"
          destructive
          pending={decide.isPending}
          onCancel={() => setConfirmation(null)}
          onConfirm={() => decideReview("reject")}
        >
          Rejection prevents this review package from authorizing a repository
          operation.
        </ConfirmationDialog>
      )}
      {confirmation === "authorize" && review && boundary && (
        <ConfirmationDialog
          title="Authorize one bounded commit?"
          confirmLabel="Authorize commit"
          pending={requestAuthorization.isPending}
          onCancel={() => setConfirmation(null)}
          onConfirm={authorize}
        >
          This expiring authorization is bound to {review.expected_branch} at{" "}
          <code className="break-all">{review.expected_head}</code> and exactly{" "}
          {boundary.length} reviewed file{boundary.length === 1 ? "" : "s"}.
        </ConfirmationDialog>
      )}
      {confirmation === "commit" && authorization && (
        <ConfirmationDialog
          title="Create the authorized commit?"
          confirmLabel="Create commit"
          pending={execute.isPending}
          onCancel={() => setConfirmation(null)}
          onConfirm={() => executeCommit(authorization)}
        >
          <p>
            Subject: <strong className="break-words">{commitSubject}</strong>
          </p>
          <p>
            Branch: <strong>{authorization.expected_branch}</strong>
          </p>
          <Alert variant="warning">
            This creates one local commit only. It does not push, merge, or
            deploy.
          </Alert>
        </ConfirmationDialog>
      )}
    </section>
  );
}
