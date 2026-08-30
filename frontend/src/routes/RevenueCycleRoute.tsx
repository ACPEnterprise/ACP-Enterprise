import { Link } from "react-router";
import { useState } from "react";

import { useHasPermission } from "../auth";
import { Alert, Badge, Card, CardContent, CardHeader, CardTitle, Input, Spinner } from "../ui";
import { useEstimates } from "../hooks/useEstimates";
import { useInvoices } from "../hooks/useInvoices";
import { useJobs } from "../hooks/useJobs";
import { usePayments } from "../hooks/usePayments";

const openInvoiceStates = new Set(["draft", "issued", "partially_paid", "adjusted"]);

function Queue({ title, count, detail, href }: { readonly title: string; readonly count: number; readonly detail: string; readonly href: string }) {
  return <Link to={href} className="rounded-xl border border-stroke bg-surface p-4 transition hover:border-action-primary"><p className="text-sm text-content-muted">{title}</p><p className="mt-1 text-3xl font-bold">{count}</p><p className="mt-2 text-xs text-content-muted">{detail}</p></Link>;
}

export function RevenueCycleRoute() {
  const [search, setSearch] = useState("");
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

  const jobItems = jobs.data?.items ?? [];
  const invoiceItems = invoices.data ?? [];
  const invoicedJobs = new Set(invoiceItems.map((invoice) => invoice.job_id));
  const completedNotInvoiced = jobItems.filter((job) => job.status === "completed" && !invoicedJobs.has(job.id));
  const paymentItems = payments.data ?? [];
  const needle = search.trim().toLowerCase();
  const results = needle ? [
    ...(estimates.data?.items ?? []).filter((item) => `${item.estimate_number} ${item.proposal_title}`.toLowerCase().includes(needle)).map((item) => ({ id: `estimate-${item.id}`, label: item.estimate_number, detail: item.proposal_title, href: `/estimates?id=${item.id}` })),
    ...jobItems.filter((item) => `${item.job_number} ${item.customer_display_name} ${item.service_location_label}`.toLowerCase().includes(needle)).map((item) => ({ id: `job-${item.id}`, label: item.job_number, detail: `${item.customer_display_name} · ${item.service_location_label}`, href: `/jobs/${item.id}` })),
    ...invoiceItems.filter((item) => (item.invoice_number ?? "").toLowerCase().includes(needle)).map((item) => ({ id: `invoice-${item.id}`, label: item.invoice_number, detail: item.status, href: `/invoices/${item.id}` })),
  ] : [];

  return <div className="space-y-6">
    <header><p className="text-sm font-semibold text-action-primary">Field Operations / Customer to Cash</p><h1 className="mt-1 text-2xl font-bold sm:text-3xl">Revenue cycle</h1><p className="mt-2 max-w-3xl text-content-muted">Operational visibility from commercial decision through Job completion, Invoice handoff, and native Payment evidence. Amounts never influence queue priority.</p></header>
    <Card><CardHeader><CardTitle>Operational search</CardTitle></CardHeader><CardContent className="space-y-3"><Input aria-label="Search operational records" placeholder="Estimate, Job, Customer, Service Location, or Invoice" value={search} onChange={(event) => setSearch(event.target.value)} />{needle && <div className="grid gap-2">{results.map((result) => <Link key={result.id} className="flex flex-wrap justify-between gap-2 rounded-lg border border-stroke p-3 text-sm" to={result.href}><strong>{result.label}</strong><span className="text-content-muted">{result.detail}</span></Link>)}{results.length === 0 && <p className="text-sm text-content-muted">No loaded authoritative records match this search.</p>}</div>}<p className="text-xs text-content-muted">Results are limited to authorized records in the current operational projections.</p></CardContent></Card>
    <section aria-label="Operational revenue queues" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {canReadEstimates && <Queue title="Estimates awaiting decision" count={(estimates.data?.items ?? []).filter((item) => ["sent", "viewed"].includes(item.status)).length} detail="Presented proposals with no accepted or rejected state." href="/estimates" />}
      {canReadEstimates && <Queue title="Accepted not converted" count={(estimates.data?.items ?? []).filter((item) => item.status === "approved" && !item.converted_job_id).length} detail="Approved Estimates with no explicit Estimate-to-Job conversion evidence." href="/estimates?status=approved" />}
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
