import { Link } from "react-router";

import { useHasPermission } from "../../auth";
import { useEstimates } from "../../hooks/useEstimates";
import { useCustomerBalance, useInvoiceWorkspace } from "../../hooks/useInvoices";
import { useJobs } from "../../hooks/useJobs";
import { useAppointments } from "../../hooks/useScheduling";
import type { JobListItem } from "../../types/jobs";
import { Alert, Badge, Card, Spinner } from "../../ui";

function windowBoundary(days: number) {
  const value = new Date();
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString();
}

const terminalJobStates = new Set(["completed", "cancelled"]);

function JobList({ jobs, empty }: { readonly jobs: readonly JobListItem[]; readonly empty: string }) {
  if (jobs.length === 0) return <p className="text-sm text-content-muted">{empty}</p>;
  return jobs.map((job) => (
    <div key={job.id} className="rounded-lg bg-surface-subtle p-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <Link to={`/jobs/${job.id}`} className="font-medium text-action-primary hover:underline">{job.job_number}</Link>
        <Badge variant="neutral">{job.status.replaceAll("_", " ")}</Badge>
      </div>
      <p className="mt-1 break-words text-content-muted">{job.service_location_label}</p>
      {!terminalJobStates.has(job.status) && <Link to={`/jobs/${job.id}`} className="mt-2 inline-block text-xs text-action-primary">Open Job{job.appointment_count === 0 ? " to schedule" : ""}</Link>}
    </div>
  ));
}

