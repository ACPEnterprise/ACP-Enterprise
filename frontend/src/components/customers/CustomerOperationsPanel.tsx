import { Link } from "react-router";

import { useHasPermission } from "../../auth";
import { useEstimates } from "../../hooks/useEstimates";
import { useCustomerBalance, useInvoiceWorkspace } from "../../hooks/useInvoices";
import { useJobs } from "../../hooks/useJobs";
import { usePayments } from "../../hooks/usePayments";
import { useHcpCustomerSourceHistory } from "../../hooks/useHcpSourceHistory";
import { useAppointments } from "../../hooks/useScheduling";
import { humanizeCommercialState } from "../../presentation/commercialLabels";
import type { CustomerProperty } from "../../types/customers";
import type { CustomerTimelineEntry } from "../../types/customers";
import type { JobListItem } from "../../types/jobs";
import { Alert, Badge, Card, Spinner } from "../../ui";
import { CustomerHistoryWorkspace } from "./CustomerHistoryWorkspace";
import { HcpHistoryDetails } from "./HcpHistoryDetails";

function windowBoundary(days: number) {
  const value = new Date();
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString();
}

const terminalJobStates = new Set(["completed", "cancelled"]);
const evidenceLabel = { CURRENT_AUTHORITATIVE: "Current ACP evidence", HISTORICAL_SOURCE_EVIDENCE: "Historical source evidence", STALE: "Source evidence is stale", CONFLICTING: "Evidence conflicts", PARTIAL: "Evidence is partial", UNAVAILABLE: "Evidence unavailable" } as const;

function JobList({ jobs, empty, customerId }: { readonly jobs: readonly JobListItem[]; readonly empty: string; readonly customerId: string }) {
  if (jobs.length === 0) return <p className="text-sm text-content-muted">{empty}</p>;
  const returnTo = encodeURIComponent(`/customers/${customerId}`);
  return jobs.map((job) => (
    <div key={job.id} className="rounded-lg bg-surface-subtle p-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <Link to={`/jobs/${job.id}?returnTo=${returnTo}`} className="font-medium text-action-primary hover:underline">{job.job_number}</Link>
        <Badge variant="neutral">{job.status.replaceAll("_", " ")}</Badge>
      </div>
      <p className="mt-1 break-words text-content-muted">{job.service_location_label}</p>
      {!terminalJobStates.has(job.status) && <Link to={`/jobs/${job.id}?returnTo=${returnTo}`} className="mt-2 inline-block text-xs text-action-primary">Open Job{job.appointment_count === 0 ? " to schedule" : ""}</Link>}
    </div>
  ));
}

