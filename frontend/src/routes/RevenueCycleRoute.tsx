import { Link } from "react-router";

import { useHasPermission } from "../auth";
import { Alert, Badge, Card, CardContent, CardHeader, CardTitle, Spinner } from "../ui";
import { useEstimates } from "../hooks/useEstimates";
import { useInvoices } from "../hooks/useInvoices";
import { useJobs } from "../hooks/useJobs";
import { usePayments } from "../hooks/usePayments";

const openInvoiceStates = new Set(["draft", "issued", "partially_paid", "adjusted"]);

function Queue({ title, count, detail, href }: { readonly title: string; readonly count: number; readonly detail: string; readonly href: string }) {
  return <Link to={href} className="rounded-xl border border-stroke bg-surface p-4 transition hover:border-action-primary"><p className="text-sm text-content-muted">{title}</p><p className="mt-1 text-3xl font-bold">{count}</p><p className="mt-2 text-xs text-content-muted">{detail}</p></Link>;
}

export function RevenueCycleRoute() {
  const canReadJobs = useHasPermission("COMPANY_JOB_READ");
  const canReadEstimates = useHasPermission("COMPANY_ESTIMATE_READ");
  const canReadInvoices = useHasPermission("COMPANY_INVOICE_READ");
  const canReadPayments = useHasPermission("COMPANY_PAYMENT_READ");
  const jobs = useJobs({ page: 1, pageSize: 200 }, canReadJobs);
  const estimates = useEstimates(undefined, undefined, canReadEstimates);
  const invoices = useInvoices(canReadInvoices);
  const payments = usePayments(canReadPayments);

  if (!canReadJobs) return <Alert variant="danger">You are not authorized to view the operational revenue cycle.</Alert>;
  const loading = jobs.isPending || (canReadEstimates && estimates.isPending) || (canReadInvoices && invoices.isPending) || (canReadPayments && payments.isPending);
  if (loading) return <Spinner label="Loading revenue cycle" />;
  if (jobs.isError) return <Alert variant="danger">The Job pipeline could not be loaded.</Alert>;
  const partialFailure = estimates.isError || invoices.isError || payments.isError;

  const jobItems = jobs.data?.items ?? [];
  const invoiceItems = invoices.data ?? [];
  const invoicedJobs = new Set(invoiceItems.map((invoice) => invoice.job_id));
  const completedNotInvoiced = jobItems.filter((job) => job.status === "completed" && !invoicedJobs.has(job.id));
  const paymentItems = payments.data ?? [];

  return <div className="space-y-6">
    <header><p className="text-sm font-semibold text-action-primary">Field Operations / Customer to Cash</p><h1 className="mt-1 text-2xl font-bold sm:text-3xl">Revenue cycle</h1><p className="mt-2 max-w-3xl text-content-muted">Operational visibility from commercial decision through Job completion, Invoice handoff, and native Payment evidence. Amounts never influence queue priority.</p></header>
    {partialFailure && <Alert variant="warning">Revenue Cycle evidence is incomplete. Unavailable queues are not zero; refresh before operational decisions.</Alert>}
    <section aria-label="Operational revenue queues" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {canReadEstimates && <Queue title="Estimates awaiting decision" count={(estimates.data?.items ?? []).filter((item) => ["sent", "viewed"].includes(item.status)).length} detail="Presented proposals with no accepted or rejected state." href="/estimates" />}
      <Queue title="Jobs needing scheduling" count={jobItems.filter((job) => job.status === "ready" && job.appointment_count === 0).length} detail="Ready Jobs without an authoritative Appointment." href="/jobs?status=ready" />
      <Queue title="Work in progress" count={jobItems.filter((job) => ["in_progress", "paused"].includes(job.status)).length} detail="Active or paused native Job lifecycle state." href="/jobs?status=in_progress" />
      {canReadInvoices && <Queue title="Completed not invoiced" count={completedNotInvoiced.length} detail="Completed Jobs with no Invoice linked by authoritative Job identity." href="/jobs?status=completed" />}
      {canReadInvoices && <Queue title="Open Invoices" count={invoiceItems.filter((invoice) => openInvoiceStates.has(invoice.status) && Number(invoice.open_amount) > 0).length} detail="Native Invoice state with an open balance; no collection policy implied." href="/invoices" />}
      {canReadInvoices && <Queue title="Reconciliation required" count={invoiceItems.filter((invoice) => invoice.accounting_status === "reconciliation_required").length} detail="Explicit native Invoice accounting-control state." href="/invoices" />}
      {canReadPayments && <Queue title="Payment receipts" count={paymentItems.length} detail="Native provider-neutral receipt evidence; settlement is not inferred." href="/payments" />}
    </section>
    <Card><CardHeader><CardTitle>Recently completed work awaiting handoff</CardTitle></CardHeader><CardContent>{canReadInvoices ? completedNotInvoiced.length ? <div className="space-y-2">{completedNotInvoiced.slice(0, 10).map((job) => <Link key={job.id} to={`/jobs/${job.id}`} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-stroke p-3"><span><strong>{job.job_number}</strong> · {job.customer_display_name}</span><Badge variant="neutral">Invoice handoff pending</Badge></Link>)}</div> : <p className="text-sm text-content-muted">No completed Jobs are waiting for Invoice handoff.</p> : <p className="text-sm text-content-muted">Invoice authority is required to evaluate this queue.</p>}</CardContent></Card>
  </div>;
}
