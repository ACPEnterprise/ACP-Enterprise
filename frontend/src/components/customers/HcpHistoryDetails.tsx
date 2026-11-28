import { useEffect, useRef, useState } from "react";
import { apiClient } from "../../api/client";
import type { HcpCustomerSourceHistory } from "../../types/hcpSourceHistory";
import { Badge } from "../../ui";

function money(cents: number | null | undefined) {
  return typeof cents === "number"
    ? new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(cents / 100)
    : "Amount unavailable in source evidence";
}

function dateValue(value: string | null | undefined) {
  if (!value) return "Date unavailable in source evidence";
  const dateOnly = value.match(/^\d{4}-\d{2}-\d{2}/)?.[0];
  const date = dateOnly ? new Date(`${dateOnly}T12:00:00`) : new Date(value);
  return Number.isNaN(date.getTime())
    ? "Date unavailable in source evidence"
    : date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function jobDate(job: HcpCustomerSourceHistory["jobs"][number]) {
  return job.service_date ?? job.scheduled_start ?? job.created_at ?? "";
}

function locationLabel(
  history: HcpCustomerSourceHistory,
  sourceLocationId: string | null,
) {
  const location = history.locations.find((item) => item.source_id === sourceLocationId);
  if (!location) return "Held relationship: source Location unavailable";
  return [location.address, location.city, location.state, location.postal_code]
    .filter(Boolean)
    .join(", ");
}

function invoiceStatus(
  invoice: HcpCustomerSourceHistory["invoices"][number] | undefined,
) {
  if (!invoice) return "Payment status unavailable in source evidence";
  if (invoice.balance_cents === 0 && invoice.amount_cents === 0 && invoice.payments.length === 0) {
    return "Source status: paid; payment transaction unavailable";
  }
  if (invoice.balance_cents === 0) return "Paid";
  if (typeof invoice.balance_cents === "number" && invoice.balance_cents > 0) {
    return "Partially paid or unpaid";
  }
  return invoice.status ?? "Payment status unavailable in source evidence";
}

function paymentNoteDisclosure(notes: Array<{ content: string | null }>) {
  const note = notes.find((item) => /paid|payment|ach|check|card/i.test(item.content ?? ""));
  return note?.content ?? null;
}

function RecoveredAttachment({
  attachment,
}: {
  readonly attachment: HcpCustomerSourceHistory["jobs"][number]["attachments"][number];
}) {
  const host = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const node = host.current;
    if (!node || !attachment.view_url) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisible(true);
        observer.disconnect();
      }
    }, { rootMargin: "240px" });
    observer.observe(node);
    return () => observer.disconnect();
  }, [attachment.view_url]);

  useEffect(() => {
    if (!visible || !attachment.view_url || objectUrl) return;
    let disposed = false;
    void apiClient.get<Blob>(attachment.view_url, { responseType: "blob" })
      .then((response) => {
        if (!disposed) setObjectUrl(URL.createObjectURL(response.data));
      })
      .catch(() => {
        if (!disposed) setError(true);
      });
    return () => {
      disposed = true;
    };
  }, [attachment.view_url, objectUrl, visible]);

  useEffect(() => () => {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  }, [objectUrl]);

  const image = attachment.file_type?.startsWith("image/");
  return (
    <div ref={host} className="min-w-0 rounded-lg border border-stroke bg-surface-subtle p-2">
      {objectUrl ? (
        <a className="block text-action-primary underline" href={objectUrl} target="_blank" rel="noreferrer">
          {image ? <img className="aspect-[4/3] w-full rounded-md object-cover" src={objectUrl} alt={attachment.file_name ?? "Recovered historical photograph"} /> : <span className="block p-2">Open {attachment.file_name ?? "recovered document"}</span>}
          <span className="mt-1 block truncate text-xs">{attachment.file_name ?? attachment.source_id}</span>
        </a>
      ) : error ? (
        <p className="p-2 text-sm text-status-danger">Recovered media could not be opened in this authenticated session.</p>
      ) : (
        <p className="p-2 text-sm text-content-muted">Loading recovered media…</p>
      )}
      {attachment.conflict_reason && <span className="text-xs text-content-muted"> · {attachment.conflict_reason}</span>}
    </div>
  );
}

