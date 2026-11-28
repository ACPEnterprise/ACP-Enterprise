import { useState } from "react";
import type {
  QboHistoricalKind,
  QboHistoricalRecord,
  QboHistoricalReportType,
} from "../../api/qboAccountingEvidence";
import {
  useQboHistoricalCatalog,
  useQboHistoricalReport,
  useQboHistoricalRecords,
} from "../../hooks/useQboAccountingEvidence";
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
} from "../../ui";

const display = (value: unknown) =>
  value === null || value === undefined || value === "" ? "—" : String(value);

export function QboHistoricalArchive({ enabled }: { enabled: boolean }) {
  const catalog = useQboHistoricalCatalog(enabled);
  const [kind, setKind] = useState<QboHistoricalKind>("transaction");
  const [draftQuery, setDraftQuery] = useState("");
  const [query, setQuery] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [reportType, setReportType] =
    useState<QboHistoricalReportType>("profit_and_loss");
  const [reportStartDate, setReportStartDate] = useState("2026-01-01");
  const [reportEndDate, setReportEndDate] = useState("2026-11-19");
  const report = useQboHistoricalReport(
    { report: reportType, startDate: reportStartDate, endDate: reportEndDate },
    enabled && catalog.isSuccess,
  );
  const records = useQboHistoricalRecords(
    { kind, query, startDate, endDate },
    enabled && catalog.isSuccess,
  );

  if (!enabled) return null;
  if (catalog.isLoading) return <Spinner label="Verifying historical accounting custody" />;
  if (catalog.isError || !catalog.data) {
    return (
      <Alert variant="warning" title="Historical accounting evidence unavailable">
        The sealed archive could not be verified. No historical value was inferred.
      </Alert>
    );
  }

  const value = catalog.data;
  return (
    <div className="space-y-6">
      <Card className="primary-work-panel">
        <CardHeader>
          <CardTitle>Complete QuickBooks historical archive</CardTitle>
          <CardDescription>
            Read-only source evidence for {value.source_company} through {value.source_cutoff}.
            It is searchable history, not live posting authority.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div><dt className="text-content-muted">API source population</dt><dd>{value.source_record_count.toLocaleString()}</dd></div>
            <div><dt className="text-content-muted">Relationship identities</dt><dd>{value.relationship_identity_count.toLocaleString()}</dd></div>
            <div><dt className="text-content-muted">Sealed datasets</dt><dd>{value.datasets.length}</dd></div>
            <div><dt className="text-content-muted">Disclosed exceptions</dt><dd>{value.exception_count}</dd></div>
          </dl>
          <dl className="grid gap-3 rounded-lg border border-stroke p-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div><dt className="text-content-muted">Trial Balance</dt><dd>${value.reconciliation_controls.trial_balance.manual_debits} debits / ${value.reconciliation_controls.trial_balance.manual_credits} credits</dd><dd className="text-xs text-content-muted">Difference ${value.reconciliation_controls.trial_balance.difference}</dd></div>
            <div><dt className="text-content-muted">Balance Sheet</dt><dd>${value.reconciliation_controls.balance_sheet.assets} assets / ${value.reconciliation_controls.balance_sheet.liabilities_plus_equity} liabilities + equity</dd><dd className="text-xs text-content-muted">Equation difference ${value.reconciliation_controls.balance_sheet.equation_difference}</dd></div>
            <div><dt className="text-content-muted">Profit and Loss</dt><dd>Net income ${value.reconciliation_controls.profit_and_loss.net_income}</dd><dd className="text-xs text-content-muted">Provider difference ${value.reconciliation_controls.profit_and_loss.provider_difference}</dd></div>
            <div><dt className="text-content-muted">General Ledger</dt><dd>{value.reconciliation_controls.general_ledger.manual_dated_rows.toLocaleString()} dated rows</dd><dd className="text-xs text-content-muted">Amount difference ${value.reconciliation_controls.general_ledger.amount_difference}</dd></div>
          </dl>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[42rem] text-sm">
              <thead><tr className="text-left"><th>Dataset</th><th>Records</th><th>Coverage</th><th>Custody digest</th></tr></thead>
              <tbody>
                {value.datasets.map((dataset) => (
                  <tr className="border-b border-stroke" key={dataset.key}>
                    <td className="py-2"><strong>{dataset.label}</strong><div className="text-xs text-content-muted">{dataset.category}</div></td>
                    <td>{dataset.record_count.toLocaleString()}</td>
                    <td>{dataset.starts_on ?? "Source report"}{dataset.ends_on ? ` – ${dataset.ends_on}` : ""}</td>
                    <td className="font-mono text-xs">{dataset.source_sha256.slice(0, 16)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card className="primary-work-panel">
        <CardHeader>
          <CardTitle>Historical financial reports</CardTitle>
          <CardDescription>
            Compare the sealed cash-basis source reports or select a period for General Ledger
            and cash activity. A fixed source report is never silently restated for another period.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-3">
            <label className="text-sm">Report<Select className="mt-1" aria-label="Historical report" value={reportType} onChange={(event) => setReportType(event.target.value as QboHistoricalReportType)}><option value="profit_and_loss">Profit and Loss</option><option value="balance_sheet">Balance Sheet</option><option value="trial_balance">Trial Balance</option><option value="general_ledger">General Ledger</option><option value="cash_activity">Cash / bank activity</option></Select></label>
            <label className="text-sm">From<Input className="mt-1" type="date" value={reportStartDate} onChange={(event) => setReportStartDate(event.target.value)} /></label>
            <label className="text-sm">Through<Input className="mt-1" type="date" value={reportEndDate} onChange={(event) => setReportEndDate(event.target.value)} /></label>
          </div>
          {report.isLoading ? <div className="mt-5"><Spinner label="Opening sealed report" /></div> : null}
          {report.isError ? <Alert className="mt-5" variant="warning" title="Historical report unavailable">The sealed source report could not be verified.</Alert> : null}
          {report.data ? (
            <div className="mt-5 space-y-3">
              {report.data.requested_period_matches_source === false ? <Alert variant="warning" title="Requested period differs from sealed source report">The displayed report retains its original {report.data.start_date ?? "opening"} through {report.data.end_date ?? "source cutoff"} period. Use General Ledger to inspect another period without fabricating a restated report.</Alert> : null}
              <p className="text-sm text-content-muted">{report.data.title} · {report.data.basis} basis · {report.data.record_count.toLocaleString()} source rows · digest <span className="font-mono">{report.data.source_sha256.slice(0, 16)}…</span></p>
              <div className="max-h-[36rem] overflow-auto">
                <table className="w-full min-w-[64rem] text-sm">
                  <tbody>
                    {report.data.rows.slice(0, 1000).map((row) => {
                      if ("cells" in row) return <tr className="border-b border-stroke" key={row.row_number}>{row.cells.map((cell, cellIndex) => <td className="px-2 py-1" key={`${row.row_number}-${cellIndex}`}>{display(cell)}</td>)}</tr>;
                      const record = row as QboHistoricalRecord;
                      return <tr className="border-b border-stroke" key={record.source_identity}><td className="py-1">{display(record.transaction_date)}</td><td>{display(record.transaction_type)}</td><td>{display(record.reference)}</td><td>{display(record.name)}</td><td>{display(record.description)}</td><td>{display(record.account)}</td><td>{display(record.amount)}</td><td>{display(record.balance)}</td></tr>;
                    })}
                  </tbody>
                </table>
              </div>
              {report.data.rows.length > 1000 ? <p className="text-sm text-content-muted">Showing the first 1,000 rows. Use Search and drill down for the full {report.data.record_count.toLocaleString()}-row population.</p> : null}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="primary-work-panel">
        <CardHeader>
          <CardTitle>Search and drill down</CardTitle>
          <CardDescription>
            Search source accounts, customers, vendors, invoices, General Ledger rows,
            bank or credit-card activity, and payroll history without changing any financial record.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-3 md:grid-cols-5"
            onSubmit={(event) => { event.preventDefault(); setQuery(draftQuery.trim()); }}
          >
            <label className="text-sm">Record type<Select className="mt-1" value={kind} onChange={(event) => setKind(event.target.value as QboHistoricalKind)}><option value="transaction">General Ledger</option><option value="bank_activity">Bank / credit card</option><option value="invoice">Invoices</option><option value="account">Accounts</option><option value="customer">Customers</option><option value="vendor">Vendors</option><option value="payroll">Historical payroll</option><option value="all">All directories and records</option></Select></label>
            <label className="text-sm md:col-span-2">Search<Input className="mt-1" aria-label="Search historical accounting" value={draftQuery} onChange={(event) => setDraftQuery(event.target.value)} placeholder="Name, number, memo, account…" /></label>
            <label className="text-sm">From<Input className="mt-1" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
            <label className="text-sm">Through<Input className="mt-1" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
            <div className="md:col-span-5"><Button type="submit">Search sealed history</Button></div>
          </form>
          {records.isLoading ? <div className="mt-5"><Spinner label="Searching historical accounting" /></div> : null}
          {records.isError ? <Alert className="mt-5" variant="warning" title="Historical search unavailable">The custody-backed query failed. No records were changed.</Alert> : null}
          {records.data ? (
            <div className="mt-5">
              <p className="mb-3 text-sm text-content-muted">Showing {records.data.records.length.toLocaleString()} of {records.data.total.toLocaleString()} matching source rows.</p>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[64rem] text-sm">
                  <thead><tr className="text-left"><th>Date</th><th>Type / number</th><th>Name</th><th>Description</th><th>Account</th><th>Amount / balance</th><th>Evidence ID</th></tr></thead>
                  <tbody>
                    {records.data.records.map((row) => (
                      <tr className="border-b border-stroke align-top" key={row.source_identity}>
                        <td className="py-2">{display(row.transaction_date)}</td>
                        <td>{display(row.transaction_type)}<div className="text-content-muted">{display(row.reference)}</div></td>
                        <td>{display(row.name)}</td>
                        <td>{display(row.description)}</td>
                        <td>{display(row.account)}<div className="text-content-muted">{display(row.account_type)}</div></td>
                        <td>{display(row.amount)}<div className="text-content-muted">{row.net_amount !== undefined ? `Net ${display(row.net_amount)}` : `Balance ${display(row.open_balance ?? row.balance)}`}</div></td>
                        <td className="font-mono text-xs" title={row.source_identity}>{row.source_identity.slice(0, 12)}…</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="primary-work-panel">
        <CardHeader><CardTitle>Unresolved financial exceptions</CardTitle><CardDescription>These source conflicts remain visible and were not resolved with invented entries or silent exclusions.</CardDescription></CardHeader>
        <CardContent><div className="space-y-3">{value.exceptions.map((exception, index) => <div className="rounded-lg border border-status-warning/40 bg-status-warning/10 p-3" key={String(exception.id ?? index)}><strong>{display(exception.id)} · {display(exception.classification)}</strong><p className="mt-1 text-sm">{display(exception.description)}</p><p className="mt-1 text-sm text-content-muted">Impact: {display(exception.dollar_difference ?? exception.total ?? exception.gross_difference ?? "non-monetary / disclosed in source register")}</p></div>)}</div></CardContent>
      </Card>
    </div>
  );
}
