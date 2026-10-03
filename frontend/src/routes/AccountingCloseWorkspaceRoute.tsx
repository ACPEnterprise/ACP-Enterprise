import { useState } from "react";
import { Link } from "react-router";

import { useHasPermission } from "../auth";
import { useAccountingPeriods } from "../hooks/useAccountingClose";
import { useOpeningControlDetail, usePayrollAccountingControl } from "../hooks/useAccountingClose";
import { usePayrollOperatingRegisters } from "../hooks/usePayroll";
import { previewSealedOpening, sealOpening } from "../api/accountingClose";
import { OpeningControlProjectionReview } from "../components/accounting/OpeningControlProjectionReview";
import { useQboApplicationLedger } from "../hooks/useQboNativeApplication";
import { useQboAccountingEvidence } from "../hooks/useQboAccountingEvidence";
import { useQboReviewQueue } from "../hooks/useQboNativeApplication";
import {
  Alert,
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Button,
  Spinner,
} from "../ui";

type Availability = "AVAILABLE" | "PARTIAL" | "UNAVAILABLE" | "REVIEW_REQUIRED";

const reportRows: Array<{
  name: string;
  acp: Availability;
  qboLabels: string[];
  note: string;
}> = [
  {
    name: "Trial Balance",
    acp: "AVAILABLE",
    qboLabels: ["trial balance"],
    note: "ACP is derived from posted ledger entries. A server comparison is required before a difference can be shown.",
  },
  {
    name: "Income Statement / P&L",
    acp: "AVAILABLE",
    qboLabels: ["profit and loss", "income statement"],
    note: "Both reports may be reviewed independently; no browser-calculated parity is asserted.",
  },
  {
    name: "Balance Sheet",
    acp: "AVAILABLE",
    qboLabels: ["balance sheet"],
    note: "Source and ACP balances require an identical cutoff and basis before comparison.",
  },
  {
    name: "General Ledger",
    acp: "AVAILABLE",
    qboLabels: ["general ledger"],
    note: "Posted ACP lines are available. Source line-level parity is not yet projected.",
  },
  {
    name: "A/R Aging",
    acp: "PARTIAL",
    qboLabels: ["aged receivables", "a/r aging", "ar aging"],
    note: "Source-backed net A/R exists; the cutoff-matched ACP control tie is pending.",
  },
  {
    name: "A/P Aging",
    acp: "AVAILABLE",
    qboLabels: ["aged payables", "a/p aging", "ap aging"],
    note: "ACP aging is available; a cutoff-matched QBO control comparison is pending.",
  },
  {
    name: "Cash Flow",
    acp: "UNAVAILABLE",
    qboLabels: ["cash flow"],
    note: "Formal Cash Flow parity requires the Banking authority candidate to be integrated.",
  },
  {
    name: "Job Costing",
    acp: "PARTIAL",
    qboLabels: ["job costing", "job profitability"],
    note: "Operational cost evidence exists, but Accounting report parity is not yet canonical.",
  },
];

const statusVariant = (value: Availability) =>
  value === "AVAILABLE"
    ? "success"
    : value === "UNAVAILABLE"
      ? "neutral"
      : "warning";
const label = (value: string) =>
  value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/^./, (letter) => letter.toUpperCase());