export function CustomerOperationsPanel({
  customerId,
  locations,
  timelineEntries = [],
  timelinePage = 1,
  timelineTotalCount,
  timelineTotalPages,
  timelineLoading = false,
  timelineFetching = false,
  onPreviousTimelinePage,
  onNextTimelinePage,
}: {
  customerId: string;
  locations: readonly CustomerProperty[];
  timelineEntries?: readonly CustomerTimelineEntry[];
  timelinePage?: number;
  timelineTotalCount?: number;
  timelineTotalPages?: number;
  timelineLoading?: boolean;
  timelineFetching?: boolean;
  onPreviousTimelinePage?: () => void;
  onNextTimelinePage?: () => void;
}) {
  const canManageJobs = useHasPermission("COMPANY_JOB_MANAGE");
  const canReadJobs = useHasPermission("COMPANY_JOB_READ");
  const canReadScheduling = useHasPermission("COMPANY_SCHEDULING_READ");
  const canReadEstimates = useHasPermission("COMPANY_ESTIMATE_READ");
  const canManageEstimates = useHasPermission("COMPANY_ESTIMATE_MANAGE");
  const canReadInvoices = useHasPermission("COMPANY_INVOICE_READ");
  const canReadPayments = useHasPermission("COMPANY_PAYMENT_READ");
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
  const payments = usePayments(canReadPayments, customerId);
  const sourceHistory = useHcpCustomerSourceHistory(
    customerId,
    canReadEstimates && canReadInvoices && canReadPayments,
  );
  // HCP history is optional source evidence.  It must not gate the native
  // Customer-to-cash workspace when that provider projection is unavailable.
  const queries = [currentJobs, historicalJobs, appointments, estimates, invoices, balance, payments];
  const evidence = balance.data?.evidence_classifications ?? [];
  const nativeEvidence = evidence.find((item) => item.source_system === "acp_native");
  const sourceEvidence = evidence.filter((item) => item.source_system !== "acp_native");
  const nativeAvailable = nativeEvidence && nativeEvidence.classification !== "UNAVAILABLE";
  const canonicalHistoryCount = (currentJobs.data?.items.length ?? 0)
    + (historicalJobs.data?.items.length ?? 0)
    + (appointments.data?.items.length ?? 0)
    + (estimates.data?.items.length ?? 0)
    + (invoices.data?.length ?? 0)
    + (payments.data?.length ?? 0);
  const historyNeedsReconciliation = !queries.some((query) => query.isLoading)
    && canonicalHistoryCount === 0
    && (sourceHistory.isError || (sourceHistory.data?.counts.estimates ?? 0) + (sourceHistory.data?.counts.invoices ?? 0) > 0);
  const unavailableDomains = [
    ...(!canReadJobs || currentJobs.isError || historicalJobs.isError ? ["Jobs"] : []),
    ...(!canReadScheduling || appointments.isError ? ["Appointments"] : []),
    ...(!canReadEstimates || estimates.isError ? ["Estimates"] : []),
    ...(!canReadInvoices || invoices.isError ? ["Invoices"] : []),
    ...(!canReadPayments || payments.isError ? ["Payments"] : []),
  ];

  return (
    <Card className="p-ui-4 sm:p-ui-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm text-action-primary">Customer-to-cash</p>
          <h3 className="mt-1 text-xl font-semibold">Operational workspace</h3>
          <p className="mt-2 text-sm text-content-muted">Jobs, appointments, estimates, invoices, payments, and activity are shown together from their canonical records.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canManageEstimates && <Link className="inline-flex min-h-11 items-center justify-center rounded-md border border-stroke-strong px-ui-4 text-sm font-semibold text-action-primary hover:bg-surface-subtle" to={`/estimates?customerId=${encodeURIComponent(customerId)}&returnTo=${encodeURIComponent(`/customers/${customerId}`)}`}>Create Estimate</Link>}
          {canManageJobs && <Link className="inline-flex min-h-11 items-center justify-center rounded-md bg-action-primary px-ui-4 text-sm font-semibold text-content-inverse hover:bg-action-primary-hover" to={`/jobs?create=1&customerId=${encodeURIComponent(customerId)}`}>Create Job</Link>}
        </div>
      </div>
      {queries.some((query) => query.isLoading) && <div className="mt-4"><Spinner label="Loading related work" /></div>}
      {queries.some((query) => query.isError) && <Alert className="mt-4" variant="warning" title="Related work is partial">One or more owning domains are unavailable. Customer identity remains usable, but do not treat missing sections or amounts as complete.</Alert>}
      {historyNeedsReconciliation && <Alert className="mt-4" variant="information" title="Historical activity is not ready">Historical data is still being imported/reconciled.</Alert>}
      {!queries.some((query) => query.isLoading) && <CustomerHistoryWorkspace
        customerId={customerId}
        locations={locations}
        currentJobs={currentJobs.data?.items ?? []}
        historicalJobs={historicalJobs.data?.items ?? []}
        appointments={appointments.data?.items ?? []}
        estimates={estimates.data?.items ?? []}
        invoices={invoices.data ?? []}
        payments={payments.data ?? []}
        evidence={evidence}
        sourceHistory={sourceHistory.data}
        unavailableDomains={unavailableDomains}
        timelineEntries={timelineEntries}
        timelinePage={timelinePage}
        timelineTotalCount={timelineTotalCount}
        timelineTotalPages={timelineTotalPages}
        timelineLoading={timelineLoading}
        timelineFetching={timelineFetching}
        onPreviousTimelinePage={onPreviousTimelinePage}
        onNextTimelinePage={onNextTimelinePage}
      />}
      {sourceHistory.data && <HcpHistoryDetails history={sourceHistory.data} />}
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        {canReadJobs && <section className="rounded-xl border border-stroke p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">Jobs</h4><Link to={`/jobs?customerId=${encodeURIComponent(customerId)}`} className="text-xs text-action-primary">View all related Jobs</Link></div>{currentJobs.data && historicalJobs.data && <p className="mt-1 text-xs text-content-muted">Showing {currentJobs.data.items.length + historicalJobs.data.items.length} of {currentJobs.data.total_count + historicalJobs.data.total_count} related Jobs.</p>}<div className="mt-3 space-y-2"><JobList customerId={customerId} jobs={[...(currentJobs.data?.items ?? []), ...(historicalJobs.data?.items ?? [])]} empty="No Jobs are linked to this Customer." /></div></section>}
        {canReadScheduling && <section className="rounded-xl border border-stroke p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">Appointments</h4><Link to="/scheduling" className="text-xs text-action-primary">Open Scheduling</Link></div><p className="mt-1 text-xs text-content-muted">Bounded to one year before and after today.</p><div className="mt-3 space-y-2">{(appointments.data?.items ?? []).map((item) => <Link key={item.id} to={`/appointments/${item.id}`} className="flex flex-wrap justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.appointment_number} · {item.arrival_window_start_at ? new Date(item.arrival_window_start_at).toLocaleString() : "Unscheduled"}</span><Badge variant="neutral">{item.status}</Badge></Link>)}{appointments.isSuccess && appointments.data.items.length === 0 && <p className="text-sm text-content-muted">No Appointments are linked to this Customer in the displayed window.</p>}</div></section>}
        {canReadEstimates && <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Estimates</h4><div className="mt-3 space-y-2">{(estimates.data?.items ?? []).map((item) => <Link key={item.id} to={`/estimates?id=${item.id}&returnTo=${encodeURIComponent(`/customers/${customerId}`)}`} className="flex flex-wrap justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.estimate_number} · {item.proposal_title}</span><Badge variant="neutral">{humanizeCommercialState(item.status)}</Badge></Link>)}{estimates.isSuccess && estimates.data.items.length === 0 && <p className="text-sm text-content-muted">No Estimates are linked to this Customer.</p>}</div></section>}
        {canReadInvoices && <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Invoices</h4><p className="mt-1 text-xs text-content-muted">Customer invoices as of {asOf}, including open and closed records.</p><div className="mt-3 space-y-2">{(invoices.data ?? []).map((item) => <Link key={item.id} to={`/invoices/${item.id}`} className="flex flex-wrap justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.invoice_number} · {item.currency} {Number(item.open_amount) > 0 ? `${item.open_amount} open` : `${item.total_amount} total`}</span><Badge variant="neutral">{item.status}</Badge></Link>)}{invoices.isSuccess && invoices.data.length === 0 && <p className="text-sm text-content-muted">No Invoices are linked to this Customer.</p>}</div></section>}
        {canReadPayments && <section className="rounded-xl border border-stroke p-4 lg:col-span-2"><h4 className="font-semibold">Payments</h4><p className="mt-1 text-xs text-content-muted">Customer payment receipts; showing at most 100 newest receipts.</p><div className="mt-3 grid gap-2 sm:grid-cols-2">{(payments.data ?? []).map((item) => <Link key={item.id} to={`/payments/${item.id}`} className="rounded-lg bg-surface-subtle p-3 text-sm"><div className="flex flex-wrap justify-between gap-2"><span className="font-medium">{item.currency} {item.captured_amount}</span><Badge variant="neutral">{item.status.replaceAll("_", " ")}</Badge></div><p className="mt-1 text-xs text-content-muted">Captured {new Date(item.captured_at).toLocaleDateString()} · {item.currency} {item.applied_amount} applied · {item.currency} {item.available_amount} unapplied</p></Link>)}{payments.isSuccess && payments.data.length === 0 && <p className="text-sm text-content-muted">No Payments are linked to this Customer.</p>}</div></section>}
      {canReadInvoices && <section className="rounded-xl border border-stroke p-4 lg:col-span-2"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">Accounts receivable</h4><Link to={`/invoices?customerId=${encodeURIComponent(customerId)}`} className="text-xs text-action-primary">Open Invoice / AR workspace</Link></div>{balance.data && <>{nativeAvailable ? <><div className="mt-3 flex flex-wrap gap-2"><Badge variant={nativeEvidence.classification === "CURRENT_AUTHORITATIVE" ? "success" : nativeEvidence.classification === "CONFLICTING" ? "danger" : "warning"}>{nativeEvidence.classification === "CURRENT_AUTHORITATIVE" ? "Current record" : "Review evidence"}</Badge></div><p className="mt-2 text-xs text-content-muted">Canonical invoice and receipt authority as of {balance.data.as_of}.</p><dl className="mt-3 grid grid-cols-2 gap-3 text-sm md:grid-cols-4"><div><dt className="text-content-muted">Open balance</dt><dd className="font-semibold">{balance.data.currency} {balance.data.open_balance}</dd></div><div><dt className="text-content-muted">Invoices</dt><dd className="font-semibold">{balance.data.native_invoice_count}</dd></div><div><dt className="text-content-muted">Applied payments</dt><dd>{balance.data.currency} {balance.data.applied_payment_total}</dd></div><div><dt className="text-content-muted">Unapplied receipts</dt><dd>{balance.data.currency} {balance.data.unapplied_receipt_total}</dd></div></dl><p className="mt-3 text-xs text-content-muted">Applied payments reduce specific Invoice obligations. Unapplied receipts remain separate Customer credit evidence and are not presented as Invoice payments.</p></> : <p className="mt-3 text-sm text-content-muted">No Customer balance evidence is available. No zero balance is inferred.</p>}</>}{balance.isError && <Alert className="mt-3" variant="warning" title="Balance evidence unavailable">The Customer balance could not be loaded. No zero balance is inferred.</Alert>}{balance.isSuccess && !balance.data && <p className="mt-3 text-sm text-content-muted">Balance evidence unavailable; no zero balance is inferred.</p>}</section>}
      {canReadEstimates && canReadInvoices && canReadPayments && <details className="rounded-xl border border-stroke p-4 lg:col-span-2"><summary className="cursor-pointer font-semibold">Audit &amp; evidence</summary><p className="mt-2 text-sm text-content-muted">Source provenance and reconciliation evidence are secondary details; normal customer work uses the unified records above.</p><div className="mt-4 space-y-3" aria-label="Customer financial source evidence">{sourceEvidence.length ? sourceEvidence.map((item) => <div key={`${item.source_system}:${item.source_record_identity ?? "unavailable"}`} className="rounded-lg border border-stroke p-3 text-sm"><div className="flex flex-wrap justify-between gap-2"><span className="font-medium">{item.source_system.replaceAll("_", " ").toUpperCase()}</span><Badge variant={item.classification === "HISTORICAL_SOURCE_EVIDENCE" ? "information" : item.classification === "CONFLICTING" ? "danger" : "warning"}>{evidenceLabel[item.classification]}</Badge></div><p className="mt-1 text-xs text-content-muted">{item.as_of ? `Source as of ${item.as_of}` : "Source as-of date unavailable"} · {item.acquired_at ? `acquired ${new Date(item.acquired_at).toLocaleDateString()}` : "acquisition time unavailable"} · {item.completeness}</p></div>) : <p className="text-sm text-content-muted">No classified source evidence is available.</p>}{sourceHistory.data ? <div className="rounded-lg border border-stroke p-3"><div className="flex flex-wrap items-center gap-2"><span className="font-medium">Source record counts</span><Badge variant="information">Read-only</Badge></div><dl className="mt-3 grid grid-cols-2 gap-3 text-sm md:grid-cols-4"><div><dt className="text-content-muted">Estimates</dt><dd className="font-semibold">{sourceHistory.data.counts.estimates}</dd></div><div><dt className="text-content-muted">Invoices</dt><dd className="font-semibold">{sourceHistory.data.counts.invoices}</dd></div><div><dt className="text-content-muted">Payment assertions</dt><dd className="font-semibold">{sourceHistory.data.counts.payments}</dd></div><div><dt className="text-content-muted">Refund assertions</dt><dd className="font-semibold">{sourceHistory.data.counts.refunds}</dd></div></dl></div> : null}</div></details>}
      </div>
    </Card>
  );
}
