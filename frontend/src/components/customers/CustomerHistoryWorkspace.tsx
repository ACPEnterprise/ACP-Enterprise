import { Link } from "react-router";

import type { CustomerProperty } from "../../types/customers";
import type { EstimateSummary } from "../../types/estimates";
import type { InvoiceWorkspaceItem, CustomerEvidenceClassification } from "../../types/invoices";
import type { JobListItem } from "../../types/jobs";
import type { PaymentReceipt } from "../../types/payments";
import type { AppointmentDetail } from "../../types/scheduling";
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
  readonly unavailableDomains: readonly string[];
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
  const hasSourceEvidence = sourceEvidence.length > 0;
  const unavailable = new Set(props.unavailableDomains);
  const domainState = (domain: string): CompletenessState => unavailable.has(domain) ? "UNAVAILABLE" : "PARTIAL";
  const invoiceState: CompletenessState = sourceEvidence.some((item) => ["STALE", "CONFLICTING", "PARTIAL"].includes(item.classification))
    ? "PARTIAL"
    : hasSourceEvidence
      ? "SOURCE_BACKED"
      : domainState("Invoices");

  return <div className="mt-5 space-y-4">
    <section aria-label="Customer history overview" className="rounded-xl border border-stroke p-4">
      <h4 className="font-semibold">Customer history overview</h4>
      <p className="mt-1 text-xs text-content-muted">Counts cover the bounded, authorized native projections loaded below. They are not Migration population totals.</p>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4 lg:grid-cols-7">
        <div><dt className="text-content-muted">Locations</dt><dd className="text-lg font-semibold">{props.locations.length}</dd></div>
        <div><dt className="text-content-muted">Open Jobs</dt><dd className="text-lg font-semibold">{props.currentJobs.length}</dd></div>
        <div><dt className="text-content-muted">Historical Jobs</dt><dd className="text-lg font-semibold">{props.historicalJobs.length}</dd></div>
        <div><dt className="text-content-muted">Appointments</dt><dd className="text-lg font-semibold">{props.appointments.length}</dd></div>
        <div><dt className="text-content-muted">Estimates</dt><dd className="text-lg font-semibold">{props.estimates.length}</dd></div>
        <div><dt className="text-content-muted">Invoices</dt><dd className="text-lg font-semibold">{props.invoices.length}</dd></div>
        <div><dt className="text-content-muted">Payments</dt><dd className="text-lg font-semibold">{props.payments.length}</dd></div>
      </dl>
      <p className="mt-3 text-sm text-content-muted">{latestJob ? <>Latest Job: <Link className="font-medium text-action-primary" to={`/jobs/${latestJob.id}?returnTo=${encodeURIComponent(`/customers/${props.customerId}`)}`}>{latestJob.job_number}</Link> · {new Date(latestJob.updated_at).toLocaleString()}</> : "No admitted Job is available in the bounded projection."}</p>
    </section>

    <section aria-label="History completeness" className="rounded-xl border border-stroke p-4">
      <h4 className="font-semibold">History completeness</h4>
      <p className="mt-1 text-xs text-content-muted">Complete means this native projection loaded completely—not that every historical source record has been admitted.</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {completeness("Customer", "COMPLETE", "The native Customer detail is authoritative and available.")}
        {completeness("Locations", domainState("Locations"), unavailable.has("Locations") ? "Location evidence could not be loaded." : "Native Locations are available; source admission completeness is not published.")}
        {completeness("Jobs", domainState("Jobs"), unavailable.has("Jobs") ? "Job evidence could not be loaded." : "Current and historical native Job pages are bounded to 25 each.")}
        {completeness("Appointments", domainState("Appointments"), unavailable.has("Appointments") ? "Appointment evidence could not be loaded." : "Appointments are bounded to one year before and after today.")}
        {completeness("Estimates", domainState("Estimates"), unavailable.has("Estimates") ? "Estimate evidence could not be loaded." : "Native Customer-linked Estimates are available; unresolved source links are not invented.")}
        {completeness("Invoices", invoiceState, hasSourceEvidence ? "Native and classified source evidence coexist; inspect the AR evidence section." : "Native Invoice history is bounded to 100; source completeness is unavailable.")}
        {completeness("Payments", domainState("Payments"), unavailable.has("Payments") ? "Payment evidence could not be loaded." : "Native provider-neutral receipts are bounded to the 100 newest records.")}
        {completeness("Attachments", "UNAVAILABLE", "No Customer-wide attachment completeness contract exists. Job evidence remains authoritative where available.")}
      </div>
      {sourceEvidence.some((item) => item.classification === "HISTORICAL_SOURCE_EVIDENCE") && <p className="mt-3 text-sm text-content-muted">Some financial history is source-backed evidence and is not presented as native ACP Accounting truth.</p>}
      {sourceEvidence.some((item) => item.classification === "UNAVAILABLE") && <p className="mt-3 text-sm text-content-muted">Some source history is unavailable. Missing evidence is not treated as zero.</p>}
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
            <p className="mt-2 text-sm">{open.length} open · {historical.length} historical Jobs · {locationAppointments.length} Appointments</p>
            <p className="mt-1 text-xs text-content-muted">{latest ? `Latest admitted service evidence ${new Date(latest.updated_at).toLocaleString()}.` : "No admitted Job history for this Location."} Source admission status is not inferred.</p>
            <Link className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-action-primary" to={`/jobs?customerId=${encodeURIComponent(props.customerId)}&serviceLocationId=${encodeURIComponent(location.id)}`}>View Location Jobs</Link>
          </article>;
        })}
        {props.locations.length === 0 && <p className="text-sm text-content-muted">No native Service Locations are available. This does not prove source history is empty.</p>}
      </div>
    </section>

    <section aria-label="Combined service history" className="rounded-xl border border-stroke p-4">
      <h4 className="font-semibold">Combined service history</h4>
      <p className="mt-1 text-xs text-content-muted">Newest 50 items from the bounded native projections. Source-only events remain outside this timeline until admitted.</p>
      <ol className="mt-3 space-y-2">
        {history.map((item) => <li className="rounded-lg bg-surface-subtle p-3 text-sm" key={item.id}><div className="flex flex-wrap items-start justify-between gap-2"><Link className="font-medium text-action-primary" to={item.href}>{item.title}</Link><time className="text-xs text-content-muted" dateTime={item.occurredAt}>{new Date(item.occurredAt).toLocaleString()}</time></div><p className="mt-1 text-content-muted">{item.detail}</p><p className="mt-1 text-xs text-content-muted">Authority: {item.authority}</p></li>)}
        {history.length === 0 && <li className="text-sm text-content-muted">No admitted cross-domain history is available. Source-only history may still be unadmitted.</li>}
      </ol>
    </section>
  </div>;
}
