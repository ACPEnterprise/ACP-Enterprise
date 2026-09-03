import { Link } from "react-router";

import { useHasPermission } from "../../auth";
import { useEstimates } from "../../hooks/useEstimates";
import { useInvoices } from "../../hooks/useInvoices";
import { useJobs } from "../../hooks/useJobs";
import { usePayments } from "../../hooks/usePayments";
import { useAppointments } from "../../hooks/useScheduling";
import { Badge, Card } from "../../ui";

function windowBoundary(days: number) {
  const value = new Date();
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString();
}

export function CustomerOperationsPanel({ customerId }: { customerId: string }) {
  const canReadJobs = useHasPermission("COMPANY_JOB_READ");
  const canReadScheduling = useHasPermission("COMPANY_SCHEDULING_READ");
  const canReadEstimates = useHasPermission("COMPANY_ESTIMATE_READ");
  const canReadInvoices = useHasPermission("COMPANY_INVOICE_READ");
  const canReadPayments = useHasPermission("COMPANY_PAYMENT_READ");
  const jobs = useJobs({ customerId, page: 1, pageSize: 25 }, canReadJobs);
  const appointments = useAppointments(
    { startAt: windowBoundary(-180), endAt: windowBoundary(365), customerId, pageSize: 50 },
    canReadScheduling,
  );
  const estimates = useEstimates(undefined, customerId, canReadEstimates);
  const invoices = useInvoices(canReadInvoices);
  const payments = usePayments(canReadPayments);
  const customerInvoices = (invoices.data ?? []).filter((item) => item.customer_id === customerId);
  const customerPayments = (payments.data ?? []).filter((item) => item.customer_id === customerId);

  return (
    <Card className="p-ui-4 sm:p-ui-6">
      <p className="text-sm text-action-primary">Customer-to-cash</p>
      <h3 className="mt-1 text-xl font-semibold">Operational workspace</h3>
      <p className="mt-2 text-sm text-content-muted">Authorized domain views remain separate; unavailable sections are not promoted into Customer authority.</p>
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        {canReadEstimates && <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Estimates</h4><div className="mt-3 space-y-2">{(estimates.data?.items ?? []).map((item) => <Link key={item.id} to={`/estimates?id=${item.id}`} className="flex justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.estimate_number} · {item.proposal_title}</span><Badge variant="neutral">{item.status}</Badge></Link>)}{estimates.isSuccess && estimates.data.items.length === 0 && <p className="text-sm text-content-muted">No Estimates.</p>}</div></section>}
        {canReadJobs && <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Jobs</h4><div className="mt-3 space-y-2">{(jobs.data?.items ?? []).map((item) => <Link key={item.id} to={`/jobs/${item.id}`} className="flex justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.job_number} · {item.service_location_label}</span><Badge variant="neutral">{item.status}</Badge></Link>)}{jobs.isSuccess && jobs.data.items.length === 0 && <p className="text-sm text-content-muted">No Jobs.</p>}</div></section>}
        {canReadScheduling && <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Appointments</h4><div className="mt-3 space-y-2">{(appointments.data?.items ?? []).map((item) => <Link key={item.id} to={`/appointments/${item.id}`} className="flex justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.appointment_number} · {item.arrival_window_start_at ? new Date(item.arrival_window_start_at).toLocaleString() : "Unscheduled"}</span><Badge variant="neutral">{item.status}</Badge></Link>)}{appointments.isSuccess && appointments.data.items.length === 0 && <p className="text-sm text-content-muted">No Appointments in the operational window.</p>}</div></section>}
        {canReadInvoices && <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Invoices</h4><div className="mt-3 space-y-2">{customerInvoices.map((item) => <Link key={item.id} to={`/invoices/${item.id}`} className="flex justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.invoice_number} · {item.currency} {item.open_amount} open</span><Badge variant="neutral">{item.status}</Badge></Link>)}{invoices.isSuccess && customerInvoices.length === 0 && <p className="text-sm text-content-muted">No Invoices.</p>}</div></section>}
        {canReadPayments && <section className="rounded-xl border border-stroke p-4 lg:col-span-2"><h4 className="font-semibold">Payment evidence</h4><p className="mt-1 text-xs text-content-muted">Provider receipt assertions; settlement and cash are not inferred.</p><div className="mt-3 grid gap-2 md:grid-cols-2">{customerPayments.map((item) => <Link key={item.id} to={`/payments/${item.id}`} className="flex justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.currency} {item.captured_amount} provider-captured · {item.applied_amount} applied</span><Badge variant="neutral">{item.status}</Badge></Link>)}{payments.isSuccess && customerPayments.length === 0 && <p className="text-sm text-content-muted">No native Payment receipts.</p>}</div></section>}
      </div>
    </Card>
  );
}
