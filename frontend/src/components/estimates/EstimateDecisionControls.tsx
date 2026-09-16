import { useState, type FormEvent } from "react";
import axios from "axios";
import { Link } from "react-router";

import type { Estimate } from "../../types/estimates";
import { Alert, Button, Field, Input, Textarea } from "../../ui";

type Mutations = ReturnType<
  typeof import("../../hooks/useEstimates").useEstimateMutations
>;

function decisionRecoveryMessage(error: unknown) {
  if (axios.isAxiosError(error)) {
    const recovery = (
      error.response?.data as { detail?: { recovery?: string } }
    )?.detail?.recovery;
    if (recovery === "RETRY_AFTER_REFRESH")
      return "Estimate authority changed. Refresh before recording this Customer decision.";
    if (recovery === "USER_CORRECTION_REQUIRED")
      return "Customer decision evidence requires correction. The entered evidence was retained.";
    if (recovery === "OWNER_ADMIN_ACTION_REQUIRED")
      return "This Estimate requires owner or administrator action before continuing.";
  }
  return "The Estimate action was not recorded. Refresh authoritative state before retrying.";
}

export function EstimateDecisionControls({
  estimate,
  mutations,
}: {
  readonly estimate: Estimate;
  readonly mutations: Mutations;
}) {
  const [customerName, setCustomerName] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [customerComment, setCustomerComment] = useState("");
  const [evidenceReference, setEvidenceReference] = useState("");
  const [rejectionReason, setRejectionReason] = useState("");
  const [jobTypeCode, setJobTypeCode] = useState("");
  const [reportedProblem, setReportedProblem] = useState("");
  const [mode, setMode] = useState<"approve" | "reject" | null>(null);
  const [revising, setRevising] = useState(false);
  const [revisionTitle, setRevisionTitle] = useState(
    estimate.current_revision.proposal_title,
  );
  const [revisionMessage, setRevisionMessage] = useState(
    estimate.current_revision.customer_message ?? "",
  );
  const [revisionTerms, setRevisionTerms] = useState(
    estimate.current_revision.terms ?? "",
  );
  const [revisionExpiry, setRevisionExpiry] = useState(
    estimate.current_revision.expires_at?.slice(0, 16) ?? "",
  );
  const transition = (action: "send" | "view" | "expire") =>
    mutations.transition.mutate({
      id: estimate.id,
      action,
      input: {
        branch_id: estimate.branch_id,
        expected_version: estimate.version,
        occurred_at: new Date().toISOString(),
      },
    });
  const decide = (event: FormEvent) => {
    event.preventDefault();
    if (!mode) return;
    mutations.decide.mutate({
      id: estimate.id,
      action: mode,
      input: {
        branch_id: estimate.branch_id,
        expected_version: estimate.version,
        occurred_at: new Date().toISOString(),
        customer_name: customerName,
        customer_email: customerEmail || undefined,
        customer_comment: customerComment || undefined,
        evidence_reference: evidenceReference || undefined,
        rejection_reason: mode === "reject" ? rejectionReason : undefined,
      },
    });
  };
  const convert = () =>
    mutations.convert.mutate({
      id: estimate.id,
      input: {
        branch_id: estimate.branch_id,
        expected_version: estimate.version,
        idempotency_key: `estimate-job-${estimate.id}`,
        job_type_code: jobTypeCode || undefined,
        customer_reported_problem: reportedProblem || undefined,
      },
    });
  const revise = (event: FormEvent) => {
    event.preventDefault();
    mutations.revise.mutate({
      id: estimate.id,
      input: {
        branch_id: estimate.branch_id,
        customer_id: estimate.customer_id,
        service_location_id: estimate.service_location_id ?? undefined,
        expected_version: estimate.version,
        proposal_title: revisionTitle,
        customer_message: revisionMessage || undefined,
        terms: revisionTerms || undefined,
        expires_at: revisionExpiry
          ? new Date(revisionExpiry).toISOString()
          : undefined,
        lines: estimate.current_revision.lines.map((line) => ({
          snapshot_id: line.snapshot_id,
          title: line.title,
          description: line.description ?? undefined,
        })),
      },
    });
  };
  const busy =
    mutations.transition.isPending ||
    mutations.decide.isPending ||
    mutations.convert.isPending ||
    mutations.revise.isPending;
  const failure = mutations.transition.isError
    ? mutations.transition.error
    : mutations.decide.isError
      ? mutations.decide.error
      : mutations.convert.isError
        ? mutations.convert.error
        : mutations.revise.isError
          ? mutations.revise.error
        : null;
  return (
    <section
      className="space-y-3 border-t border-stroke pt-4"
      aria-label="Estimate lifecycle"
    >
      <div className="flex flex-wrap gap-2">
        {!["approved", "accepted", "cancelled"].includes(estimate.status) && (
          <Button variant="outline" disabled={busy} onClick={() => setRevising(true)}>
            Revise customer presentation
          </Button>
        )}
        {estimate.status === "draft" && (
          <Button disabled={busy} onClick={() => transition("send")}>
            Record as presented
          </Button>
        )}
        {estimate.status === "sent" && (
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => transition("view")}
          >
            Record customer view
          </Button>
        )}
        {["sent", "viewed"].includes(estimate.status) && (
          <>
            <Button disabled={busy} onClick={() => setMode("approve")}>
              Record acceptance
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => setMode("reject")}
            >
              Record rejection
            </Button>
          </>
        )}
        {["draft", "sent", "viewed"].includes(estimate.status) && (
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => transition("expire")}
          >
            Record expiration
          </Button>
        )}
      </div>
      {revising && (
        <form
          className="grid gap-3 rounded-lg bg-surface-subtle p-4 sm:grid-cols-2"
          onSubmit={revise}
        >
          <Alert className="sm:col-span-2">
            This creates a new immutable revision. Existing sealed service lines and prices are retained.
          </Alert>
          <Field label="Proposal title">
            <Input value={revisionTitle} onChange={(event) => setRevisionTitle(event.target.value)} required />
          </Field>
          <Field label="Expiration (optional)">
            <Input type="datetime-local" value={revisionExpiry} onChange={(event) => setRevisionExpiry(event.target.value)} />
          </Field>
          <Field label="Customer message (optional)">
            <Textarea value={revisionMessage} onChange={(event) => setRevisionMessage(event.target.value)} />
          </Field>
          <Field label="Terms (optional)">
            <Textarea value={revisionTerms} onChange={(event) => setRevisionTerms(event.target.value)} />
          </Field>
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" loading={mutations.revise.isPending}>Create revised Draft</Button>
            <Button type="button" variant="ghost" onClick={() => setRevising(false)}>Cancel</Button>
          </div>
        </form>
      )}
      {mode && (
        <form
          className="grid gap-3 rounded-lg bg-surface-subtle p-4 sm:grid-cols-2"
          onSubmit={decide}
        >
          <Field label="Customer name">
            <Input
              value={customerName}
              onChange={(event) => setCustomerName(event.target.value)}
              required
            />
          </Field>
          <Field label="Customer email (optional)">
            <Input
              type="email"
              value={customerEmail}
              onChange={(event) => setCustomerEmail(event.target.value)}
            />
          </Field>
          <Field label="Acceptance evidence reference (optional)">
            <Input
              value={evidenceReference}
              onChange={(event) => setEvidenceReference(event.target.value)}
              placeholder="Signed document or sanctioned evidence ID"
            />
          </Field>
          <Field label="Customer comment (optional)">
            <Textarea
              value={customerComment}
              onChange={(event) => setCustomerComment(event.target.value)}
            />
          </Field>
          {mode === "reject" && (
            <Field label="Rejection reason">
              <Textarea
                value={rejectionReason}
                onChange={(event) => setRejectionReason(event.target.value)}
                required
              />
            </Field>
          )}
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" loading={mutations.decide.isPending}>
              Confirm {mode === "approve" ? "acceptance" : "rejection"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setMode(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      {estimate.conversion ? (
        <Alert variant="success">
          Converted to Job{" "}
          <Link className="font-semibold underline" to={`/jobs/${estimate.conversion.job_id}`}>
            {estimate.conversion.job_number}
          </Link>
          . The sold Estimate snapshot remains preserved.
        </Alert>
      ) : estimate.status === "approved" && (
        <div className="grid gap-3 rounded-lg border border-stroke p-4 sm:grid-cols-2">
          {!estimate.service_location_id && (
            <Alert className="sm:col-span-2" variant="warning" role="alert">
              Select a Service Location on a revised Estimate before converting it to a Job. The approved sold snapshot remains unchanged.
            </Alert>
          )}
          <Field label="Job type code (optional)">
            <Input
              value={jobTypeCode}
              onChange={(event) => setJobTypeCode(event.target.value)}
            />
          </Field>
          <Field label="Customer-reported problem (optional)">
            <Textarea
              value={reportedProblem}
              onChange={(event) => setReportedProblem(event.target.value)}
            />
          </Field>
          <div className="sm:col-span-2">
            <Button
              type="button"
              loading={mutations.convert.isPending}
              disabled={!estimate.service_location_id}
              onClick={convert}
            >
              Convert approved Estimate to Job
            </Button>
          </div>
        </div>
      )}
      {mutations.convert.data && (
        <Alert variant="success">
          Created Job {mutations.convert.data.job_number}. Sold snapshot lineage{" "}
          {mutations.convert.data.snapshot_lineage_digest.slice(0, 12)}… is
          preserved.
        </Alert>
      )}
      {failure && (
        <Alert variant="danger" role="alert" aria-live="assertive">
          {decisionRecoveryMessage(failure)}
        </Alert>
      )}
      <p className="text-xs text-content-muted">
        These controls record explicit Customer evidence. They do not send
        communications, infer a decision, or claim legal-signature validity. Use
        only evidence permitted by owner-approved policy.
      </p>
    </section>
  );
}
