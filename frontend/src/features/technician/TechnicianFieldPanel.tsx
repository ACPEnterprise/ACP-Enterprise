import { useState } from "react";

import { useTechnicianField } from "../../hooks/useTechnicianField";
import type { TechnicianItineraryItem } from "../../types/technician";
import type { CustomerDisposition } from "../../types/technicianField";
import { Alert, Button, Field, Input, Spinner, Textarea } from "../../ui";

export function TechnicianFieldPanel({ item }: { readonly item: TechnicianItineraryItem }) {
  const field = useTechnicianField(item.job_id ?? "", item.job_version ?? 1, item.assignment_version);
  const [summary, setSummary] = useState("");
  const [disposition, setDisposition] = useState<CustomerDisposition>("approved");
  const [customerName, setCustomerName] = useState("");
  const [reason, setReason] = useState("");
  const busy = field.note.isPending || field.approval.isPending || field.arrival.isPending || field.lifecycle.isPending || field.handoff.isPending;

  if (!item.job_id) return null;
  if (field.state.isLoading) return <Spinner label="Loading field controls" />;
  if (field.state.isError) return <Alert variant="danger" title="Field controls unavailable">Refresh before changing this job.</Alert>;
  const state = field.state.data;
  return (
    <div className="space-y-ui-3 border-t border-border-subtle pt-ui-3">
      <div className="flex flex-wrap gap-ui-2">
        {item.arrival_state === "pending" && <Button disabled={busy} onClick={() => field.arrival.mutate({ appointmentId: item.appointment_id, state: "en_route", version: item.assignment_version })}>On my way</Button>}
        {item.arrival_state === "en_route" && <Button disabled={busy} onClick={() => field.arrival.mutate({ appointmentId: item.appointment_id, state: "arrived", version: item.assignment_version })}>I&apos;ve arrived</Button>}
        {item.arrival_state === "arrived" && item.job_status === "ready" && <Button disabled={busy} onClick={() => field.lifecycle.mutate({ action: "start", version: item.job_version ?? 1 })}>Start work</Button>}
        {item.job_status === "in_progress" && <Button variant="outline" disabled={busy} onClick={() => field.lifecycle.mutate({ action: "pause", version: item.job_version ?? 1 })}>Pause</Button>}
        {item.job_status === "paused" && <Button disabled={busy} onClick={() => field.lifecycle.mutate({ action: "resume", version: item.job_version ?? 1 })}>Resume</Button>}
      </div>
      {!state?.work_summary_recorded && (
        <Field label="Work performed" controlId={`work-summary-${item.job_id}`}>
          <Textarea id={`work-summary-${item.job_id}`} value={summary} onChange={(event) => setSummary(event.target.value)} rows={3} />
          <Button className="mt-ui-2" disabled={busy || !summary.trim()} onClick={() => field.note.mutate(summary)}>Save work summary</Button>
        </Field>
      )}
      {!state?.customer_disposition && (
        <div className="space-y-ui-2">
          <Field label="Customer disposition" controlId={`disposition-${item.job_id}`}>
            <select id={`disposition-${item.job_id}`} className="min-h-11 w-full rounded-md border border-border-default bg-surface-primary px-ui-3" value={disposition} onChange={(event) => setDisposition(event.target.value as CustomerDisposition)}>
              <option value="approved">Approved</option><option value="unavailable">Unavailable</option><option value="refused">Refused</option>
            </select>
          </Field>
          {disposition === "approved" ? <Input aria-label="Customer name" placeholder="Customer name" value={customerName} onChange={(event) => setCustomerName(event.target.value)} /> : <Textarea aria-label="Disposition reason" placeholder="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />}
          <Button disabled={busy || (disposition === "approved" ? !customerName.trim() : !reason.trim())} onClick={() => field.approval.mutate({ disposition, customerName, reason })}>Record disposition</Button>
        </div>
      )}
      {state && !state.completion_ready && (
        <Alert variant="warning" title="Completion requirements remain">
          {state.missing_requirements.length > 0
            ? state.missing_requirements.join(", ")
            : "Refresh authoritative field state before completion."}
          {state.commercial_authorization === "missing" && " An accepted estimate or authorized non-billable disposition is required."}
        </Alert>
      )}
      {state?.commercial_authorization === "non_billable" && (
        <Alert title="Authorized non-billable work">{state.non_billable_reason}</Alert>
      )}
      {item.job_status === "in_progress" && state?.completion_ready && <Button disabled={busy} onClick={() => field.lifecycle.mutate({ action: "complete", version: item.job_version ?? 1 })}>Complete job</Button>}
      {item.job_status === "completed" && state?.invoice_handoff_status !== "completed" && <Button disabled={busy} onClick={() => field.handoff.mutate()}>Check invoice handoff</Button>}
      {state?.invoice_handoff_status === "completed" && <Alert variant="success" title="Invoice ready">The authoritative invoice handoff is complete.</Alert>}
      {state?.invoice_handoff_status === "pending" && <Alert variant="warning" title="Invoice handoff pending">No invoice has been reported complete. Retry after authoritative invoicing finishes.</Alert>}
      {state?.invoice_handoff_status === "reconciliation_required" && <Alert variant="danger" title="Invoice reconciliation required">Office review is required before this handoff can be treated as complete.</Alert>}
      {(field.note.isError || field.approval.isError || field.arrival.isError || field.lifecycle.isError || field.handoff.isError) && <Alert variant="danger" title="Action not recorded">Refresh authoritative state before retrying. No local success was assumed.</Alert>}
    </div>
  );
}
