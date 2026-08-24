import { useState, type FormEvent } from "react";
import { useParams } from "react-router";
import { useHasPermission } from "../auth";
import { ReceiptSummary } from "../components/payments/ReceiptSummary";
import { usePayment, usePaymentMutations } from "../hooks/usePayments";
import { Alert, Button, Card, CardContent, CardHeader, CardTitle, Input, Spinner } from "../ui";

export function PaymentDetailRoute() {
  const { receiptId = "" } = useParams(); const query = usePayment(receiptId); const mutations = usePaymentMutations();
  const canApply = useHasPermission("COMPANY_PAYMENT_APPLY"); const canRefund = useHasPermission("COMPANY_PAYMENT_REFUND");
  const [apply, setApply] = useState({ invoice: "", amount: "", version: "1" }); const [refund, setRefund] = useState({ amount: "", reason: "" });
  if (query.isPending) return <Spinner label="Loading payment" />; if (!query.data || query.isError) return <Alert variant="danger">Payment could not be loaded.</Alert>; const receipt = query.data;
  const applySubmit = async (e: FormEvent) => { e.preventDefault(); await mutations.apply.mutateAsync({ id: receipt.id, input: { branch_id: receipt.branch_id, invoice_id: apply.invoice, amount: apply.amount, expected_invoice_version: Number(apply.version), idempotency_key: crypto.randomUUID(), occurred_at: new Date().toISOString() } }); };
  const refundSubmit = async (e: FormEvent) => { e.preventDefault(); await mutations.refund.mutateAsync({ id: receipt.id, input: { branch_id: receipt.branch_id, amount: refund.amount, reason: refund.reason, expected_version: receipt.version, idempotency_key: crypto.randomUUID() } }); };
  return <div className="mx-auto max-w-4xl space-y-6 pb-12"><ReceiptSummary receipt={receipt}/>{canApply && <Card><CardHeader><CardTitle>Apply to Invoice</CardTitle></CardHeader><CardContent><form className="grid gap-3 sm:grid-cols-3" onSubmit={(e) => void applySubmit(e)}><Input aria-label="Invoice ID" required value={apply.invoice} onChange={(e)=>setApply({...apply,invoice:e.target.value})}/><Input aria-label="Application amount" required type="number" step="0.01" value={apply.amount} onChange={(e)=>setApply({...apply,amount:e.target.value})}/><Input aria-label="Invoice version" required type="number" value={apply.version} onChange={(e)=>setApply({...apply,version:e.target.value})}/><Button type="submit" loading={mutations.apply.isPending}>Apply receipt</Button></form></CardContent></Card>}{canRefund && <Card><CardHeader><CardTitle>Refund unapplied funds</CardTitle></CardHeader><CardContent><form className="grid gap-3 sm:grid-cols-2" onSubmit={(e)=>void refundSubmit(e)}><Input aria-label="Refund amount" required type="number" step="0.01" value={refund.amount} onChange={(e)=>setRefund({...refund,amount:e.target.value})}/><Input aria-label="Refund reason" required value={refund.reason} onChange={(e)=>setRefund({...refund,reason:e.target.value})}/><Button type="submit" loading={mutations.refund.isPending}>Request refund</Button></form></CardContent></Card>}</div>;
}
