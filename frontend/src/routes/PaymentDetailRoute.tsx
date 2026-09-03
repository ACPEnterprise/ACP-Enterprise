import { useState, type FormEvent } from "react";
import { useParams } from "react-router";

import { getOperatorApiError } from "../api/errors";
import { useHasPermission } from "../auth";
import { ReceiptSummary } from "../components/payments/ReceiptSummary";
import { usePayment, usePaymentMutations } from "../hooks/usePayments";
import { Alert, Button, Card, CardContent, CardHeader, CardTitle, Input, Spinner } from "../ui";

export function PaymentDetailRoute() {
  const { receiptId = "" } = useParams();
  const canRead = useHasPermission("COMPANY_PAYMENT_READ");
  const query = usePayment(receiptId, canRead);
  const mutations = usePaymentMutations();
  const canApply = useHasPermission("COMPANY_PAYMENT_APPLY");
  const canRefund = useHasPermission("COMPANY_PAYMENT_REFUND");
  const [apply, setApply] = useState({ invoice: "", amount: "", version: "1" });
  const [refund, setRefund] = useState({ amount: "", reason: "" });

  if (!canRead) return <Alert variant="danger">You are not authorized to view this Payment.</Alert>;
  if (query.isPending) return <Spinner label="Loading payment" />;
  if (!query.data || query.isError) return <Alert variant="danger">Payment could not be loaded.</Alert>;

  const receipt = query.data;
  const mutationError = mutations.apply.error ?? mutations.refund.error;
  const safeMutationError = mutationError ? getOperatorApiError(mutationError, "Payment") : null;
  const applySubmit = (event: FormEvent) => {
    event.preventDefault();
    mutations.apply.mutate({ id: receipt.id, input: { branch_id: receipt.branch_id, invoice_id: apply.invoice, amount: apply.amount, expected_invoice_version: Number(apply.version), idempotency_key: crypto.randomUUID(), occurred_at: new Date().toISOString() } });
  };
  const refundSubmit = (event: FormEvent) => {
    event.preventDefault();
    mutations.refund.mutate({ id: receipt.id, input: { branch_id: receipt.branch_id, amount: refund.amount, reason: refund.reason, expected_version: receipt.version, idempotency_key: crypto.randomUUID() } });
  };

  return <div className="mx-auto max-w-4xl space-y-6 pb-12">
    <ReceiptSummary receipt={receipt}/>
    {safeMutationError && <Alert variant="danger">{safeMutationError.message} Refresh both the receipt and Invoice before retrying; prior evidence was not rewritten.</Alert>}
    {canApply && <Card><CardHeader><CardTitle>Apply to Invoice</CardTitle></CardHeader><CardContent><form className="grid gap-3 sm:grid-cols-3" onSubmit={(event) => void applySubmit(event)}><Input aria-label="Invoice ID" required value={apply.invoice} onChange={(event)=>setApply({...apply,invoice:event.target.value})}/><Input aria-label="Application amount" required type="number" step="0.01" value={apply.amount} onChange={(event)=>setApply({...apply,amount:event.target.value})}/><Input aria-label="Invoice version" required type="number" value={apply.version} onChange={(event)=>setApply({...apply,version:event.target.value})}/><Button type="submit" loading={mutations.apply.isPending}>Apply receipt</Button></form></CardContent></Card>}
    {canRefund && <Card><CardHeader><CardTitle>Refund unapplied funds</CardTitle></CardHeader><CardContent><form className="grid gap-3 sm:grid-cols-2" onSubmit={(event)=>void refundSubmit(event)}><Input aria-label="Refund amount" required type="number" step="0.01" value={refund.amount} onChange={(event)=>setRefund({...refund,amount:event.target.value})}/><Input aria-label="Refund reason" required value={refund.reason} onChange={(event)=>setRefund({...refund,reason:event.target.value})}/><Button type="submit" loading={mutations.refund.isPending}>Request refund</Button></form></CardContent></Card>}
  </div>;
}
