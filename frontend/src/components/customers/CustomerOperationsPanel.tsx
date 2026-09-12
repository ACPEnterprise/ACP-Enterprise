import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Link } from "react-router";

import { useHasPermission } from "../../auth";
import { useEstimates } from "../../hooks/useEstimates";
import { useCustomerBalance, useInvoiceWorkspace } from "../../hooks/useInvoices";
import { useJobs } from "../../hooks/useJobs";
import { usePayments } from "../../hooks/usePayments";
import { useAppointments } from "../../hooks/useScheduling";
import { Alert, Badge, Button, Card, Spinner } from "../../ui";

function windowBoundary(days: number) {
  const value = new Date();
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString();
}

export function CustomerOperationsPanel({ customerId }: { customerId: string }) {
  const [appointmentCursor, setAppointmentCursor] = useState({ customerId, page: 1 });
  const [invoiceCursor, setInvoiceCursor] = useState({ customerId, page: 1 });
  const appointmentPage = appointmentCursor.customerId === customerId ? appointmentCursor.page : 1;
  const invoicePage = invoiceCursor.customerId === customerId ? invoiceCursor.page : 1;
  const invoicePageSize = 25;
  const canReadJobs = useHasPermission("COMPANY_JOB_READ");
  const canReadScheduling = useHasPermission("COMPANY_SCHEDULING_READ");
  const canReadEstimates = useHasPermission("COMPANY_ESTIMATE_READ");
  const canReadInvoices = useHasPermission("COMPANY_INVOICE_READ");
  const canReadPayments = useHasPermission("COMPANY_PAYMENT_READ");
  const asOf = new Date().toISOString().slice(0, 10);
  const jobs = useJobs({ customerId, page: 1, pageSize: 25 }, canReadJobs);
  const appointments = useAppointments(
    { startAt: windowBoundary(-180), endAt: windowBoundary(365), customerId, page: appointmentPage, pageSize: 50 },
    canReadScheduling,
  );
  const estimates = useEstimates(undefined, customerId, canReadEstimates);
  const invoices = useInvoiceWorkspace(
    { asOf, state: "all", customerId, limit: invoicePageSize, offset: (invoicePage - 1) * invoicePageSize },
    canReadInvoices,
  );
  const customerBalance = useCustomerBalance(customerId, asOf, canReadInvoices);
  const payments = usePayments(canReadPayments);
  const customerPayments = (payments.data ?? []).filter((item) => item.customer_id === customerId);
  const relatedQueries = [jobs, appointments, estimates, invoices, customerBalance, payments];
  const appointmentTotalPages = appointments.data
    ? Math.ceil(appointments.data.total_count / appointments.data.page_size)
    : 0;
  const invoiceTotalPages = customerBalance.data
    ? Math.ceil(customerBalance.data.native_invoice_count / invoicePageSize)
    : 0;

  return (
    <Card className="p-ui-4 sm:p-ui-6">
      <p className="text-sm text-action-primary">Customer-to-cash</p>
      <h3 className="mt-1 text-xl font-semibold">Operational workspace</h3>
      <p className="mt-2 text-sm text-content-muted">Authorized domain views remain separate; unavailable sections are not promoted into Customer authority.</p>
      {relatedQueries.some((query) => query.isLoading) && <div className="mt-4"><Spinner label="Loading related work" /></div>}
      {relatedQueries.some((query) => query.isError) && <div className="mt-4"><Alert variant="warning">Some related work is unavailable. Customer identity remains available; refresh before relying on this workspace as a complete related-work view.</Alert></div>}
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        {canReadEstimates && <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Estimates</h4>{estimates.data && <p className="mt-1 text-xs text-content-muted">Showing {estimates.data.items.length} of {estimates.data.total} related Estimates.</p>}<div className="mt-3 space-y-2">{(estimates.data?.items ?? []).map((item) => <Link key={item.id} to={`/estimates?id=${item.id}`} className="flex justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.estimate_number} · {item.proposal_title}</span><Badge variant="neutral">{item.status}</Badge></Link>)}{estimates.isSuccess && estimates.data.items.length === 0 && <p className="text-sm text-content-muted">No Estimates.</p>}</div></section>}
        {canReadJobs && <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Jobs</h4>{jobs.data && <p className="mt-1 text-xs text-content-muted">Showing {jobs.data.items.length} of {jobs.data.total_count} related Jobs.</p>}<div className="mt-3 space-y-2">{(jobs.data?.items ?? []).map((item) => <Link key={item.id} to={`/jobs/${item.id}`} className="flex justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.job_number} · {item.service_location_label}</span><Badge variant="neutral">{item.status}</Badge></Link>)}{jobs.isSuccess && jobs.data.items.length === 0 && <p className="text-sm text-content-muted">No Jobs are currently linked in native Job authority.</p>}</div>{jobs.data && jobs.data.total_count > 0 && <Link className="mt-3 inline-flex text-sm font-semibold text-action-primary" to={`/jobs?customerId=${customerId}`}>Open all related Jobs</Link>}</section>}
        {canReadScheduling && <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Appointments</h4>{appointments.data && <p className="mt-1 text-xs text-content-muted">Showing {appointments.data.items.length} of {appointments.data.total_count} Appointments in the operating window · page {appointments.data.page} of {appointmentTotalPages || 1}.</p>}<div className="mt-3 space-y-2">{(appointments.data?.items ?? []).map((item) => <Link key={item.id} to={`/appointments/${item.id}`} className="flex justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.appointment_number} · {item.arrival_window_start_at ? new Date(item.arrival_window_start_at).toLocaleString() : "Unscheduled"}</span><Badge variant="neutral">{item.status}</Badge></Link>)}{appointments.isSuccess && appointments.data.items.length === 0 && <p className="text-sm text-content-muted">No Appointments in the operational window.</p>}</div>{appointmentTotalPages > 1 && <div className="mt-3 flex gap-2"><Button type="button" variant="outline" disabled={appointmentPage === 1} onClick={() => setAppointmentCursor({ customerId, page: Math.max(1, appointmentPage - 1) })} leadingIcon={<ChevronLeft size={16} />}>Previous Appointments</Button><Button type="button" variant="outline" disabled={appointmentPage >= appointmentTotalPages} onClick={() => setAppointmentCursor({ customerId, page: appointmentPage + 1 })} trailingIcon={<ChevronRight size={16} />}>Next Appointments</Button></div>}</section>}
        {canReadInvoices && <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Invoices</h4>{invoices.data && customerBalance.data && <p className="mt-1 text-xs text-content-muted">Showing {invoices.data.length} of {customerBalance.data.native_invoice_count} related Invoices · page {invoicePage} of {invoiceTotalPages || 1}.</p>}<div className="mt-3 space-y-2">{(invoices.data ?? []).map((item) => <Link key={item.id} to={`/invoices/${item.id}`} className="flex justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.invoice_number} · {item.currency} {item.open_amount} open</span><Badge variant="neutral">{item.status}</Badge></Link>)}{invoices.isSuccess && invoices.data.length === 0 && <p className="text-sm text-content-muted">No Invoices.</p>}</div>{invoiceTotalPages > 1 && <div className="mt-3 flex gap-2"><Button type="button" variant="outline" disabled={invoicePage === 1} onClick={() => setInvoiceCursor({ customerId, page: Math.max(1, invoicePage - 1) })} leadingIcon={<ChevronLeft size={16} />}>Previous Invoices</Button><Button type="button" variant="outline" disabled={invoicePage >= invoiceTotalPages} onClick={() => setInvoiceCursor({ customerId, page: invoicePage + 1 })} trailingIcon={<ChevronRight size={16} />}>Next Invoices</Button></div>}</section>}
        {canReadPayments && <section className="rounded-xl border border-stroke p-4 lg:col-span-2"><h4 className="font-semibold">Payment evidence</h4><p className="mt-1 text-xs text-content-muted">Provider receipt assertions; settlement and cash are not inferred. This view matches the Customer against the latest bounded authorized receipt page and does not claim complete Payment history.</p><div className="mt-3 grid gap-2 md:grid-cols-2">{customerPayments.map((item) => <Link key={item.id} to={`/payments/${item.id}`} className="flex justify-between gap-3 rounded-lg bg-surface-subtle p-3 text-sm"><span>{item.currency} {item.captured_amount} provider-captured · {item.applied_amount} applied</span><Badge variant="neutral">{item.status}</Badge></Link>)}{payments.isSuccess && customerPayments.length === 0 && <p className="text-sm text-content-muted">No matching Payment receipts are present in the bounded result.</p>}</div></section>}
      </div>
    </Card>
  );
}
