import { useState, type FormEvent } from "react";
import type { CommercialHistoryItem, CommercialReport, Estimate, EstimateFollowUp } from "../../types/estimates";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Field, Input, Select } from "../../ui";

function currencyBuckets(values: Record<string, string>) {
  const entries = Object.entries(values);
  return entries.length ? entries.map(([currency, value]) => `${currency} ${value}`).join(" · ") : "None";
}

export function CommercialSummary({ report }: { readonly report?: CommercialReport }) {
  if (!report) return null;
  const metrics = [["Created", report.created], ["Presented", report.presented], ["Accepted", report.accepted], ["Converted", report.converted]] as const;
  return <Card><CardHeader><CardTitle>Commercial performance</CardTitle><CardDescription>Operational Estimate evidence—not recognized revenue or profitability.</CardDescription></CardHeader><CardContent className="space-y-4"><dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">{metrics.map(([label, value]) => <div key={label} className="rounded-lg border border-stroke p-3"><dt className="text-xs text-content-muted">{label}</dt><dd className="text-2xl font-semibold">{value}</dd></div>)}</dl><div className="grid gap-2 text-sm sm:grid-cols-2"><p><strong>Accepted commercial value:</strong> {currencyBuckets(report.accepted_value_by_currency)}</p><p><strong>Outstanding presented value:</strong> {currencyBuckets(report.outstanding_value_by_currency)}</p></div></CardContent></Card>;
}

export function FollowUpQueue({ items }: { readonly items: EstimateFollowUp[] }) {
  return <Card><CardHeader><CardTitle>Sales follow-up queue</CardTitle><CardDescription>Provider-neutral work only; no message is sent from this queue.</CardDescription></CardHeader><CardContent>{items.length ? <ul className="space-y-2">{items.map((item) => <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-stroke p-3"><div><p className="font-medium">Estimate {item.estimate_id.slice(0, 8)}</p><p className="text-xs text-content-muted">Assigned operator {item.assigned_user_id.slice(0, 8)} · sequence {item.sequence}{item.due_at ? ` · due ${new Date(item.due_at).toLocaleString()}` : " · cadence not configured"}</p></div><Badge variant="neutral">{item.state}</Badge></li>)}</ul> : <p className="rounded-lg border border-dashed border-stroke p-5 text-sm text-content-muted">No governed follow-up work has been recorded.</p>}</CardContent></Card>;
}

export function CommercialEngagementControls({ estimate, userId, mutations }: { readonly estimate: Estimate; readonly userId: string; readonly mutations: ReturnType<typeof import("../../hooks/useEstimates").useEstimateMutations> }) {
  const [recipient, setRecipient] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [prepared, setPrepared] = useState(false);
  const presented = ["sent", "viewed"].includes(estimate.status);
  const prepare = async (event: FormEvent) => {
    event.preventDefault();
    await mutations.preparePresentation.mutateAsync({ id: estimate.id, input: { branch_id: estimate.branch_id, recipient_reference: recipient, channel: "protected_link", idempotency_key: `presentation:${crypto.randomUUID()}` } });
    setPrepared(true);
  };
  const followUp = async () => {
    await mutations.followUp.mutateAsync({ id: estimate.id, input: { branch_id: estimate.branch_id, assigned_user_id: userId, state: "open", due_at: dueAt ? new Date(dueAt).toISOString() : undefined, occurred_at: new Date().toISOString(), idempotency_key: `followup:${crypto.randomUUID()}` } });
  };
  return <section className="grid gap-4 border-t border-stroke pt-4 lg:grid-cols-2" aria-label="Commercial engagement">
    <form className="space-y-3 rounded-lg border border-stroke p-4" onSubmit={(event) => void prepare(event)}><h3 className="font-semibold">Protected presentation</h3><p className="text-sm text-content-muted">Prepare provider-neutral access for the exact current revision. This does not send email or SMS.</p><Field label="Recipient authority"><Input value={recipient} onChange={(event) => setRecipient(event.target.value)} placeholder="Authorized recipient reference" required /></Field><Select aria-label="Delivery channel" value="protected_link" disabled><option value="protected_link">Protected access</option></Select><Button type="submit" disabled={!presented} loading={mutations.preparePresentation.isPending}>Prepare access</Button>{!presented && <p className="text-xs text-content-muted">Present this Estimate before preparing Customer access.</p>}{prepared && <Alert variant="success">Protected access authority is prepared. Provider delivery remains intentionally disconnected.</Alert>}{mutations.preparePresentation.isError && <Alert variant="danger">Access preparation failed. Refresh the current revision before retrying.</Alert>}</form>
    <div className="space-y-3 rounded-lg border border-stroke p-4"><h3 className="font-semibold">Follow-up work</h3><p className="text-sm text-content-muted">Create accountable work without assuming a Company cadence or sending a communication.</p><Field label="Due at (optional)"><Input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></Field><Button type="button" variant="secondary" disabled={!presented} loading={mutations.followUp.isPending} onClick={() => void followUp()}>Add to my follow-up queue</Button>{mutations.followUp.isError && <Alert variant="danger">Follow-up was not recorded. Refresh authoritative state.</Alert>}</div>
  </section>;
}

export function CommercialTimeline({ items }: { readonly items: CommercialHistoryItem[] }) {
  return <section className="space-y-3 border-t border-stroke pt-4" aria-label="Commercial history"><h3 className="font-semibold">Commercial history</h3>{items.length ? <ol className="space-y-2">{items.map((item, index) => <li key={`${item.evidence_type}-${item.occurred_at}-${index}`} className="grid gap-1 rounded-lg border border-stroke p-3 sm:grid-cols-[10rem_1fr_auto]"><Badge variant="neutral">{item.evidence_type.replaceAll("_", " ")}</Badge><span>{item.state.replaceAll("_", " ")}{item.detail ? ` · ${item.detail}` : ""}</span><time className="text-xs text-content-muted" dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleString()}</time></li>)}</ol> : <p className="text-sm text-content-muted">No lifecycle evidence has been recorded.</p>}</section>;
}
