import { Link } from "react-router";

import type { CustomerProperty } from "../../types/customers";
import type { EstimateSummary } from "../../types/estimates";
import type { InvoiceWorkspaceItem, CustomerEvidenceClassification } from "../../types/invoices";
import type { JobListItem } from "../../types/jobs";
import type { PaymentReceipt } from "../../types/payments";
import type { AppointmentDetail } from "../../types/scheduling";
import type { CustomerTimelineEntry } from "../../types/customers";
import type { HcpCustomerSourceHistory } from "../../types/hcpSourceHistory";
import { Badge } from "../../ui";
import { buildCustomerHistoryItems } from "./customerHistory";

type CompletenessState = "COMPLETE" | "PARTIAL" | "SOURCE_BACKED" | "NOT_ADMITTED" | "UNAVAILABLE";

interface CustomerHistoryWorkspaceProps {
  readonly customerId: string;
  readonly locations: readonly CustomerProperty[];
  readonly currentJobs: readonly JobListItem[];
  readonly historicalJobs: readonly JobListItem[];
  readonly appointments: readonly AppointmentDetail[];
  readonly estimates: readonly EstimateSummary[];
  readonly invoices: readonly InvoiceWorkspaceItem[];
  readonly payments: readonly PaymentReceipt[];
  readonly evidence: readonly CustomerEvidenceClassification[];
  readonly sourceHistory?: HcpCustomerSourceHistory;
  readonly unavailableDomains: readonly string[];
  readonly timelineEntries?: readonly CustomerTimelineEntry[];
  readonly timelinePage?: number;
  readonly timelineTotalCount?: number;
  readonly timelineTotalPages?: number;
  readonly timelineLoading?: boolean;
  readonly timelineFetching?: boolean;
  readonly onPreviousTimelinePage?: () => void;
  readonly onNextTimelinePage?: () => void;
}

const terminalJobs = new Set(["completed", "cancelled"]);

function completeness(
  label: string,
  state: CompletenessState,
  explanation: string,
) {
  const variant = state === "COMPLETE" ? "success" : state === "UNAVAILABLE" ? "danger" : state === "SOURCE_BACKED" ? "information" : "warning";
  return <div className="rounded-lg border border-stroke p-3" key={label}><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium">{label}</span><Badge variant={variant}>{state.replaceAll("_", " ")}</Badge></div><p className="mt-1 text-xs text-content-muted">{explanation}</p></div>;
}

