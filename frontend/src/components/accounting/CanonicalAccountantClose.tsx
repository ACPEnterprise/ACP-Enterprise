import { useState } from "react";
import { Link } from "react-router";

import type {
  AccountingPeriod,
  ReportComparison,
  ReportFamily,
} from "../../api/accountingClose";
import {
  useAccountantReview,
  useGovernedPeriodClose,
  usePeriodCloseReadiness,
  useReportComparisons,
} from "../../hooks/useAccountingClose";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Select,
  Spinner,
} from "../../ui";

const familyLabels: Record<ReportFamily, string> = {
  trial_balance: "Trial Balance",
  profit_and_loss: "Profit & Loss",
  balance_sheet: "Balance Sheet",
  general_ledger: "General Ledger",
  ar_aging: "A/R Aging",
  ap_aging: "A/P Aging",
  cash_flow: "Cash Flow",
  job_costing: "Job Costing",
};

const words = (value: string) =>
  value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/^./, (letter) => letter.toUpperCase());

const money = (value: string | null, currency: string | null) => {
  if (value === null || currency === null) return "Unavailable";
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? new Intl.NumberFormat(undefined, { style: "currency", currency }).format(
        parsed,
      )
    : "Unavailable";
};

const stateVariant = (state: string) =>
  state === "COMPARABLE" || state === "READY"
    ? "success"
    : state === "UNAVAILABLE"
      ? "neutral"
      : "warning";

