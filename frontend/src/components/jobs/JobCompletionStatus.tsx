import { Link } from "react-router";

import { useFieldJobState } from "../../hooks/useTechnicianField";
import { Alert, Badge, Card, CardContent, CardHeader, CardTitle, Spinner } from "../../ui";

const label = (value: string) => value.replaceAll("_", " ");

export function JobCompletionStatus({ jobId }: { readonly jobId: string }) {
  const field = useFieldJobState(jobId);
  if (field.isPending) return <Spinner label="Loading completion readiness" />;
  if (field.isError) return <Alert variant="information">Field completion authority is not established for this Job.</Alert>;
  const state = field.data;
  return <Card><CardHeader><CardTitle>Completion and commercial handoff</CardTitle></CardHeader><CardContent className="space-y-4">
    <div className="grid gap-3 sm:grid-cols-3">
      <div><p className="text-xs text-content-muted">Completion readiness</p><Badge variant="neutral">{state.completion_ready ? "Ready" : "Blocked"}</Badge></div>
      <div><p className="text-xs text-content-muted">Commercial authority</p><Badge variant="neutral">{label(state.commercial_authorization)}</Badge></div>
      <div><p className="text-xs text-content-muted">Invoice handoff</p><Badge variant="neutral">{state.invoice_handoff_status ? label(state.invoice_handoff_status) : "Not started"}</Badge></div>
    </div>
    {!state.completion_ready && state.missing_requirements.length > 0 && <div><p className="text-sm font-semibold">Required evidence still missing</p><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-content-muted">{state.missing_requirements.map((requirement) => <li key={requirement}>{label(requirement)}</li>)}</ul></div>}
    {state.invoice_id && <Link className="text-sm font-semibold text-action-primary" to={`/invoices/${state.invoice_id}`}>Open authoritative Invoice</Link>}
    <p className="text-xs text-content-muted">This view is read-only. Field evidence, Job completion, and Invoice creation remain governed by their domain authorities.</p>
  </CardContent></Card>;
}