export function CustomerHistoryWorkspace(props: CustomerHistoryWorkspaceProps) {
  const allJobs = [...props.currentJobs, ...props.historicalJobs];
  const history = buildCustomerHistoryItems(props);
  const latestJob = [...allJobs].sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0];
  const sourceEvidence = props.evidence.filter((item) => item.source_system !== "acp_native");
  const unavailable = new Set(props.unavailableDomains);
  const domainState = (domain: string): CompletenessState => unavailable.has(domain) ? "UNAVAILABLE" : "PARTIAL";
  const invoiceState: CompletenessState = sourceEvidence.some((item) => ["STALE", "CONFLICTING", "PARTIAL"].includes(item.classification))
    ? "PARTIAL"
    : domainState("Invoices");

  return <div className="mt-5 space-y-4">
    <section aria-label="Customer history overview" className="rounded-xl border border-stroke p-4">
      <h4 className="font-semibold">Customer history overview</h4>
      <p className="mt-1 text-xs text-content-muted">This summary shows the customer records currently available here.</p>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4 lg:grid-cols-7">
        <div><dt className="text-content-muted">Locations</dt><dd className="text-lg font-semibold">{props.locations.length}</dd></div>
        <div><dt className="text-content-muted">Jobs</dt><dd className="text-lg font-semibold">{allJobs.length}</dd></div>
        <div><dt className="text-content-muted">Appointments</dt><dd className="text-lg font-semibold">{props.appointments.length}</dd></div>
        <div><dt className="text-content-muted">Estimates</dt><dd className="text-lg font-semibold">{props.estimates.length}</dd></div>
        <div><dt className="text-content-muted">Invoices</dt><dd className="text-lg font-semibold">{props.invoices.length}</dd></div>
        <div><dt className="text-content-muted">Payments</dt><dd className="text-lg font-semibold">{props.payments.length}</dd></div>
      </dl>
      <p className="mt-3 text-sm text-content-muted">{latestJob ? <>Latest Job: <Link className="font-medium text-action-primary" to={`/jobs/${latestJob.id}?returnTo=${encodeURIComponent(`/customers/${props.customerId}`)}`}>{latestJob.job_number}</Link> · {new Date(latestJob.updated_at).toLocaleString()}</> : "No Job is available in the current customer record."}</p>
    </section>

    <section aria-label="History completeness" className="rounded-xl border border-stroke p-4">
      <h4 className="font-semibold">History completeness</h4>
      <p className="mt-1 text-xs text-content-muted">This view brings older imported history and newer TwelveHats activity together. Record details remain available for review.</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {completeness("Customer", "COMPLETE", "The Customer record is available.")}
        {completeness("Locations", domainState("Locations"), unavailable.has("Locations") ? "Location evidence could not be loaded." : "Customer locations are available in the unified record.")}
        {completeness("Jobs", domainState("Jobs"), unavailable.has("Jobs") ? "Job evidence could not be loaded." : "Migrated and TwelveHats Jobs are shown together.")}
        {completeness("Appointments", domainState("Appointments"), unavailable.has("Appointments") ? "Appointment history could not be loaded." : "Appointments shown here cover one year before and after today.")}
        {completeness("Estimates", domainState("Estimates"), unavailable.has("Estimates") ? "Estimate evidence could not be loaded." : "Customer-linked Estimates are shown in the same workflow.")}
        {completeness("Invoices", invoiceState, "This view shows up to the 100 newest customer invoices.")}
        {completeness("Payments", domainState("Payments"), unavailable.has("Payments") ? "Payment history could not be loaded." : "This view shows up to the 100 newest customer payment receipts.")}
        {completeness(
          "Photos & attachments",
          props.sourceHistory ? "SOURCE_BACKED" : "UNAVAILABLE",
          props.sourceHistory
            ? "Recovered source media and attachment status are shown in the service history below."
            : "Photos and attachments are not yet available in this customer history view.",
        )}
      </div>
      {sourceEvidence.some((item) => item.classification === "UNAVAILABLE") && <p className="mt-3 text-sm text-content-muted">Some history could not be loaded. A missing item does not mean there was no activity.</p>}
    </section>

    <section aria-label="Service Location history" className="rounded-xl border border-stroke p-4">
      <h4 className="font-semibold">Service Location history</h4>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {props.locations.map((location) => {
          const locationJobs = allJobs.filter((item) => item.service_location_id === location.id);
          const open = locationJobs.filter((item) => !terminalJobs.has(item.status));
          const historical = locationJobs.filter((item) => terminalJobs.has(item.status));
          const locationAppointments = props.appointments.filter((item) => item.service_location_id === location.id);
          const latest = [...locationJobs].sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0];
          return <article className="rounded-lg bg-surface-subtle p-4" key={location.id}>
            <h5 className="font-medium">{location.address_line_1}</h5>
            <p className="text-sm text-content-muted">{location.address_line_2 ? `${location.address_line_2}, ` : ""}{location.city}, {location.state} {location.postal_code}</p>
            <p className="mt-2 text-sm">{open.length} open · {historical.length} closed · {locationAppointments.length} Appointments</p>
            <p className="mt-1 text-xs text-content-muted">{latest ? `Latest service activity ${new Date(latest.updated_at).toLocaleString()}.` : "No Job activity is available for this Location."}</p>
            <Link className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-action-primary" to={`/jobs?customerId=${encodeURIComponent(props.customerId)}&serviceLocationId=${encodeURIComponent(location.id)}`}>View Location Jobs</Link>
          </article>;
        })}
        {props.locations.length === 0 && <p className="text-sm text-content-muted">No Service Locations are available in this customer record.</p>}
      </div>
    </section>

    <section aria-label="Activity timeline" className="rounded-xl border border-stroke p-4">
      <h4 className="font-semibold">Activity timeline</h4>
      <p className="mt-1 text-xs text-content-muted">Migrated and TwelveHats activity appears together in chronological order.</p>
      <ol className="mt-3 space-y-2">
        {history.map((item) => <li className="rounded-lg bg-surface-subtle p-3 text-sm" id={item.kind === "activity" ? item.href.slice(1) : undefined} key={item.id}><div className="flex flex-wrap items-start justify-between gap-2">{item.kind === "activity" ? <span className="font-medium text-content">{item.title}</span> : <Link className="font-medium text-action-primary" to={item.href}>{item.title}</Link>}<time className="text-xs text-content-muted" dateTime={item.occurredAt}>{new Date(item.occurredAt).toLocaleString()}</time></div><p className="mt-1 text-content-muted">{item.detail}</p></li>)}
        {history.length === 0 && <li className="text-sm text-content-muted">No activity is available in this customer record.</li>}
      </ol>
      {props.timelineLoading && <p className="mt-3 text-sm text-content-muted">Loading customer activity…</p>}
      {props.timelineTotalPages && props.timelineTotalPages > 1 && <div className="mt-4 flex flex-col gap-3 border-t border-stroke pt-4 text-sm sm:flex-row sm:items-center sm:justify-between"><span className="text-content-muted">Activity page {props.timelinePage ?? 1} of {props.timelineTotalPages}</span><div className="grid grid-cols-2 gap-2"><button type="button" className="min-h-11 rounded-lg border border-stroke-strong px-3 font-medium" disabled={(props.timelinePage ?? 1) <= 1 || props.timelineFetching} onClick={props.onPreviousTimelinePage}>Previous activity</button><button type="button" className="min-h-11 rounded-lg border border-stroke-strong px-3 font-medium" disabled={(props.timelinePage ?? 1) >= props.timelineTotalPages || props.timelineFetching} onClick={props.onNextTimelinePage}>Next activity</button></div></div>}
    </section>
  </div>;
}
