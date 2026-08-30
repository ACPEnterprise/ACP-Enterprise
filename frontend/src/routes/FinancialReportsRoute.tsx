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
import { useHasPermission } from "../auth";
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

function StatementSection({ title, rows }: { title: string; rows: StatementRow[] }) {
  return (
    <section>
      <h3 className="mb-2 font-semibold">{title}</h3>
      <table className="w-full text-sm">
        <tbody>
          {rows.map((row) => (
            <tr className="border-b border-stroke" key={row.account_id}>
              <td className="py-2">{row.code} · {row.name}</td>
              <td className="py-2 text-right tabular-nums">{row.amount}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function ReportBody({ report }: { report: FinancialReport }) {
  if (isTrialBalance(report)) {
    return <table className="w-full text-sm"><thead><tr className="text-left"><th>Account</th><th>Beginning</th><th>Debits</th><th>Credits</th><th>Ending</th></tr></thead><tbody>{report.rows.map((row) => <tr className="border-b border-stroke" key={row.account_id}><td className="py-2">{row.code} · {row.name}</td><td>{row.beginning_balance}</td><td>{row.debits}</td><td>{row.credits}</td><td>{row.ending_balance}</td></tr>)}</tbody></table>;
  }
  if (isBalanceSheet(report)) {
    return <div className="grid gap-6 md:grid-cols-2"><StatementSection title="Assets" rows={report.assets}/><div className="space-y-6"><StatementSection title="Liabilities" rows={report.liabilities}/><StatementSection title="Equity" rows={report.equity}/><p className="font-semibold">Current earnings <span className="float-right tabular-nums">{report.current_earnings}</span></p></div><p className="font-bold">Total assets <span className="float-right tabular-nums">{report.total_assets}</span></p><p className="font-bold">Liabilities, equity, and current earnings <span className="float-right tabular-nums">{report.liabilities_equity_and_current_earnings}</span></p></div>;
  }
  if (isIncomeStatement(report)) {
    return <div className="space-y-6"><StatementSection title="Revenue" rows={report.revenue}/><StatementSection title="Expenses" rows={report.expenses}/><p className="font-bold">Net income <span className="float-right tabular-nums">{report.net_income}</span></p></div>;
  }
  const ledger = report as GeneralLedger;
  return <table className="w-full text-sm"><thead><tr className="text-left"><th>Date</th><th>Account</th><th>Source</th><th>Debit</th><th>Credit</th><th>Running</th></tr></thead><tbody>{ledger.rows.map((row) => <tr className="border-b border-stroke" key={row.line_id}><td className="py-2">{row.effective_date}</td><td>{row.account_code} · {row.account_name}</td><td>{row.source_type} · {row.source_identity}</td><td>{row.debit}</td><td>{row.credit}</td><td>{row.running_balance}</td></tr>)}</tbody></table>;
}

export function FinancialReportsRoute() {
  const canRead = useHasPermission("COMPANY_ACCOUNTING_REPORT_READ");
  const [reportName, setReportName] = useState<ReportName>("trial-balance");
  const [startDate, setStartDate] = useState(yearStart);
  const [endDate, setEndDate] = useState(today);
  const [branchId, setBranchId] = useState("");
  const [request, setRequest] = useState({ report: reportName, startDate, endDate, branchId: "" });
  const report = useFinancialReport(request, canRead);
  if (!canRead) return <Alert variant="danger">You are not authorized to read financial statements.</Alert>;
  return <div className="mx-auto max-w-7xl space-y-6 pb-12"><header><p className="text-sm font-semibold text-action-primary">Native Accounting</p><h1 className="mt-1 text-2xl font-bold sm:text-3xl">Financial statements</h1><p className="mt-2 text-content-muted">Read-only statements derived exclusively from posted ACP General Ledger entries.</p></header><Card><CardHeader><CardTitle>Report scope</CardTitle><CardDescription>Branch reports exclude unassigned Company lines and are labeled as workpapers.</CardDescription></CardHeader><CardContent><form className="grid gap-3 md:grid-cols-5" onSubmit={(event) => { event.preventDefault(); setRequest({ report: reportName, startDate, endDate, branchId }); }}><Select aria-label="Report" value={reportName} onChange={(event) => setReportName(event.target.value as ReportName)}><option value="trial-balance">Trial Balance</option><option value="balance-sheet">Balance Sheet</option><option value="income-statement">Income Statement</option><option value="general-ledger">General Ledger</option></Select><Input aria-label="Start date" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)}/><Input aria-label="End date" type="date" required value={endDate} onChange={(event) => setEndDate(event.target.value)}/><Input aria-label="Branch ID (optional)" value={branchId} onChange={(event) => setBranchId(event.target.value)}/><Button type="submit">Generate</Button></form></CardContent></Card>{report.isPending ? <Spinner label="Generating financial report"/> : report.isError ? <Alert variant="danger">The authoritative report could not be generated. Review Accounting reconciliation evidence.</Alert> : report.data ? <Card><CardHeader><CardTitle>{report.data.manifest.report_name.replaceAll("_", " ")}</CardTitle><CardDescription>{report.data.scope.scope_label} · {report.data.manifest.currency} · {report.data.manifest.accounting_basis} · cutoff {report.data.manifest.ledger_cutoff.slice(0, 12)}</CardDescription></CardHeader><CardContent><div className="mb-5 grid gap-2 text-sm sm:grid-cols-5"><span>Integrity: {report.data.quality.integrity}</span><span>Complete: {report.data.quality.completeness}</span><span>Freshness: {report.data.quality.freshness}</span><span>Reconciliation: {report.data.quality.reconciliation}</span><span>Review: {report.data.quality.review}</span></div><div className="overflow-x-auto"><ReportBody report={report.data}/></div><p className="mt-5 break-all text-xs text-content-muted">Definition {report.data.manifest.definition_version} · checksum {report.data.manifest.checksum}</p></CardContent></Card> : null}</div>;
}