export function HcpHistoryDetails({
  history,
  compact = false,
}: {
  readonly history: HcpCustomerSourceHistory;
  readonly compact?: boolean;
}) {
  const jobs = [...history.jobs].sort((left, right) =>
    jobDate(right).localeCompare(jobDate(left)),
  );
  const estimateById = new Map(history.estimates.map((item) => [item.source_id, item]));
  const invoiceByJob = new Map(history.invoices.map((item) => [item.source_job_id, item]));

  return (
    <section aria-label="Historical customer journey" className="mt-4 rounded-xl border-2 border-[#c01529] bg-surface-subtle p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="font-semibold">Service history</h4>
          <p className="mt-1 text-xs text-content-muted">
            Complete source-backed history, newest service date first. Historical records are read-only.
          </p>
        </div>
        <Badge variant="information">SOURCE BACKED</Badge>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3 lg:grid-cols-6">
        <div><dt className="text-content-muted">Locations</dt><dd className="font-semibold">{history.counts.locations}</dd></div>
        <div><dt className="text-content-muted">Jobs</dt><dd className="font-semibold">{history.counts.jobs}</dd></div>
        <div><dt className="text-content-muted">Appointments</dt><dd className="font-semibold">{history.counts.appointments}</dd></div>
        <div><dt className="text-content-muted">Estimates</dt><dd className="font-semibold">{history.counts.estimates}</dd></div>
        <div><dt className="text-content-muted">Invoices</dt><dd className="font-semibold">{history.counts.invoices}</dd></div>
        <div><dt className="text-content-muted">Payments</dt><dd className="font-semibold">{history.counts.payments}</dd></div>
      </dl>

      {!compact && (
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {history.locations.map((location) => (
            <div className="rounded-lg border border-stroke bg-surface p-3" key={location.source_id}>
              <p className="font-medium">{location.address ?? "Address unavailable in source evidence"}</p>
              <p className="text-sm text-content-muted">{[location.city, location.state, location.postal_code].filter(Boolean).join(", ") || "Location details unavailable"}</p>
            </div>
          ))}
        </div>
      )}

      <div className="mt-5 space-y-3">
        {jobs.map((job) => {
          const invoice = invoiceByJob.get(job.source_id);
          const notes = job.notes ?? [];
          const attachments = job.attachments ?? [];
          const assignedEmployees = job.assigned_employee_source_ids ?? [];
          const assignedEmployeeNames = job.assigned_employee_names ?? [];
          const estimateIds = [job.original_estimate_id, ...(job.original_estimate_ids ?? [])].filter(
            (value): value is string => Boolean(value),
          );
          const estimate = estimateIds.map((id) => estimateById.get(id)).find(Boolean);
          return (
            <article className="rounded-xl border-2 border-[#c01529] bg-surface p-4" key={job.source_id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-action-primary">{dateValue(jobDate(job))}</p>
                  <h5 className="mt-1 text-lg font-semibold">{job.number ? `Job ${job.number}` : "Job number unavailable in source evidence"}</h5>
                </div>
                <Badge variant="neutral">{job.status ?? "Status unavailable in source evidence"}</Badge>
              </div>
              <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                <div><dt className="text-content-muted">Scheduled service date</dt><dd>{dateValue(job.service_date ?? job.scheduled_start)}</dd></div>
                <div><dt className="text-content-muted">Service address</dt><dd>{locationLabel(history, job.source_location_id) !== "Held relationship: source Location unavailable" ? locationLabel(history, job.source_location_id) : job.source_location ? [job.source_location.address, job.source_location.city, job.source_location.state, job.source_location.postal_code].filter(Boolean).join(", ") || "Address unavailable in source evidence" : "Held relationship: source Location unavailable"}</dd></div>
                <div><dt className="text-content-muted">Invoice amount</dt><dd>{money(invoice?.amount_cents)}</dd></div>
                <div><dt className="text-content-muted">Payment status</dt><dd>{invoiceStatus(invoice)}</dd></div>
                <div><dt className="text-content-muted">Technicians</dt><dd>{assignedEmployeeNames.length ? assignedEmployeeNames.join(", ") : assignedEmployees.length ? assignedEmployees.join(", ") : "Technician assignment unavailable in source evidence"}</dd></div>
                <div><dt className="text-content-muted">Original source ID</dt><dd className="break-all">{job.source_id}</dd></div>
              </dl>
              <p className="mt-3 whitespace-pre-wrap text-sm">{job.description || "Job description unavailable in source evidence"}</p>

              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                <details open className="rounded-lg border border-stroke p-3">
                  <summary className="cursor-pointer font-medium">Estimate</summary>
                  {estimate ? (
                    <>
                      <p className="mt-1 text-sm">{estimate.number ?? "Estimate number unavailable"} · {estimate.status ?? "Status unavailable"}</p>
                      <ul className="mt-2 space-y-1 text-sm">{estimate.options.map((option) => <li key={option.source_id}>{option.name ?? "Line item description unavailable"} · {money(option.amount_cents)}</li>)}</ul>
                    </>
                  ) : <p className="mt-1 text-sm text-content-muted">No preceding estimate is linked in source evidence.</p>}
                </details>
                <details open className="rounded-lg border border-stroke p-3">
                  <summary className="cursor-pointer font-medium">Invoice and payments</summary>
                  {invoice ? (
                    <>
                      <p className="mt-1 text-sm"><strong>Invoice {invoice.number ?? "number unavailable"}</strong> · {dateValue(invoice.invoice_date)} · {invoiceStatus(invoice)}</p>
                      <p className="mt-1 text-sm">Outstanding: {money(invoice.balance_cents)}</p>
                      {paymentNoteDisclosure(notes) && <p className="mt-2 rounded-md bg-status-warning/10 p-2 text-sm text-status-warning">Source note: “{paymentNoteDisclosure(notes)}”. This note is preserved but is not counted as a payment transaction because the source invoice contains no payment record.</p>}
                      {(invoice.line_items ?? []).length > 0 && <ul className="mt-2 space-y-1 text-sm">{invoice.line_items.map((line, index) => <li key={`${invoice.source_id}-line-${index}`}>{line.description ?? "Line item description unavailable"} · {money(line.amount_cents)}</li>)}</ul>}
                      {invoice.payments.length > 0 ? <ul className="mt-2 space-y-1 text-sm">{invoice.payments.map((payment) => <li key={payment.source_id}>Payment {payment.source_id} · {dateValue(payment.date)} · {money(payment.amount_cents)} · {payment.status}</li>)}</ul> : <p className="mt-2 text-sm text-content-muted">No payment records in source evidence.</p>}
                    </>
                  ) : <p className="mt-1 text-sm text-content-muted">No invoice is linked in source evidence.</p>}
                </details>
              </div>

              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <details open className="rounded-lg border border-stroke p-3">
                  <summary className="cursor-pointer font-medium">Notes</summary>
                  {notes.length > 0 ? <ul className="mt-2 space-y-1 text-sm">{notes.map((note, index) => <li key={note.source_id ?? `note-${index}`}>{note.content ?? "Note content unavailable in source evidence"}</li>)}</ul> : <p className="mt-1 text-sm text-content-muted">No notes are present in source evidence.</p>}
                </details>
                <details open className="rounded-lg border border-stroke p-3">
                  <summary className="cursor-pointer font-medium">Photographs and documents</summary>
                  {attachments.length > 0 ? <div className="mt-2 grid gap-3 sm:grid-cols-2">{attachments.map((attachment) => attachment.body_available && attachment.view_url ? <RecoveredAttachment attachment={attachment} key={attachment.source_id} /> : <div className="min-w-0 rounded-lg border border-stroke bg-surface-subtle p-2" key={attachment.source_id}><span className="block text-sm">{attachment.file_name ?? attachment.source_id} · {attachment.status ?? "Unavailable"}</span>{attachment.conflict_reason && <span className="text-xs text-content-muted"> · {attachment.conflict_reason}</span>}</div>)}</div> : <p className="mt-1 text-sm text-content-muted">No photographs or documents are present in source evidence.</p>}
                </details>
              </div>
            </article>
          );
        })}
        {jobs.length === 0 && <p className="text-sm text-content-muted">No historical jobs are available in source evidence.</p>}
      </div>
    </section>
  );
}