export function CanonicalAccountantClose({
  periods,
  canReconcile,
  canManagePeriods,
  canApprove,
}: {
  periods: AccountingPeriod[];
  canReconcile: boolean;
  canManagePeriods: boolean;
  canApprove: boolean;
}) {
  const [selectedId, setSelectedId] = useState(periods[0]?.id ?? "");
  const [closeReason, setCloseReason] = useState("");
  const selected =
    periods.find((period) => period.id === selectedId) ?? periods[0] ?? null;
  const comparisons = useReportComparisons(
    selected?.id ?? null,
    Boolean(selected),
  );
  const review = useAccountantReview(canReconcile);
  const readiness = usePeriodCloseReadiness(
    selected?.id ?? null,
    Boolean(selected),
  );
  const closePeriod = useGovernedPeriodClose();

  if (!selected) {
    return (
      <Alert variant="warning">
        No Accounting period is available. No report or close state was
        inferred.
      </Alert>
    );
  }

  const closeAllowed =
    readiness.data?.overall_readiness === "READY" &&
    selected.status === "closing" &&
    canManagePeriods &&
    canApprove;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Close period</CardTitle>
          <CardDescription>
            Select a period to load its current server-owned comparisons, review
            queue, and close readiness.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="block max-w-md text-sm font-medium">
            Accounting period
            <Select
              className="mt-1 w-full"
              value={selected.id}
              onChange={(event) => {
                setSelectedId(event.target.value);
                setCloseReason("");
              }}
            >
              {periods.map((period) => (
                <option key={period.id} value={period.id}>
                  {period.name} · {words(period.status)}
                </option>
              ))}
            </Select>
          </label>
          <p className="text-sm text-content-muted">
            {selected.start_date} – {selected.end_date} · lifecycle{" "}
            {words(selected.status)}
          </p>
        </CardContent>
      </Card>

      <ReportComparisonTable
        comparisons={comparisons.data ?? []}
        loading={comparisons.isLoading}
        error={comparisons.isError}
      />

      <Card>
        <CardHeader>
          <CardTitle>Accountant review</CardTitle>
          <CardDescription>
            Each item keeps the lifecycle and governed action of its owning
            domain.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!canReconcile ? (
            <Alert variant="warning">
              Accounting reconciliation permission is required to view this
              queue.
            </Alert>
          ) : review.isLoading ? (
            <Spinner label="Loading accountant review queue" />
          ) : review.isError ? (
            <Alert variant="danger">
              Accountant review evidence is unavailable. No empty queue was
              inferred.
            </Alert>
          ) : review.data?.items.length ? (
            <div className="overflow-x-auto">
              <table className="min-w-[920px] w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th>Source</th>
                    <th>Category</th>
                    <th>Record</th>
                    <th>Requirement</th>
                    <th>Source status</th>
                    <th>Evidence</th>
                    <th>Next action</th>
                  </tr>
                </thead>
                <tbody>
                  {review.data.items.map((item) => (
                    <tr
                      className="border-b border-stroke align-top"
                      key={`${item.source_domain}:${item.source_reference}:${item.category}`}
                    >
                      <td className="py-2">{words(item.source_domain)}</td>
                      <td>{words(item.category)}</td>
                      <td>{item.display_identity}</td>
                      <td>{item.review_requirement}</td>
                      <td>
                        {words(item.source_lifecycle)} · {words(item.state)}
                      </td>
                      <td>
                        {item.provenance.length
                          ? item.provenance.join(" · ")
                          : "Unavailable"}
                      </td>
                      <td>
                        {item.action_path ? (
                          <Link
                            className="font-semibold text-action-primary underline"
                            to={item.action_path}
                          >
                            Open governed workflow
                          </Link>
                        ) : (
                          "No operator action available"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>No review items were returned by the canonical server queue.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Period close readiness</CardTitle>
          <CardDescription>
            This state and its evidence digest are calculated by Accounting on
            the server.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {readiness.isLoading ? (
            <Spinner label="Refreshing period close readiness" />
          ) : readiness.isError || !readiness.data ? (
            <Alert variant="danger">
              Close readiness is unavailable. The period cannot be closed.
            </Alert>
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p>
                  {readiness.data.start_date} – {readiness.data.end_date} ·{" "}
                  {readiness.data.accounting_basis} · {readiness.data.currency}
                </p>
                <Badge variant={stateVariant(readiness.data.overall_readiness)}>
                  {words(readiness.data.overall_readiness)}
                </Badge>
              </div>
              <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                <ReadinessItem
                  label="Trial Balance"
                  value={readiness.data.trial_balance_readiness}
                />
                <ReadinessItem
                  label="Opening and equity"
                  value={readiness.data.opening_equity_readiness}
                />
                <ReadinessItem
                  label="A/R"
                  value={readiness.data.ar_readiness}
                />
                <ReadinessItem
                  label="A/P"
                  value={readiness.data.ap_readiness}
                />
                <ReadinessItem
                  label="Payroll"
                  value={readiness.data.payroll_readiness}
                />
                <ReadinessItem
                  label="Report comparisons"
                  value={readiness.data.report_comparison_readiness}
                />
                <ReadinessItem
                  label="Accountant review blockers"
                  value={String(readiness.data.accountant_review_blocker_count)}
                />
                <ReadinessItem
                  label="Lifecycle"
                  value={readiness.data.lifecycle_status}
                />
              </dl>
              <p className="text-sm">
                Required approvals:{" "}
                {readiness.data.required_approvals.length
                  ? readiness.data.required_approvals.map(words).join(", ")
                  : "None reported"}
              </p>
              {readiness.data.blockers.length ? (
                <div className="overflow-x-auto">
                  <table className="min-w-[760px] w-full text-sm">
                    <thead>
                      <tr className="text-left">
                        <th>Area</th>
                        <th>State</th>
                        <th>Blocker</th>
                        <th>Evidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {readiness.data.blockers.map((blocker) => (
                        <tr
                          className="border-b border-stroke"
                          key={`${blocker.family}:${blocker.code}`}
                        >
                          <td className="py-2">{words(blocker.family)}</td>
                          <td>{words(blocker.state)}</td>
                          <td>{blocker.explanation}</td>
                          <td>{blocker.evidence_reference ?? "Unavailable"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
              {readiness.data.overall_readiness === "BLOCKED" ? (
                <Alert variant="warning" title="Close is blocked">
                  Resolve the server-reported blockers and refresh readiness. No
                  close request can be submitted.
                </Alert>
              ) : null}
              {closeAllowed ? (
                <div className="space-y-3 rounded-lg border border-stroke p-4">
                  <label className="block text-sm font-medium">
                    Close reason
                    <Input
                      className="mt-1"
                      value={closeReason}
                      onChange={(event) => setCloseReason(event.target.value)}
                    />
                  </label>
                  <Button
                    disabled={!closeReason.trim() || closePeriod.isPending}
                    onClick={() =>
                      void closePeriod
                        .mutateAsync({
                          periodId: selected.id,
                          expectedVersion: selected.version,
                          reason: closeReason.trim(),
                        })
                        .catch(() => undefined)
                    }
                  >
                    Close period
                  </Button>
                  <p className="text-xs text-content-muted">
                    Readiness is fetched again immediately before submission.
                    The browser sends only the current server-issued digest.
                  </p>
                </div>
              ) : readiness.data.overall_readiness === "READY" ? (
                <Alert variant="warning">
                  Close requires a closing period plus Period Management and
                  Finance Approval permissions.
                </Alert>
              ) : null}
              {closePeriod.isError ? (
                <Alert variant="danger">
                  This reconciliation changed or is no longer ready. Review the
                  refreshed evidence before trying again. The close was not
                  retried.
                </Alert>
              ) : null}
              {closePeriod.isSuccess ? (
                <Alert variant="success">
                  The server closed the period. Period and readiness evidence
                  were refreshed.
                </Alert>
              ) : null}
              <p className="break-all text-xs text-content-muted">
                Readiness generated{" "}
                {new Date(readiness.data.generated_at).toLocaleString()} ·
                evidence {readiness.data.evidence_digest}
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ReadinessItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-content-muted">{label}</dt>
      <dd>{words(value)}</dd>
    </div>
  );
}

function ReportComparisonTable({
  comparisons,
  loading,
  error,
}: {
  comparisons: ReportComparison[];
  loading: boolean;
  error: boolean;
}) {
  if (loading) return <Spinner label="Loading canonical report comparisons" />;
  if (error)
    return (
      <Alert variant="danger">
        Canonical report comparisons are unavailable. No differences were
        inferred.
      </Alert>
    );
  return (
    <Card>
      <CardHeader>
        <CardTitle>Financial-report parity</CardTitle>
        <CardDescription>
          All values and differences below come from the canonical server
          comparison.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="overflow-x-auto">
          <table className="min-w-[1240px] w-full text-sm">
            <thead>
              <tr className="text-left">
                <th>Report</th>
                <th>ACP</th>
                <th>QuickBooks</th>
                <th>Comparison</th>
                <th>ACP total</th>
                <th>QBO total</th>
                <th>Difference</th>
                <th>Period / cutoff</th>
                <th>Basis / currency</th>
                <th>Provenance</th>
                <th>Comparison evidence</th>
              </tr>
            </thead>
            <tbody>
              {comparisons.map((item) => (
                <tr
                  className="border-b border-stroke align-top"
                  key={item.family}
                >
                  <td className="py-3 font-medium">
                    {familyLabels[item.family]}
                  </td>
                  <td>{item.acp_available ? "Available" : "Unavailable"}</td>
                  <td>{item.qbo_available ? "Available" : "Unavailable"}</td>
                  <td>
                    <Badge variant={stateVariant(item.state)}>
                      {words(item.state)}
                    </Badge>
                    {item.non_comparable_reasons.length ? (
                      <ul className="mt-1 list-disc pl-4 text-xs text-content-muted">
                        {item.non_comparable_reasons.map((reason) => (
                          <li key={reason}>{words(reason)}</li>
                        ))}
                      </ul>
                    ) : null}
                  </td>
                  <td>{money(item.acp_total, item.currency)}</td>
                  <td>{money(item.qbo_total, item.currency)}</td>
                  <td>
                    {item.state === "COMPARABLE"
                      ? money(item.difference, item.currency)
                      : "Unavailable"}
                  </td>
                  <td>
                    {item.start_date ? `${item.start_date} – ` : ""}
                    {item.end_date ?? "Unavailable"}
                    <br />
                    {item.cutoff
                      ? `Cutoff ${new Date(item.cutoff).toLocaleString()}`
                      : "Cutoff unavailable"}
                  </td>
                  <td>
                    {item.basis ?? "Unavailable"} ·{" "}
                    {item.currency ?? "Unavailable"}
                    <br />
                    Scope validated by server
                  </td>
                  <td>
                    ACP:{" "}
                    {item.acp_provenance.length
                      ? item.acp_provenance.join(" · ")
                      : "Unavailable"}
                    <br />
                    QBO:{" "}
                    {item.qbo_provenance.length
                      ? item.qbo_provenance.join(" · ")
                      : "Unavailable"}
                  </td>
                  <td className="break-all">{item.evidence_digest}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {comparisons
          .filter(
            (item) => item.lines.length || item.family === "trial_balance",
          )
          .map((item) => (
            <ReportDetail key={item.family} comparison={item} />
          ))}
        <Alert variant="information">
          Cash Flow comparison is report parity only. It does not prove that
          Banking reconciliation is complete.
        </Alert>
      </CardContent>
    </Card>
  );
}

function ReportDetail({ comparison }: { comparison: ReportComparison }) {
  return (
    <details className="rounded-lg border border-stroke p-3">
      <summary className="cursor-pointer font-semibold">
        {familyLabels[comparison.family]} supporting lines
      </summary>
      {comparison.family === "trial_balance" ? (
        <div className="mt-3 space-y-3">
          <dl className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <ReadinessItem
              label="ACP debits"
              value={money(comparison.acp_total_debits, comparison.currency)}
            />
            <ReadinessItem
              label="ACP credits"
              value={money(comparison.acp_total_credits, comparison.currency)}
            />
            <ReadinessItem
              label="QBO debits"
              value={money(comparison.qbo_total_debits, comparison.currency)}
            />
            <ReadinessItem
              label="QBO credits"
              value={money(comparison.qbo_total_credits, comparison.currency)}
            />
            <ReadinessItem
              label="ACP balance"
              value={
                comparison.acp_balanced === null
                  ? "Unavailable"
                  : comparison.acp_balanced
                    ? "Balanced"
                    : "Unbalanced"
              }
            />
            <ReadinessItem
              label="QBO balance"
              value={
                comparison.qbo_balanced === null
                  ? "Unavailable"
                  : comparison.qbo_balanced
                    ? "Balanced"
                    : "Unbalanced"
              }
            />
          </dl>
          <p className="text-sm text-content-muted">
            Retained earnings, owner equity, opening equity, and unexplained
            differences remain separate server-returned classifications below. A
            missing classification remains unavailable.
          </p>
        </div>
      ) : null}
      {comparison.family === "ar_aging" || comparison.family === "ap_aging" ? (
        <p className="mt-3 text-sm text-content-muted">
          This aging comparison is separate from the opening control and
          subledger reconciliation shown in QuickBooks Cutover.
        </p>
      ) : null}
      {comparison.lines.length ? (
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-[980px] w-full text-sm">
            <thead>
              <tr className="text-left">
                <th>Line</th>
                <th>ACP classification</th>
                <th>QBO classification</th>
                <th>ACP amount</th>
                <th>QBO amount</th>
                <th>Difference</th>
                <th>ACP debit / credit</th>
                <th>QBO debit / credit</th>
                <th>State</th>
              </tr>
            </thead>
            <tbody>
              {comparison.lines.map((line) => (
                <tr className="border-b border-stroke" key={line.identity}>
                  <td className="py-2">{line.label}</td>
                  <td>
                    {line.acp_classification
                      ? words(line.acp_classification)
                      : "Unavailable"}
                  </td>
                  <td>
                    {line.qbo_classification
                      ? words(line.qbo_classification)
                      : "Unavailable"}
                  </td>
                  <td>{money(line.acp_amount, comparison.currency)}</td>
                  <td>{money(line.qbo_amount, comparison.currency)}</td>
                  <td>
                    {comparison.state === "COMPARABLE"
                      ? money(line.difference, comparison.currency)
                      : "Unavailable"}
                  </td>
                  <td>
                    {money(line.acp_debit, comparison.currency)} /{" "}
                    {money(line.acp_credit, comparison.currency)}
                  </td>
                  <td>
                    {money(line.qbo_debit, comparison.currency)} /{" "}
                    {money(line.qbo_credit, comparison.currency)}
                  </td>
                  <td>{words(line.disposition)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-3 text-sm text-content-muted">
          No line-level comparison was returned.
        </p>
      )}
    </details>
  );
}
