import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { createBridgePeriod, createCutoverReview, getCutoverGates, getCutoverReview, getDirectDepositReadiness, writeCutoverFact } from "../../api/payrollCutover";
import { Alert, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Spinner } from "../../ui";

const human = (value: string) => value.replaceAll("_", " ").toLowerCase();

export function PayrollCutoverReview() {
  const client = useQueryClient();
  const review = useQuery({ queryKey: ["payroll", "cutover-review"], queryFn: getCutoverReview });
  const gates = useQuery({ queryKey: ["payroll", "cutover-gates"], queryFn: getCutoverGates, enabled: Boolean(review.data?.review) });
  const deposit = useQuery({ queryKey: ["payroll", "direct-deposit-readiness"], queryFn: getDirectDepositReadiness });
  const [message, setMessage] = useState("");
  const refresh = () => { void client.invalidateQueries({ queryKey: ["payroll", "cutover-review"] }); void client.invalidateQueries({ queryKey: ["payroll", "cutover-gates"] }); };
  const start = useMutation({ mutationFn: createCutoverReview, onSuccess: refresh });
  const saveFact = useMutation({ mutationFn: ({ body, certify }: { body: Record<string, unknown>; certify: boolean }) => writeCutoverFact(body, certify), onSuccess: refresh });
  const bridge = useMutation({ mutationFn: createBridgePeriod, onSuccess: refresh });
  if (review.isLoading) return <Spinner label="Loading Payroll cutover review" />;
  if (review.isError || !review.data) return <Alert variant="danger">Payroll cutover review is unavailable. No authority was changed.</Alert>;
  if (!review.data.review) return <Card><CardHeader><CardTitle>Cutover Review</CardTitle><CardDescription>Candidate evidence remains non-authoritative until certified.</CardDescription></CardHeader><CardContent><Button onClick={() => start.mutate({})}>Start protected review</Button></CardContent></Card>;
  const reviewId = review.data.review.id;
  const submitFact = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setMessage(""); const data = new FormData(event.currentTarget);
    try { await saveFact.mutateAsync({ certify: data.get("mode") === "certify", body: { review_id: reviewId, expected_review_version: review.data.review!.version, employee_id: data.get("employee_id") || null, fact_key: data.get("fact_key"), candidate_classification: "HUMAN_REVIEW", candidate_reference: {}, action: data.get("action"), certifier_role: data.get("certifier_role"), certified_value: data.get("value") || null, idempotency_key: crypto.randomUUID() } }); setMessage("Fact revision saved. Candidate and certified authority remain distinct."); event.currentTarget.reset(); } catch { setMessage("Fact revision was rejected. Blank, authority, scope, or concurrency checks may be incomplete."); }
  };
  const submitBridge = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setMessage(""); const data = new FormData(event.currentTarget);
    try { await bridge.mutateAsync({ review_id: reviewId, expected_review_version: review.data.review!.version, period_start: data.get("period_start"), period_end: data.get("period_end"), pay_date: data.get("pay_date"), source_type: "manual_paper_check", source_reference: data.get("source_reference"), idempotency_key: crypto.randomUUID() }); setMessage("Externally calculated bridge period saved as draft; it is not ACP Payroll."); event.currentTarget.reset(); } catch { setMessage("Bridge period was rejected. Review chronology, overlap, and authority."); }
  };
  return <section className="space-y-4" aria-labelledby="cutover-title">
    <Card><CardHeader><CardTitle id="cutover-title">Cutover Review</CardTitle><CardDescription>QuickBooks legacy → manual paper-check bridge → prospective ACP authority. No Payroll is calculated or executed here.</CardDescription></CardHeader><CardContent className="space-y-3">
      <p>Review state: <strong>{human(review.data.review.lifecycle)}</strong></p>
      <p>Certified/current facts: <strong>{review.data.facts.length}</strong> · Bridge periods recorded: <strong>{review.data.bridge_periods.length}</strong></p>
      <Alert variant={gates.data?.status === "READY_FOR_CUTOVER_APPROVAL" ? "success" : "warning"} title={gates.data?.status ?? "Cutover gates loading"}>{gates.data?.blockers.length ? `${gates.data.blockers.length} mandatory gate(s) remain.` : "All certification gates are complete; separate approval is still required."}</Alert>
    </CardContent></Card>
    <Card><CardHeader><CardTitle>Employee certification</CardTitle><CardDescription>Confirm, correct, provide, or explicitly mark facts not applicable. Blank remains missing.</CardDescription></CardHeader><CardContent className="space-y-3">
      <form className="grid gap-3 md:grid-cols-2" onSubmit={submitFact}>
        <label>Employee<select className="block w-full" name="employee_id"><option value="">Company-level fact</option>{review.data.employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.display_name} — {employee.status}</option>)}</select></label>
        <label>Fact key<input className="block w-full" name="fact_key" required /></label>
        <label>Action<select className="block w-full" name="action"><option value="confirm">Confirm</option><option value="correct">Correct</option><option value="provide">Provide</option><option value="not_applicable">Not Applicable</option></select></label>
        <label>Certification role<select className="block w-full" name="certifier_role"><option value="owner">Owner</option><option value="accountant">Accountant</option></select></label>
        <label className="md:col-span-2">Protected value<input autoComplete="off" className="block w-full" name="value" type="password" /><span className="text-xs text-content-muted">Encrypted server-side; never returned to this page.</span></label>
        <label><input name="mode" type="checkbox" value="certify" /> Certify now (otherwise Save Draft)</label>
        <Button disabled={saveFact.isPending} type="submit">Save Draft / Certification</Button>
      </form>
    </CardContent></Card>
    <Card><CardHeader><CardTitle>Manual bridge Payroll</CardTitle><CardDescription>Externally calculated / manually paid. This does not create an ACP Payroll run.</CardDescription></CardHeader><CardContent><form className="grid gap-3 md:grid-cols-2" onSubmit={submitBridge}><label>Period start<input className="block w-full" name="period_start" type="date" required /></label><label>Period end<input className="block w-full" name="period_end" type="date" required /></label><label>Pay/check date<input className="block w-full" name="pay_date" type="date" required /></label><label>Source/document reference<input className="block w-full" name="source_reference" required /></label><Button disabled={bridge.isPending} type="submit">Save bridge Payroll draft</Button></form></CardContent></Card>
    <Card><CardHeader><CardTitle>Accountant certification</CardTitle><CardDescription>YTD wages/taxes, liabilities, remittances, and opening coverage require accountant authority. Aggregate accounting balances are reconciliation evidence only.</CardDescription></CardHeader><CardContent><p>{review.data.facts.filter((fact) => fact.certifier_role === "accountant" && fact.certification_state === "certified").length} accountant-certified fact(s).</p></CardContent></Card>
    <Card><CardHeader><CardTitle>Direct-deposit readiness</CardTitle><CardDescription>Read-only readiness; no ACH, prenote, micro-entry, or bank transaction can be initiated.</CardDescription></CardHeader><CardContent><Alert variant="warning" title={deposit.data?.status ?? "Loading"}>{deposit.data?.blockers.map(human).join(" · ") || "Readiness unavailable"}</Alert></CardContent></Card>
    {message && <Alert variant={message.includes("saved") ? "success" : "danger"}>{message}</Alert>}
  </section>;
}
