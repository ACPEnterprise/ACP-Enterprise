import { useState, type FormEvent } from "react";
import axios from "axios";

import type { Estimate } from "../../types/estimates";
import { Alert, Button, Field, Input, Textarea } from "../../ui";

type Mutations = ReturnType<typeof import("../../hooks/useEstimates").useEstimateMutations>;

function decisionRecoveryMessage(error: unknown) {
  if (axios.isAxiosError(error)) {
    const recovery = (error.response?.data as { detail?: { recovery?: string } })?.detail?.recovery;
    if (recovery === "RETRY_AFTER_REFRESH") return "Estimate authority changed. Refresh before recording this Customer decision.";
    if (recovery === "USER_CORRECTION_REQUIRED") return "Customer decision evidence requires correction. The entered evidence was retained.";
    if (recovery === "OWNER_ADMIN_ACTION_REQUIRED") return "This Estimate requires owner or administrator action before continuing.";
  }
  return "The Estimate action was not recorded. Refresh authoritative state before retrying.";
}

export function EstimateDecisionControls({ estimate, mutations }: { readonly estimate: Estimate; readonly mutations: Mutations }) {
  const [customerName, setCustomerName] = useState("");
  const [rejectionReason, setRejectionReason] = useState("");
  const [mode, setMode] = useState<"approve" | "reject" | null>(null);
  const transition = (action: "send" | "view" | "expire") => mutations.transition.mutate({ id: estimate.id, action, input: { branch_id: estimate.branch_id, expected_version: estimate.version, occurred_at: new Date().toISOString() } });
  const decide = (event: FormEvent) => {
    event.preventDefault();
    if (!mode) return;
    mutations.decide.mutate({ id: estimate.id, action: mode, input: { branch_id: estimate.branch_id, expected_version: estimate.version, occurred_at: new Date().toISOString(), customer_name: customerName, rejection_reason: mode === "reject" ? rejectionReason : undefined } });
  };
  const busy = mutations.transition.isPending || mutations.decide.isPending;
  const failure = mutations.transition.isError ? mutations.transition.error : mutations.decide.isError ? mutations.decide.error : null;
  return <section className="space-y-3 border-t border-stroke pt-4" aria-label="Estimate lifecycle">
    <div className="flex flex-wrap gap-2">
      {estimate.status === "draft" && <Button disabled={busy} onClick={() => transition("send")}>Record as presented</Button>}
      {estimate.status === "sent" && <Button variant="outline" disabled={busy} onClick={() => transition("view")}>Record customer view</Button>}
      {["sent", "viewed"].includes(estimate.status) && <><Button disabled={busy} onClick={() => setMode("approve")}>Record acceptance</Button><Button variant="outline" disabled={busy} onClick={() => setMode("reject")}>Record rejection</Button></>}
      {["draft", "sent", "viewed"].includes(estimate.status) && <Button variant="ghost" disabled={busy} onClick={() => transition("expire")}>Record expiration</Button>}
    </div>
    {mode && <form className="grid gap-3 rounded-lg bg-surface-subtle p-4" onSubmit={decide}><Field label="Customer name"><Input value={customerName} onChange={(event) => setCustomerName(event.target.value)} required /></Field>{mode === "reject" && <Field label="Rejection reason"><Textarea value={rejectionReason} onChange={(event) => setRejectionReason(event.target.value)} required /></Field>}<div className="flex gap-2"><Button type="submit" loading={mutations.decide.isPending}>Confirm {mode === "approve" ? "acceptance" : "rejection"}</Button><Button type="button" variant="ghost" onClick={() => setMode(null)}>Cancel</Button></div></form>}
    {failure && <Alert variant="danger" role="alert" aria-live="assertive">{decisionRecoveryMessage(failure)}</Alert>}
    <p className="text-xs text-content-muted">These controls record explicit Customer evidence. They do not send communications or infer a decision.</p>
  </section>;
}