export function AccountingCloseWorkspaceRoute() {
  const canRead = useHasPermission("COMPANY_ACCOUNTING_REPORT_READ");
  const canReconcile = useHasPermission("COMPANY_ACCOUNTING_RECONCILE");
  const canManagePeriods = useHasPermission("COMPANY_ACCOUNTING_PERIOD_MANAGE");
  const canApprove = useHasPermission("COMPANY_ACCOUNTING_FINANCE_APPROVE");
  const source = useQboAccountingEvidence("accrual", canRead);
  const periods = useAccountingPeriods(canRead);
  const review = useQboReviewQueue(canReconcile);
  const ledger = useQboApplicationLedger(canRead);
  const [openingPackageId, setOpeningPackageId] = useState<string | null>(null);
  const [previewState, setPreviewState] = useState<{ pending: boolean; error: boolean; ready: boolean }>({ pending: false, error: false, ready: false });
  const [sealState, setSealState] = useState<{ pending: boolean; error: boolean }>({ pending: false, error: false });
  const opening = useOpeningControlDetail(openingPackageId, canRead);
  const payrollRegisters = usePayrollOperatingRegisters(canRead);
  const selectedPayrollRun = payrollRegisters.data?.find((item) => item.lifecycle === "approved" || item.lifecycle === "closed") ?? payrollRegisters.data?.[0] ?? null;
  const payrollCutoff = selectedPayrollRun ? `${selectedPayrollRun.period_end}T23:59:59Z` : null;
  const payrollControl = usePayrollAccountingControl(selectedPayrollRun?.run_id ?? null, payrollCutoff, canRead);

  if (!canRead)
    return (
      <Alert variant="danger">
        Accounting report permission is required to review close readiness.
      </Alert>
    );
  if (source.isLoading || periods.isLoading)
    return <Spinner label="Loading accountant close workspace" />;

  const sourceReports = source.data?.reports ?? [];
  const sourceReportState = (labels: string[]): Availability => {
    const match = sourceReports.find((item) =>
      labels.some((candidate) => item.label.toLowerCase().includes(candidate)),
    );
    if (!match) return "UNAVAILABLE";
    if (match.state === "available") return "AVAILABLE";
    if (match.state === "unavailable") return "UNAVAILABLE";
    return "PARTIAL";
  };
  const openReviewItems =
    review.data?.filter(
      (item) => item.state !== "RESOLVED" && item.state !== "APPROVED",
    ) ?? [];
  const sourceRunId = ledger.data?.source_evidence.source_run_id ?? null;
  const runPreview = async () => {
    if (!sourceRunId) return;
    setPreviewState({ pending: true, error: false, ready: false });
    try {
      await previewSealedOpening(sourceRunId);
      setPreviewState({ pending: false, error: false, ready: true });
    } catch {
      setPreviewState({ pending: false, error: true, ready: false });
    }
  };
  const runSeal = async () => {
    if (!sourceRunId) return;
    setSealState({ pending: true, error: false });
    try {
      const value = await sealOpening(sourceRunId);
      const id = typeof value === "object" && value !== null && "id" in value ? String(value.id) : null;
      if (id) setOpeningPackageId(id);
      setSealState({ pending: false, error: false });
    } catch {
      setSealState({ pending: false, error: true });
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-8 pb-12">
      <header>
        <p className="text-sm font-semibold text-action-primary">Accounting</p>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">
          Accountant close workspace
        </h1>
        <p className="mt-2 text-content-muted">
          Review report coverage, source differences, period status, and
          handoffs without changing financial authority.
        </p>
      </header>

      {source.isError ? (
        <Alert variant="warning" title="QuickBooks evidence unavailable">
          Source comparison remains unavailable. ACP values are not treated as
          matching QuickBooks.
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Opening package controls</CardTitle>
          <CardDescription>Package identity is supplied by the governed QBO custody ledger. Preview and persistence are server-owned; this workspace submits no accounting values.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm">Canonical sealed package: <code>{sourceRunId ?? "Unavailable"}</code></p>
          {previewState.error && <Alert variant="warning">The sealed opening preview is unavailable. No client-derived opening authority was used.</Alert>}
          {previewState.ready && <Alert variant="information">Server preview returned. Review it before choosing to persist the exact governed snapshot.</Alert>}
          {sealState.error && <Alert variant="warning">The governed opening snapshot could not be persisted.</Alert>}
          <div className="flex flex-wrap gap-2">
            <Button disabled={!sourceRunId || previewState.pending} onClick={() => void runPreview()}>Preview sealed package</Button>
            <Button variant="secondary" disabled={!sourceRunId || sealState.pending} onClick={() => void runSeal()}>Persist governed snapshot</Button>
          </div>
          {opening.isError && <Alert variant="warning">Persisted opening-control detail is unavailable.</Alert>}
          {opening.data && <OpeningControlProjectionReview value={opening.data} />}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Financial-report parity</CardTitle>
          <CardDescription>
            Availability is shown separately for ACP and QuickBooks. Difference
            remains unavailable until the server compares the same cutoff and
            basis.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="min-w-[880px] w-full text-sm">
              <thead>
                <tr className="text-left">
                  <th>Report</th>
                  <th>ACP</th>
                  <th>QuickBooks source</th>
                  <th>Difference</th>
                  <th>Cutoff / basis</th>
                  <th>Reconciliation</th>
                </tr>
              </thead>
              <tbody>
                {reportRows.map((row) => {
                  const qbo = sourceReportState(row.qboLabels);
                  return (
                    <tr
                      className="border-b border-stroke align-top"
                      key={row.name}
                    >
                      <td className="py-3 font-medium">
                        {row.name}
                        <p className="mt-1 max-w-md text-xs font-normal text-content-muted">
                          {row.note}
                        </p>
                      </td>
                      <td>
                        <Badge variant={statusVariant(row.acp)}>
                          {label(row.acp)}
                        </Badge>
                      </td>
                      <td>
                        <Badge variant={statusVariant(qbo)}>{label(qbo)}</Badge>
                      </td>
                      <td>Unavailable</td>
                      <td>
                        {source.data?.as_of
                          ? `${source.data.as_of.slice(0, 10)} · ${source.data.accounting_basis}`
                          : "Unavailable"}
                      </td>
                      <td>
                        {row.acp === "AVAILABLE" && qbo === "AVAILABLE"
                          ? "Ready for server comparison"
                          : "Incomplete"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link
              className="font-semibold text-action-primary underline"
              to="/financial-reports"
            >
              Open ACP financial reports
            </Link>
            <Link
              className="font-semibold text-action-primary underline"
              to="/accounting/quickbooks-cutover"
            >
              Open QuickBooks cutover
            </Link>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Accountant review queue</CardTitle>
          <CardDescription>
            Only governed QuickBooks review items are unified here today. Other
            close areas remain linked to their authoritative workspace.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!canReconcile ? (
            <Alert variant="warning">
              Accounting reconciliation permission is required to see source
              exceptions.
            </Alert>
          ) : review.isError ? (
            <Alert variant="warning">
              The governed QuickBooks review queue is unavailable.
            </Alert>
          ) : openReviewItems.length ? (
            <div className="overflow-x-auto">
              <table className="min-w-[760px] w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th>Area</th>
                    <th>Reference</th>
                    <th>Issue</th>
                    <th>Required reviewer</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {openReviewItems.map((item) => (
                    <tr className="border-b border-stroke" key={item.id}>
                      <td className="py-2">{label(item.source_family)}</td>
                      <td>{item.reference_number ?? "Unavailable"}</td>
                      <td>{item.exact_conflict}</td>
                      <td>
                        {item.allowed_actions
                          .map((action) => label(action.required_authority))
                          .join(", ") || "Unavailable"}
                      </td>
                      <td>{label(item.state)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>No open QuickBooks application exceptions were reported.</p>
          )}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <ReviewLink
              title="Opening, A/R and A/P"
              detail="Opening controls and control-account differences"
              to="/accounting/quickbooks-cutover"
            />
            <ReviewLink
              title="Banking"
              detail="Matches, reconciliation, and Cash Flow classification · pending integration"
            />
            <ReviewLink
              title="Payroll"
              detail="Opening/YTD, liabilities, register, and settlement"
              to="/payroll"
            />
            <ReviewLink
              title="Inventory and Job Cost"
              detail="Valuation and Job attribution evidence"
              to="/inventory"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Accounting periods</CardTitle>
          <CardDescription>
            Period status comes directly from Accounting. Close remains
            unavailable here until a canonical blocker and
            reconciliation-evidence projection exists.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {periods.isError ? (
            <Alert variant="danger">Accounting periods are unavailable.</Alert>
          ) : periods.data?.length ? (
            <div className="overflow-x-auto">
              <table className="min-w-[620px] w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th>Period</th>
                    <th>Dates</th>
                    <th>Status</th>
                    <th>Close readiness</th>
                  </tr>
                </thead>
                <tbody>
                  {periods.data.map((period) => (
                    <tr className="border-b border-stroke" key={period.id}>
                      <td className="py-2">{period.name}</td>
                      <td>
                        {period.start_date} – {period.end_date}
                      </td>
                      <td>{label(period.status)}</td>
                      <td>
                        {period.status === "closed"
                          ? "Closed"
                          : "Reconciliation evidence required"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>
              No Accounting periods are available. No period status was
              inferred.
            </p>
          )}
          <Alert variant="warning" title="Close controls required">
            The server can enforce balanced postings and distinct Finance
            approval, but it does not yet project the unresolved blockers or
            accepted reconciliation digest needed for a safe operator close. No
            close action is shown.
          </Alert>
          <p className="text-sm text-content-muted">
            Period management:{" "}
            {canManagePeriods ? "authorized" : "not authorized"} · Finance
            approval: {canApprove ? "authorized" : "not authorized"}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Payroll accounting review</CardTitle>
          <CardDescription>
            Payroll authority remains separate from Accounting posting
            authority.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {payrollControl.isError && <Alert variant="warning">Payroll-to-GL evidence is unavailable for the selected run. No difference was calculated in the browser.</Alert>}
          {payrollControl.data && <div className="space-y-3"><p className="text-sm">Run cutoff {payrollControl.data.cutoff_at} · status {payrollControl.data.status} · currency {payrollControl.data.currency}</p><div className="overflow-x-auto"><table className="min-w-[760px] w-full text-sm"><thead><tr className="text-left"><th>Category</th><th>Payroll</th><th>General Ledger</th><th>Difference</th><th>Classification</th><th>Explanation</th></tr></thead><tbody>{payrollControl.data.findings.map((finding) => <tr className="border-b border-stroke" key={finding.category}><td className="py-2">{finding.category}</td><td>{finding.payroll_amount ?? "Unavailable"}</td><td>{finding.general_ledger_amount ?? "Unavailable"}</td><td>{finding.difference ?? "Unavailable"}</td><td>{finding.disposition}</td><td>{finding.explanation}</td></tr>)}</tbody></table></div></div>}
          {!payrollControl.data && !payrollControl.isError && <p className="text-sm text-content-muted">No approved or closed Payroll run is currently available for a server-owned Payroll-to-GL projection.</p>}
          <ul className="grid gap-2 text-sm sm:grid-cols-2">
            <li>
              Payroll register and liability totals: available in Payroll when
              calculated
            </li>
            <li>
              Opening/YTD and bridge certification: available in Payroll cutover
              review
            </li>
            <li>
              Settlement and release evidence: available when admitted by
              Payroll
            </li>
            <li>Payroll-to-General-Ledger posting tie: server projection shown above when an approved/closed run is available</li>
          </ul>
          <Alert variant="warning">This is read-only review. Payroll execution and Accounting posting remain unavailable from this workspace.</Alert>
          <Link
            className="font-semibold text-action-primary underline"
            to="/payroll"
          >
            Open Payroll review
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

function ReviewLink({
  title,
  detail,
  to,
}: {
  title: string;
  detail: string;
  to?: string;
}) {
  const content = (
    <>
      <strong>{title}</strong>
      <span className="mt-1 block text-sm text-content-muted">{detail}</span>
    </>
  );
  return to ? (
    <Link
      className="rounded-lg border border-stroke p-3 hover:border-action-primary"
      to={to}
    >
      {content}
    </Link>
  ) : (
    <div className="rounded-lg border border-stroke p-3" aria-disabled="true">
      {content}
    </div>
  );
}
