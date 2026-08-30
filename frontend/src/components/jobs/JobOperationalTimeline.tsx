import { Link } from "react-router";

import { useHasPermission } from "../../auth";
import { useInvoices } from "../../hooks/useInvoices";
import type { JobDetail } from "../../types/jobs";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "../../ui";

interface TimelineItem { readonly at: string; readonly label: string; readonly detail: string; readonly href?: string }

export function JobOperationalTimeline({ job }: { readonly job: JobDetail }) {
  const canReadInvoices = useHasPermission("COMPANY_INVOICE_READ");
  const invoices = useInvoices(canReadInvoices);
  const items: TimelineItem[] = [
    { at: job.created_at, label: "Job created", detail: job.job_number },
    ...(job.activated_at ? [{ at: job.activated_at, label: "Job made ready", detail: "Operational lifecycle" }] : []),
    ...job.appointments.flatMap((appointment) => appointment.arrival_window_start_at ? [{ at: appointment.arrival_window_start_at, label: "Appointment scheduled", detail: appointment.appointment_number, href: `/appointments/${appointment.appointment_id}` }] : []),
    ...(job.started_at ? [{ at: job.started_at, label: "Field work started", detail: "Authoritative Job state" }] : []),
    ...(job.completed_at ? [{ at: job.completed_at, label: "Job completed", detail: "Completion evidence accepted" }] : []),
    ...(invoices.data ?? []).filter((invoice) => invoice.job_id === job.id).flatMap((invoice) => [
      { at: invoice.created_at, label: "Invoice handoff created", detail: invoice.invoice_number, href: `/invoices/${invoice.id}` },
      ...(invoice.issued_at ? [{ at: invoice.issued_at, label: "Invoice issued", detail: invoice.status, href: `/invoices/${invoice.id}` }] : []),
      ...(invoice.status === "paid" ? [{ at: invoice.updated_at, label: "Invoice paid", detail: "Native Invoice state", href: `/invoices/${invoice.id}` }] : []),
    ]),
  ].sort((left, right) => new Date(left.at).getTime() - new Date(right.at).getTime());
  return <Card><CardHeader><CardTitle>Customer-to-cash history</CardTitle></CardHeader><CardContent><ol className="space-y-3">{items.map((item, index) => <li key={`${item.label}-${item.at}-${index}`} className="grid gap-1 border-l-2 border-stroke pl-4 sm:grid-cols-[11rem_1fr_auto]"><time className="text-xs text-content-muted">{new Date(item.at).toLocaleString()}</time><div><p className="font-medium">{item.label}</p><p className="text-sm text-content-muted">{item.detail}</p></div>{item.href && <Link className="text-sm font-semibold text-action-primary" to={item.href}>Open</Link>}</li>)}</ol>{!canReadInvoices && <Badge className="mt-4" variant="neutral">Invoice history hidden by permission</Badge>}<p className="mt-4 text-xs text-content-muted">Timeline entries are derived from authoritative domain timestamps. Missing evidence remains absent.</p></CardContent></Card>;
}
