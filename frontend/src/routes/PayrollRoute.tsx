import { useHasPermission } from "../auth";
import { useComplianceSchemas, usePayrollOperationsSummary, usePayrollReports } from "../hooks/usePayroll";
import { Alert, Card, CardContent, CardDescription, CardHeader, CardTitle, Spinner } from "../ui";

const label = (value: string) => value.replaceAll("_", " ").replaceAll(":", " · ");

function StateList({ values, empty }: { values: Record<string, number>; empty: string }) {
  const entries = Object.entries(values).sort(([left], [right]) => left.localeCompare(right));
  if (!entries.length) return <p className="text-sm text-content-muted">{empty}</p>;
  return <dl className="grid gap-2">{entries.map(([state, count]) => <div className="flex justify-between gap-4 border-b border-stroke py-2" key={state}><dt className="capitalize">{label(state)}</dt><dd className="font-semibold tabular-nums">{count}</dd></div>)}</dl>;
}

export function PayrollRoute() {
  const canReadReporting = useHasPermission("COMPANY_PAYROLL_REPORTING_READ");
  const canReadRuns = useHasPermission("COMPANY_PAYROLL_RUN_READ");
  const canRead = canReadReporting || canReadRuns;
  const operations = usePayrollOperationsSummary();
  const reports = usePayrollReports();
  const schemas = useComplianceSchemas();
  if (!canRead) return <Alert variant="danger">You are not authorized to view Payroll Administration.</Alert>;
  if (operations.isPending || reports.isPending || schemas.isPending) return <Spinner label="Loading Payroll Administration" />;
  if (operations.isError || reports.isError || schemas.isError || !operations.data) return <Alert variant="danger" title="Payroll Administration unavailable">Authoritative Payroll readiness could not be loaded. No Payroll action was taken.</Alert>;
  const value = operations.data;
  return <div className="mx-auto max-w-7xl space-y-6 pb-12">
    <header><p className="text-sm font-semibold text-action-primary">Financial Operations</p><h1 className="mt-1 text-2xl font-bold sm:text-3xl">Payroll Administration</h1><p className="mt-2 text-content-muted">Readiness, reconciliation, reporting, payment, remittance, statements, and correction evidence. Provider execution and filing remain disabled.</p></header>
    <Alert variant={value.blocker_count ? "warning" : "information"} title={value.blocker_count ? "Payroll attention required" : "Payroll evidence reconciled"}>{value.blocker_count ? `${value.blocker_count} Employee disposition blocker(s) remain explicit.` : "No unexplained Employee blocker is present in the admitted run population."} History: {value.history_ready ? "complete authority available" : "incomplete—YTD remains unavailable"}.</Alert>
    <section aria-label="Payroll readiness" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Card><CardHeader><CardTitle>Approved gross</CardTitle><CardDescription>Accepted Payroll runs only</CardDescription></CardHeader><CardContent className="text-2xl font-bold tabular-nums">{value.aggregate_approved_gross}</CardContent></Card>
      <Card><CardHeader><CardTitle>Approved net</CardTitle><CardDescription>Before payment execution</CardDescription></CardHeader><CardContent className="text-2xl font-bold tabular-nums">{value.aggregate_approved_net}</CardContent></Card>
      <Card><CardHeader><CardTitle>Reconciliation</CardTitle><CardDescription>All known dispositions</CardDescription></CardHeader><CardContent className="capitalize">{label(value.reconciliation_state)}</CardContent></Card>
      <Card><CardHeader><CardTitle>Provider boundary</CardTitle><CardDescription>No provider selected</CardDescription></CardHeader><CardContent className="text-sm capitalize">Filing · {label(value.provider_readiness.filing)}<br/>Payment · {label(value.provider_readiness.payment)}<br/>Remittance · {label(value.provider_readiness.remittance)}</CardContent></Card>
    </section>
    <section className="grid gap-4 lg:grid-cols-3">
      <Card><CardHeader><CardTitle>Payroll runs</CardTitle><CardDescription>Assembly, review, and final approval</CardDescription></CardHeader><CardContent><StateList values={value.run_counts} empty="No synthetic or operational runs."/><h3 className="mt-5 font-semibold">Employee dispositions</h3><StateList values={value.member_dispositions} empty="No run population assembled."/></CardContent></Card>
      <Card><CardHeader><CardTitle>Payments</CardTitle><CardDescription>Release and settlement evidence</CardDescription></CardHeader><CardContent><StateList values={value.payment_counts} empty="No payment authority prepared."/></CardContent></Card>
      <Card><CardHeader><CardTitle>Remittance</CardTitle><CardDescription>Tax, deduction, and benefit obligations</CardDescription></CardHeader><CardContent><StateList values={value.remittance_counts} empty="No remittance obligations identified."/></CardContent></Card>
      <Card><CardHeader><CardTitle>Reporting & compliance</CardTitle><CardDescription>Period, quarter, annual, and prepared packages</CardDescription></CardHeader><CardContent><StateList values={value.reporting_counts} empty="No reporting snapshot prepared."/><p className="mt-4 text-sm">Configured schemas: <strong>{schemas.data?.length ?? 0}</strong></p></CardContent></Card>
      <Card><CardHeader><CardTitle>Pay statements</CardTitle><CardDescription>Issued history and protected artifacts</CardDescription></CardHeader><CardContent><StateList values={value.statement_counts} empty="No statement issued."/></CardContent></Card>
      <Card><CardHeader><CardTitle>Adjustments</CardTitle><CardDescription>Correction and off-cycle authority</CardDescription></CardHeader><CardContent><StateList values={value.adjustment_counts} empty="No open adjustment authority."/></CardContent></Card>
    </section>
    <Card><CardHeader><CardTitle>Reporting history</CardTitle><CardDescription>Authoritative totals remain permission-protected; incomplete history is never presented as YTD.</CardDescription></CardHeader><CardContent>{reports.data?.length ? <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left"><th>Period</th><th>Scope</th><th>State</th><th>Blockers</th></tr></thead><tbody>{reports.data.map((report) => <tr className="border-b border-stroke" key={report.id}><td className="py-3">{report.period_start} – {report.period_end}</td><td className="capitalize">{label(report.period_kind)}</td><td className="capitalize">{label(report.state)}</td><td>{report.blockers.length ? report.blockers.map(label).join(", ") : "None"}</td></tr>)}</tbody></table></div> : <p className="text-content-muted">No Payroll reports have been admitted.</p>}</CardContent></Card>
  </div>;
}
