import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { useHasPermission } from "../auth";
import { usePaymentMutations, usePayments } from "../hooks/usePayments";
import { Alert, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Spinner } from "../ui";

export function PaymentsRoute() {
  const canRead = useHasPermission("COMPANY_PAYMENT_READ");
  const canCollect = useHasPermission("COMPANY_PAYMENT_COLLECT");
  const receipts = usePayments(); const mutations = usePaymentMutations();
  const [form, setForm] = useState({ branch: "", customer: "", invoice: "", amount: "", currency: "USD", method: "" });
  if (!canRead) return <Alert variant="danger">You are not authorized to view Payments.</Alert>;
  const submit = async (event: FormEvent) => { event.preventDefault(); await mutations.collect.mutateAsync({ branch_id: form.branch, customer_id: form.customer, invoice_id: form.invoice || undefined, amount: form.amount, currency: form.currency, opaque_payment_method: form.method, idempotency_key: crypto.randomUUID() }); };
  return <div className="mx-auto max-w-5xl space-y-6 pb-12"><header><p className="text-sm font-semibold text-action-primary">Financial Operations</p><h1 className="mt-1 text-2xl font-bold sm:text-3xl">Payments and settlements</h1><p className="mt-2 text-content-muted">Collect, apply, refund, and reconcile verified payment evidence.</p></header>
    {receipts.isPending ? <Spinner label="Loading payments" /> : receipts.isError ? <Alert variant="danger">Payments could not be loaded.</Alert> : <Card><CardHeader><CardTitle>Receipts</CardTitle><CardDescription>Unapplied and applied customer cash.</CardDescription></CardHeader><CardContent><ul className="space-y-2">{receipts.data?.map((receipt) => <li key={receipt.id}><Link className="flex justify-between rounded-lg border border-stroke p-3" to={`/payments/${receipt.id}`}><span>{receipt.id.slice(0, 8)}</span><span>{receipt.status} · {receipt.available_amount} {receipt.currency} available</span></Link></li>)}</ul></CardContent></Card>}
    {canCollect && <Card><CardHeader><CardTitle>Collect a payment</CardTitle><CardDescription>Only provider-safe opaque payment identities are accepted. Live processing remains disabled.</CardDescription></CardHeader><CardContent><form className="grid gap-3 sm:grid-cols-2" onSubmit={(event) => void submit(event)}>
      <Input aria-label="Branch ID" required value={form.branch} onChange={(e) => setForm({...form, branch:e.target.value})}/><Input aria-label="Customer ID" required value={form.customer} onChange={(e) => setForm({...form, customer:e.target.value})}/><Input aria-label="Invoice ID (optional)" value={form.invoice} onChange={(e) => setForm({...form, invoice:e.target.value})}/><Input aria-label="Amount" type="number" min="0.01" step="0.01" required value={form.amount} onChange={(e) => setForm({...form, amount:e.target.value})}/><Input aria-label="Currency" required value={form.currency} onChange={(e) => setForm({...form, currency:e.target.value.toUpperCase()})}/><Input aria-label="Opaque payment method" placeholder="opaque_test_success" required value={form.method} onChange={(e) => setForm({...form, method:e.target.value})}/><Button type="submit" loading={mutations.collect.isPending}>Collect payment</Button>
    </form></CardContent></Card>}</div>;
}
