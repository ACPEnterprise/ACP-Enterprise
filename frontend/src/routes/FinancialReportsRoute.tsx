import { useState } from "react";

import {
  type BalanceSheet,
  type FinancialReport,
  type GeneralLedger,
  type IncomeStatement,
  type ReportName,
  type StatementRow,
  type TrialBalance,
} from "../api/financialReporting";
import { useAuth, useHasPermission } from "../auth";
import { QboSourceEvidence } from "../components/accounting/QboSourceEvidence";
import { useFinancialReport } from "../hooks/useFinancialReporting";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Select,
  Spinner,
} from "../ui";

const today = new Date().toISOString().slice(0, 10);
const yearStart = `${today.slice(0, 4)}-01-01`;

const isTrialBalance = (value: FinancialReport): value is TrialBalance =>
  value.manifest.report_name === "trial_balance";
const isBalanceSheet = (value: FinancialReport): value is BalanceSheet =>
  value.manifest.report_name === "balance_sheet";
const isIncomeStatement = (value: FinancialReport): value is IncomeStatement =>
  value.manifest.report_name === "income_statement";

function formatAmount(value: string, currency: string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "Unavailable";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
  }).format(amount);
}

function StatementSection({
  title,
  rows,
  currency,
}: {
  title: string;
  rows: StatementRow[];
  currency: string;
}) {
  return (
    <section>
      <h3 className="mb-2 font-semibold">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-content-muted">
          No posted {title.toLowerCase()} accounts exist for this report scope.
        </p>
      ) : (
      <table className="w-full text-sm">
        <tbody>
          {rows.map((row) => (
            <tr className="border-b border-stroke" key={row.account_id}>
              <td className="py-2">
                {row.code} · {row.name}
              </td>
              <td className="py-2 text-right tabular-nums">{formatAmount(row.amount, currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      )}
    </section>
  );
}

function ReportBody({ report }: { report: FinancialReport }) {
  if (isTrialBalance(report)) {
    if (report.rows.length === 0) {
      return <p className="text-content-muted">No posted account balances exist for this report scope.</p>;
    }
    return (
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left">
            <th>Account</th>
            <th>Beginning</th>
            <th>Debits</th>
            <th>Credits</th>
            <th>Ending</th>
          </tr>
        </thead>
        <tbody>
          {report.rows.map((row) => (
            <tr className="border-b border-stroke" key={row.account_id}>
              <td className="py-2">
                {row.code} · {row.name}
              </td>
              <td>{formatAmount(row.beginning_balance, report.manifest.currency)}</td>
              <td>{formatAmount(row.debits, report.manifest.currency)}</td>
              <td>{formatAmount(row.credits, report.manifest.currency)}</td>
              <td>{formatAmount(row.ending_balance, report.manifest.currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  if (isBalanceSheet(report)) {
    return (
      <div className="grid gap-6 md:grid-cols-2">
        <StatementSection title="Assets" rows={report.assets} currency={report.manifest.currency} />
        <div className="space-y-6">
          <StatementSection title="Liabilities" rows={report.liabilities} currency={report.manifest.currency} />
          <StatementSection title="Equity" rows={report.equity} currency={report.manifest.currency} />
          <p className="font-semibold">
            Current earnings{" "}
            <span className="float-right tabular-nums">
              {formatAmount(report.current_earnings, report.manifest.currency)}
            </span>
          </p>
        </div>
        <p className="font-bold">
          Total assets{" "}
          <span className="float-right tabular-nums">
            {formatAmount(report.total_assets, report.manifest.currency)}
          </span>
        </p>
        <p className="font-bold">
          Liabilities, equity, and current earnings{" "}
          <span className="float-right tabular-nums">
            {formatAmount(report.liabilities_equity_and_current_earnings, report.manifest.currency)}
          </span>
        </p>
      </div>
    );
  }
  if (isIncomeStatement(report)) {
    return (
      <div className="space-y-6">
        <StatementSection title="Revenue" rows={report.revenue} currency={report.manifest.currency} />
        <StatementSection title="Expenses" rows={report.expenses} currency={report.manifest.currency} />
        <p className="font-bold">
          Net income{" "}
          <span className="float-right tabular-nums">{formatAmount(report.net_income, report.manifest.currency)}</span>
        </p>
      </div>
    );
  }
  const ledger = report as GeneralLedger;
  if (ledger.rows.length === 0) {
    return <p className="text-content-muted">No posted General Ledger lines exist for this report period and scope.</p>;
  }
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left">
          <th>Date</th>
          <th>Account</th>
          <th>Source</th>
          <th>Debit</th>
          <th>Credit</th>
          <th>Running</th>
        </tr>
      </thead>
      <tbody>
        {ledger.rows.map((row) => (
          <tr className="border-b border-stroke" key={row.line_id}>
            <td className="py-2">{row.effective_date}</td>
            <td>
              {row.account_code} · {row.account_name}
            </td>
            <td>
              {row.source_type} · {row.source_identity}
            </td>
            <td>{formatAmount(row.debit, report.manifest.currency)}</td>
            <td>{formatAmount(row.credit, report.manifest.currency)}</td>
            <td>{formatAmount(row.running_balance, report.manifest.currency)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function FinancialReportsRoute() {
  const { activeCompany } = useAuth();
  const canRead = useHasPermission("COMPANY_ACCOUNTING_REPORT_READ");
  const [reportName, setReportName] = useState<ReportName>("trial-balance");
  const [startDate, setStartDate] = useState(yearStart);
  const [endDate, setEndDate] = useState(today);
  const [branchId, setBranchId] = useState("");
  const [request, setRequest] = useState({
    report: reportName,
    startDate,
    endDate,
    branchId: "",
  });
  const invalidPeriod = !endDate || Boolean(startDate && startDate > endDate);
  const report = useFinancialReport(request, canRead);
  if (!canRead)
    return (
      <Alert variant="danger">
        You are not authorized to read financial statements.
      </Alert>
    );
  return (
    <div className="mx-auto max-w-7xl space-y-8 pb-12">
      <header>
        <p className="text-sm font-semibold text-action-primary">
          Accounting evidence
        </p>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">
          Financial reports and source evidence
        </h1>
        <p className="mt-2 text-content-muted">
          ACP-posted statements and external source-reported evidence remain
          visibly separate.
        </p>
      </header>
      <section
        aria-label="ACP native financial statements"
        className="space-y-6"
      >
        <div>
          <h2 className="text-xl font-semibold">
            ACP native financial statements
          </h2>
          <p className="text-sm text-content-muted">
            Derived exclusively from posted ACP General Ledger entries.
          </p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Report scope</CardTitle>
            <CardDescription>
              Branch reports exclude unassigned Company lines and are labeled as
              workpapers.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-3 md:grid-cols-5"
              onSubmit={(event) => {
                event.preventDefault();
                if (invalidPeriod) return;
                setRequest({
                  report: reportName,
                  startDate,
                  endDate,
                  branchId,
                });
              }}
            >
              <Select
                aria-label="Report"
                value={reportName}
                onChange={(event) =>
                  setReportName(event.target.value as ReportName)
                }
              >
                <option value="trial-balance">Trial Balance</option>
                <option value="balance-sheet">Balance Sheet</option>
                <option value="income-statement">Income Statement</option>
                <option value="general-ledger">General Ledger</option>
              </Select>
              <Input
                aria-label="Start date"
                type="date"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
              />
              <Input
                aria-label="End date"
                type="date"
                required
                value={endDate}
                onChange={(event) => setEndDate(event.target.value)}
              />
              <Select
                aria-label="Branch"
                value={branchId}
                onChange={(event) => setBranchId(event.target.value)}
              >
                <option value="">Company-wide</option>
                {(activeCompany?.branches ?? []).map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name}{branch.code ? ` (${branch.code})` : ""}
                  </option>
                ))}
              </Select>
              <Button type="submit">Generate</Button>
            </form>
            {invalidPeriod ? (
              <p className="mt-3 text-sm text-status-danger" role="alert">
                Choose a start date on or before the end date. No financial report was requested.
              </p>
            ) : null}
          </CardContent>
        </Card>
        {report.isPending ? (
          <Spinner label="Generating financial report" />
        ) : report.isError ? (
          <Alert variant="danger">
            The authoritative report could not be generated. Review Accounting
            reconciliation evidence.
          </Alert>
        ) : report.data ? (
          <Card>
            <CardHeader>
              <CardTitle>
                {report.data.manifest.report_name.replaceAll("_", " ")}
              </CardTitle>
              <CardDescription>
                {report.data.scope.scope_label} ·{" "}
                {report.data.manifest.currency} ·{" "}
                {report.data.manifest.accounting_basis} · cutoff{" "}
                {report.data.manifest.ledger_cutoff.slice(0, 12)}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="mb-5 grid gap-2 text-sm sm:grid-cols-5">
                <span>Integrity: {report.data.quality.integrity}</span>
                <span>Complete: {report.data.quality.completeness}</span>
                <span>Freshness: {report.data.quality.freshness}</span>
                <span>
                  Reconciliation: {report.data.quality.reconciliation}
                </span>
                <span>Review: {report.data.quality.review}</span>
              </div>
              <div className="overflow-x-auto">
                <ReportBody report={report.data} />
              </div>
              <p className="mt-5 break-all text-xs text-content-muted">
                Definition {report.data.manifest.definition_version} · checksum{" "}
                {report.data.manifest.checksum}
              </p>
            </CardContent>
          </Card>
        ) : null}
      </section>
      <QboSourceEvidence enabled={canRead} />
    </div>
  );
}