export function CustomerOperationsPanel({ customerId }: { customerId: string }) {
  const canManageJobs = useHasPermission("COMPANY_JOB_MANAGE");
  const canReadJobs = useHasPermission("COMPANY_JOB_READ");
  const canReadScheduling = useHasPermission("COMPANY_SCHEDULING_READ");
  const canReadEstimates = useHasPermission("COMPANY_ESTIMATE_READ");
  const canReadInvoices = useHasPermission("COMPANY_INVOICE_READ");
  const asOf = new Date().toISOString().slice(0, 10);
  const currentJobs = useJobs({ customerId, status: ["draft", "ready", "in_progress", "paused"], page: 1, pageSize: 25, sortField: "updated_at", sortDirection: "desc" }, canReadJobs);
  const historicalJobs = useJobs({ customerId, status: ["completed", "cancelled"], page: 1, pageSize: 25, sortField: "updated_at", sortDirection: "desc" }, canReadJobs);
  const appointments = useAppointments(
    { startAt: windowBoundary(-365), endAt: windowBoundary(365), customerId, pageSize: 100 },
    canReadScheduling,
  );
  const estimates = useEstimates(undefined, customerId, canReadEstimates);
  const invoices = useInvoiceWorkspace({ asOf, state: "all", customerId, limit: 100, offset: 0 }, canReadInvoices);
  const balance = useCustomerBalance(customerId, asOf, canReadInvoices);
  const queries = [currentJobs, historicalJobs, appointments, estimates, invoices, balance];
  const openInvoices = (invoices.data ?? []).filter((invoice) => Number(invoice.open_amount) > 0 && !["paid", "voided"].includes(invoice.status));
  const historicalInvoices = (invoices.data ?? []).filter((invoice) => !openInvoices.includes(invoice));

  return (
    <Card className="p-ui-4 sm:p-ui-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm text-action-primary">Customer-to-cash</p>
          <h3 className="mt-1 text-xl font-semibold">Operational workspace</h3>
          <p className="mt-2 text-sm text-content-muted">Related records come from their owning domains. Missing or unavailable evidence is never treated as none or zero.</p>
        </div>
        {canManageJobs && <Link className="inline-flex min-h-11 items-center justify-center rounded-md bg-action-primary px-ui-4 text-sm font-semibold text-content-inverse hover:bg-action-primary-hover" to={`/jobs?create=1&customerId=${encodeURIComponent(customerId)}`}>Create Job</Link>}
      </div>
      {queries.some((query) => query.isLoading) && <div className="mt-4"><Spinner label="Loading related work" /></div>}
      {queries.some((query) => query.isError) && <Alert className="mt-4" variant="warning" title="Related work is partial">One or more owning domains are unavailable. Customer identity remains usable, but do not treat missing sections or amounts as complete.</Alert>}
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        {canReadJobs && <section className="rounded-xl border border-stroke p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">Current Jobs</h4><Link to={`/jobs?customerId=${encodeURIComponent(customerId)}`} className="text-xs text-action-primary">View all related Jobs</Link></div>{currentJobs.data && <p className="mt-1 text-xs text-content-muted">Showing {currentJobs.data.items.length} of {currentJobs.data.total_count} current linked Jobs.</p>}<div className="mt-3 space-y-2"><JobList jobs={currentJobs.data?.items ?? []} empty="No current Jobs are linked in native Job authority." /></div></section>}
        {canReadJobs && <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Historical Jobs</h4>{historicalJobs.data && <p className="mt-1 text-xs text-content-muted">Showing {historicalJobs.data.items.length} of {historicalJobs.data.total_count} completed or cancelled linked Jobs.</p>}<div className="mt-3 space-y-2"><JobList jobs={historicalJobs.data?.items ?? []} empty="No historical Jobs are present in native Job authority." /></div></section>}
        {canReadScheduling && <section className="rounded-xl border border-stroke p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">Appointments</h4><Link to="/scheduling" className="text-xs text-action-primary">Open Scheduling</Link></div><p className="mt-1 text-xs text-content-muted">Bounded to one year before and after today; this is not all-time history.</p><div className="mt-3 space-y-2">{(appointments.data?.items ?? []).map((item) => <Link key={item.id} to={`/appointments/${item.id}`} className="flex flex-wrap justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.appointment_number} · {item.arrival_window_start_at ? new Date(item.arrival_window_start_at).toLocaleString() : "Unscheduled"}</span><Badge variant="neutral">{item.status}</Badge></Link>)}{appointments.isSuccess && appointments.data.items.length === 0 && <p className="text-sm text-content-muted">No Appointments are present in the displayed operational window.</p>}</div></section>}
        {canReadEstimates && <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Estimates</h4><div className="mt-3 space-y-2">{(estimates.data?.items ?? []).map((item) => <Link key={item.id} to={`/estimates?id=${item.id}`} className="flex flex-wrap justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.estimate_number} · {item.proposal_title}</span><Badge variant="neutral">{item.status}</Badge></Link>)}{estimates.isSuccess && estimates.data.items.length === 0 && <p className="text-sm text-content-muted">No native Estimates are linked to this Customer.</p>}</div></section>}
        {canReadInvoices && <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Open invoices</h4><p className="mt-1 text-xs text-content-muted">CURRENT_AUTHORITATIVE · Customer-scoped Invoice evidence as of {asOf}.</p><div className="mt-3 space-y-2">{openInvoices.map((item) => <Link key={item.id} to={`/invoices/${item.id}`} className="flex flex-wrap justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.invoice_number} · {item.currency} {item.open_amount} open</span><Badge variant="neutral">{item.status}</Badge></Link>)}{invoices.isSuccess && openInvoices.length === 0 && <p className="text-sm text-content-muted">No open native Invoices are present in this bounded projection.</p>}</div></section>}
        {canReadInvoices && <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Historical invoices</h4><p className="mt-1 text-xs text-content-muted">Paid, adjusted, and voided native Invoice history; showing at most 100 total Customer invoices.</p><div className="mt-3 space-y-2">{historicalInvoices.map((item) => <Link key={item.id} to={`/invoices/${item.id}`} className="flex flex-wrap justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.invoice_number} · {item.currency} {item.open_amount} open</span><Badge variant="neutral">{item.status}</Badge></Link>)}{invoices.isSuccess && historicalInvoices.length === 0 && <p className="text-sm text-content-muted">No historical native Invoices are present in this bounded projection.</p>}</div></section>}
        {canReadInvoices && <section className="rounded-xl border border-stroke p-4 lg:col-span-2"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">Accounts receivable evidence</h4><Link to={`/invoices?customerId=${encodeURIComponent(customerId)}`} className="text-xs text-action-primary">Open Invoice / AR workspace</Link></div>{balance.data && <><div className="mt-3 flex flex-wrap gap-2"><Badge variant="success">CURRENT_AUTHORITATIVE</Badge><Badge variant={balance.data.legacy_evidence_incomplete ? "warning" : "neutral"}>{balance.data.legacy_evidence_incomplete ? "PARTIAL" : "Native history complete"}</Badge></div><p className="mt-2 text-xs text-content-muted">Native Invoice/receipt authority as of {balance.data.as_of}. Historical source evidence remains a separate read-only authority.</p><dl className="mt-3 grid grid-cols-2 gap-3 text-sm md:grid-cols-4"><div><dt className="text-content-muted">Open balance</dt><dd className="font-semibold">{balance.data.currency} {balance.data.open_balance}</dd></div><div><dt className="text-content-muted">Native invoices</dt><dd className="font-semibold">{balance.data.native_invoice_count}</dd></div><div><dt className="text-content-muted">Applied payments</dt><dd>{balance.data.currency} {balance.data.applied_payment_total}</dd></div><div><dt className="text-content-muted">Unapplied receipts</dt><dd>{balance.data.currency} {balance.data.unapplied_receipt_total}</dd></div></dl><p className="mt-3 text-xs text-content-muted">Applied payments reduce specific Invoice obligations. Unapplied receipts remain separate Customer credit evidence and are not presented as Invoice payments.</p></>}{balance.data?.legacy_evidence_incomplete && <Alert className="mt-3" variant="warning" title="PARTIAL historical evidence">Historical source evidence is incomplete. Native balance evidence must not be presented as the full source balance. STALE or CONFLICTING source state is not asserted by this Customer balance contract.</Alert>}{balance.isError && <Alert className="mt-3" variant="warning" title="UNAVAILABLE balance evidence">The authoritative Customer balance could not be loaded. No zero balance is inferred.</Alert>}{balance.isSuccess && !balance.data && <p className="mt-3 text-sm text-content-muted">UNAVAILABLE · Balance evidence is unavailable; no zero balance is inferred.</p>}</section>}
      </div>
    </Card>
  );
}
