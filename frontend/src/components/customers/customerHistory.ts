import type { EstimateSummary } from "../../types/estimates";
import type { InvoiceWorkspaceItem } from "../../types/invoices";
import type { JobListItem } from "../../types/jobs";
import type { PaymentReceipt } from "../../types/payments";
import type { AppointmentDetail } from "../../types/scheduling";

export interface CustomerHistorySources {
  readonly customerId: string;
  readonly currentJobs: readonly JobListItem[];
  readonly historicalJobs: readonly JobListItem[];
  readonly appointments: readonly AppointmentDetail[];
  readonly estimates: readonly EstimateSummary[];
  readonly invoices: readonly InvoiceWorkspaceItem[];
  readonly payments: readonly PaymentReceipt[];
}

export interface CustomerHistoryItem {
  readonly id: string;
  readonly occurredAt: string;
  readonly title: string;
  readonly detail: string;
  readonly href: string;
  readonly authority: string;
  readonly locationId: string | null;
}

const amount = (currency: string, value: string) => `${currency} ${value}`;

export function buildCustomerHistoryItems(props: CustomerHistorySources): CustomerHistoryItem[] {
  const returnTo = encodeURIComponent(`/customers/${props.customerId}`);
  const jobs = [...props.currentJobs, ...props.historicalJobs].map((job) => ({
    id: `job:${job.id}`,
    occurredAt: job.completed_at ?? job.updated_at,
    title: `Job ${job.job_number}`,
    detail: `${job.status.replaceAll("_", " ")} · ${job.service_location_label}`,
    href: `/jobs/${job.id}?returnTo=${returnTo}`,
    authority: "Native ACP Job",
    locationId: job.service_location_id,
  }));
  const appointments = props.appointments.map((item) => ({
    id: `appointment:${item.id}`,
    occurredAt: item.arrival_window_start_at ?? item.updated_at,
    title: `Appointment ${item.appointment_number}`,
    detail: item.status.replaceAll("_", " "),
    href: `/appointments/${item.id}`,
    authority: "Native ACP Scheduling",
    locationId: item.service_location_id,
  }));
  const estimates = props.estimates.map((item) => ({
    id: `estimate:${item.id}`,
    occurredAt: item.updated_at,
    title: `Estimate ${item.estimate_number}`,
    detail: `${item.status.replaceAll("_", " ")} · ${amount(item.currency, item.total_amount)}`,
    href: `/estimates?id=${item.id}`,
    authority: "Native ACP Estimate",
    locationId: item.service_location_id,
  }));
  const invoices = props.invoices.map((item) => ({
    id: `invoice:${item.id}`,
    occurredAt: item.last_ar_activity_at ?? `${item.issue_date}T00:00:00Z`,
    title: `Invoice ${item.invoice_number}`,
    detail: `${item.status.replaceAll("_", " ")} · ${amount(item.currency, item.total_amount)} total · ${amount(item.currency, item.open_amount)} open`,
    href: `/invoices/${item.id}`,
    authority: "Native ACP Invoice / AR",
    locationId: item.service_location_id,
  }));
  const payments = props.payments.map((item) => ({
    id: `payment:${item.id}`,
    occurredAt: item.captured_at,
    title: "Payment receipt",
    detail: `${item.status.replaceAll("_", " ")} · ${amount(item.currency, item.captured_amount)} captured · ${amount(item.currency, item.applied_amount)} applied · ${amount(item.currency, item.refunded_amount)} refunded`,
    href: `/payments/${item.id}`,
    authority: "Native ACP Payment evidence",
    locationId: null,
  }));
  return [...jobs, ...appointments, ...estimates, ...invoices, ...payments]
    .sort((left, right) => right.occurredAt.localeCompare(left.occurredAt) || left.id.localeCompare(right.id))
    .slice(0, 50);
}
