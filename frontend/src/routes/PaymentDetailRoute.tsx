import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";

import { getOperatorApiError } from "../api/errors";
import { useHasPermission } from "../auth";
import { ReceiptSummary } from "../components/payments/ReceiptSummary";
import { usePayment, usePaymentMutations } from "../hooks/usePayments";
import { useInvoiceWorkspace } from "../hooks/useInvoices";
import { Alert, Button, Card, CardContent, CardHeader, CardTitle, Input, Spinner } from "../ui";

export function PaymentDetailRoute() {
  const { receiptId = "" } = useParams();
  const canRead = useHasPermission("COMPANY_PAYMENT_READ");
  const query = usePayment(receiptId, canRead);
  const mutations = usePaymentMutations();
  const canApply = useHasPermission("COMPANY_PAYMENT_APPLY");
  const canReadInvoices = useHasPermission("COMPANY_INVOICE_READ");
  const canRefund = useHasPermission("COMPANY_PAYMENT_REFUND");
  const [apply, setApply] = useState({ invoice: "", amount: "" });
  const [refund, setRefund] = useState({ amount: "", reason: "" });
  const today = new Date().toISOString().slice(0, 10);
  const openInvoices = useInvoiceWorkspace(
    { asOf: today, state: "open", customerId: query.data?.customer_id, limit: 100 },
    canRead && canApply && canReadInvoices && Boolean(query.data?.customer_id),
  );

  if (!canRead) return <Alert variant="danger">You are not authorized to view this Payment.</Alert>;
  if (query.isPending) return <Spinner label="Loading payment" />;
  if (!query.data || query.isError) return <Alert variant="danger">Payment could not be loaded.</Alert>;

  const receipt = query.data;
  const mutationError = mutations.apply.error ?? mutations.refund.error;
  const safeMutationError = mutationError ? getOperatorApiError(mutationError, "Payment") : null;
  const applySubmit = (event: FormEvent) => {
    event.preventDefault();
    const invoice = openInvoices.data?.find((item) => item.id === apply.invoice);
    if (!invoice) return;
    mutations.apply.mutate({ id: receipt.id, input: { branch_id: receipt.branch_id, invoice_id: invoice.id, amount: apply.amount, expected_invoice_version: invoice.version, idempotency_key: crypto.randomUUID(), occurred_at: new Date().toISOString() } });
  };
  const refundSubmit = (event: FormEvent) => {
    event.preventDefault();
    mutations.refund.mutate({ id: receipt.id, input: { branch_id: receipt.branch_id, amount: refund.amount, reason: refund.reason, expected_version: receipt.version, idempotency_key: crypto.randomUUID() } });
  };

  return <div className="mx-auto max-w-4xl space-y-6 pb-12">
    <Link className="inline-flex min-h-11 items-center font-semibold text-action-primary hover:underline" to={`/customers/${receipt.customer_id}`}>Back to Customer</Link>
    <ReceiptSummary receipt={receipt}/>
    {safeMutationError && <Alert variant="danger">{safeMutationError.message} Refresh both the receipt and Invoice before retrying; prior evidence was not rewritten.</Alert>}
    {canApply && <Card><CardHeader><CardTitle>Apply receipt to an Invoice</CardTitle></CardHeader><CardContent><p className="mb-4 text-sm text-content-muted">Choose this Customer&apos;s open Invoice. The current Invoice version is handled automatically.</p>{!canReadInvoices && <Alert variant="warning">Invoice read access is required to choose where this receipt belongs.</Alert>}{openInvoices.isError && <Alert variant="warning">Open Invoices could not be loaded. Refresh before applying this receipt.</Alert>}{openInvoices.isSuccess && openInvoices.data.length === 0 && <p className="mb-4 text-sm text-content-muted">No open Invoices are available for this Customer.</p>}<form className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(10rem,auto)_auto]" onSubmit={(event) => void applySubmit(event)}><label className="grid gap-1 text-sm"><span>Invoice</span><select aria-label="Payment Invoice" required className="min-h-11 rounded-lg border border-stroke bg-surface px-3" value={apply.invoice} onChange={(event)=>setApply({...apply,invoice:event.target.value})} disabled={!canReadInvoices || openInvoices.isPending || !openInvoices.data?.length}><option value="">Select open Invoice</option>{openInvoices.data?.map((invoice) => <option key={invoice.id} value={invoice.id}>{invoice.invoice_number} · {invoice.customer_display_name} · {invoice.currency} {invoice.open_amount} due</option>)}</select></label><Input aria-label="Application amount" required type="number" min="0.01" step="0.01" value={apply.amount} onChange={(event)=>setApply({...apply,amount:event.target.value})}/><Button type="submit" loading={mutations.apply.isPending} disabled={!canReadInvoices || !apply.invoice || !apply.amount || openInvoices.isError}>Apply receipt</Button></form></CardContent></Card>}
    {canRefund && <Card><CardHeader><CardTitle>Refund unapplied funds</CardTitle></CardHeader><CardContent><form className="grid gap-3 sm:grid-cols-2" onSubmit={(event)=>void refundSubmit(event)}><Input aria-label="Refund amount" required type="number" step="0.01" value={refund.amount} onChange={(event)=>setRefund({...refund,amount:event.target.value})}/><Input aria-label="Refund reason" required value={refund.reason} onChange={(event)=>setRefund({...refund,reason:event.target.value})}/><Button type="submit" loading={mutations.refund.isPending}>Request refund</Button></form></CardContent></Card>}
  </div>;
}
