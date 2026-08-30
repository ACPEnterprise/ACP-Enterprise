import { useState, type FormEvent } from "react";

import type { Estimate } from "../../types/estimates";
import { Alert, Button, Field, Input, Textarea } from "../../ui";

type Mutations = ReturnType<typeof import("../../hooks/useEstimates").useEstimateMutations>;

export function EstimateDecisionControls({ estimate, mutations }: { readonly estimate: Estimate; readonly mutations: Mutations }) {
  const [customerName, setCustomerName] = useState("");
  const [rejectionReason, setRejectionReason] = useState("");
  const [mode, setMode] = useState<"approve" | "reject" | null>(null);
  const [revisionMode, setRevisionMode] = useState(false);
  const [revisionTitle, setRevisionTitle] = useState(estimate.current_revision.proposal_title);
  const transition = (action: "send" | "view" | "expire") => mutations.transition.mutate({ id: estimate.id, action, input: { branch_id: estimate.branch_id, expected_version: estimate.version, occurred_at: new Date().toISOString() } });
  const decide = (event: FormEvent) => {
    event.preventDefault();
    if (!mode) return;
    mutations.decide.mutate({ id: estimate.id, action: mode, input: { branch_id: estimate.branch_id, expected_version: estimate.version, occurred_at: new Date().toISOString(), customer_name: customerName, rejection_reason: mode === "reject" ? rejectionReason : undefined } });
  };
  const revise = async (event: FormEvent) => {
    event.preventDefault();
    await mutations.revise.mutateAsync({ id: estimate.id, input: { branch_id: estimate.branch_id, customer_id: estimate.customer_id, service_location_id: estimate.service_location_id ?? undefined, proposal_title: revisionTitle, customer_message: estimate.current_revision.customer_message ?? undefined, terms: estimate.current_revision.terms ?? undefined, expected_version: estimate.version, lines: estimate.current_revision.lines.map((line) => ({ snapshot_id: line.snapshot_id, title: line.title, description: line.description ?? undefined })), discount_type: estimate.current_revision.discount_type ?? undefined, discount_value: estimate.current_revision.discount_value ?? undefined } });
    setRevisionMode(false);
  };
  const busy = mutations.transition.isPending || mutations.decide.isPending || mutations.revise.isPending;
  return <section className="space-y-3 border-t border-stroke pt-4" aria-label="Estimate lifecycle">
    <div className="flex flex-wrap gap-2">
      {estimate.status === "draft" && <Button disabled={busy} onClick={() => transition("send")}>Record as presented</Button>}
      {estimate.status === "sent" && <Button variant="outline" disabled={busy} onClick={() => transition("view")}>Record customer view</Button>}
      {["sent", "viewed"].includes(estimate.status) && <><Button disabled={busy} onClick={() => setMode("approve")}>Record acceptance</Button><Button variant="outline" disabled={busy} onClick={() => setMode("reject")}>Record rejection</Button></>}
      {["draft", "sent", "viewed"].includes(estimate.status) && <Button variant="ghost" disabled={busy} onClick={() => transition("expire")}>Record expiration</Button>}
      {["draft", "sent", "viewed", "rejected", "expired"].includes(estimate.status) && <Button variant="outline" disabled={busy} onClick={() => setRevisionMode(true)}>Create successor revision</Button>}
    </div>
    {mode && <form className="grid gap-3 rounded-lg bg-surface-subtle p-4" onSubmit={decide}><Field label="Customer name"><Input value={customerName} onChange={(event) => setCustomerName(event.target.value)} required /></Field>{mode === "reject" && <Field label="Rejection reason"><Textarea value={rejectionReason} onChange={(event) => setRejectionReason(event.target.value)} required /></Field>}<div className="flex gap-2"><Button type="submit" loading={mutations.decide.isPending}>Confirm {mode === "approve" ? "acceptance" : "rejection"}</Button><Button type="button" variant="ghost" onClick={() => setMode(null)}>Cancel</Button></div></form>}
    {revisionMode && <form className="grid gap-3 rounded-lg border border-stroke p-4" onSubmit={(event) => void revise(event)}><Field label="Successor revision title"><Input value={revisionTitle} onChange={(event) => setRevisionTitle(event.target.value)} required /></Field><p className="text-xs text-content-muted">The successor preserves immutable Price Book snapshot lineage. Prior presentation and decision evidence remain historical.</p><div className="flex gap-2"><Button type="submit" loading={mutations.revise.isPending}>Create revision</Button><Button type="button" variant="ghost" onClick={() => setRevisionMode(false)}>Cancel</Button></div></form>}
    {(mutations.transition.isError || mutations.decide.isError || mutations.revise.isError) && <Alert variant="danger">The Estimate action was not recorded. Refresh authoritative state before retrying.</Alert>}
    <p className="text-xs text-content-muted">These controls record explicit Customer evidence. They do not send communications or infer a decision.</p>
  </section>;
}
