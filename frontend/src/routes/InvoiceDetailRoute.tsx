import { useState } from "react";
import { Link, useParams } from "react-router";
import { useHasPermission } from "../auth";
import { InvoiceSummary } from "../components/invoices/InvoiceSummary";
import { useInvoice, useInvoiceMutations } from "../hooks/useInvoices";
import { Alert, Button, Card, CardContent, CardHeader, CardTitle, Input, Spinner } from "../ui";

export function InvoiceDetailRoute() {
  const { invoiceId = "" } = useParams();
  const canRead = useHasPermission("COMPANY_INVOICE_READ");
  const invoice = useInvoice(invoiceId, canRead);
  const canIssue = useHasPermission("COMPANY_INVOICE_ISSUE");
  const canAdjust = useHasPermission("COMPANY_INVOICE_ADJUST");
  const mutations = useInvoiceMutations();
  const [adjustment, setAdjustment] = useState({ amount: "", reason: "" });
  const mutationError = mutations.issue.error ?? mutations.credit.error ?? mutations.writeOff.error ?? mutations.void.error;
  if (!canRead)
    return <Alert variant="danger">You are not authorized to view this Invoice.</Alert>;
  if (invoice.isPending) return <Spinner label="Loading Invoice" />;
  if (invoice.isError || !invoice.data)
    return <Alert variant="danger">Invoice could not be loaded.</Alert>;
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <InvoiceSummary invoice={invoice.data} />
      <Link
        className="inline-flex min-h-11 items-center justify-center rounded-md bg-action-secondary px-ui-4 text-sm font-semibold text-content hover:brightness-110"
        to={`/lia?contextDomain=invoicing&contextId=${encodeURIComponent(invoice.data.id)}`}
      >
        Ask LIA about this Invoice
      </Link>
      {mutationError && <Alert variant="danger">The Invoice could not be updated. Refresh and verify its current state before retrying.</Alert>}
      {invoice.data.status === "draft" && canIssue && (
        <Button
          loading={mutations.issue.isPending}
          onClick={() =>
            void mutations.issue.mutateAsync({
              id: invoice.data.id,
              input: {
                branch_id: invoice.data.branch_id,
                expected_version: invoice.data.version,
                idempotency_key: crypto.randomUUID(),
                occurred_at: new Date().toISOString(),
              },
            })
          }
        >
          Issue Invoice
        </Button>
      )}
      {canAdjust && !["paid", "voided", "cancelled"].includes(invoice.data.status) && (
        <Card><CardHeader><CardTitle>Governed adjustment</CardTitle></CardHeader><CardContent className="space-y-3">
          <p className="text-sm text-content-muted">Credits and write-offs append AR evidence; they never rewrite the issued Invoice.</p>
          <div className="grid gap-3 sm:grid-cols-2"><Input aria-label="Adjustment amount" type="number" min="0.01" step="0.01" value={adjustment.amount} onChange={(event) => setAdjustment({...adjustment, amount: event.target.value})}/><Input aria-label="Adjustment reason" value={adjustment.reason} onChange={(event) => setAdjustment({...adjustment, reason: event.target.value})}/></div>
          <div className="flex flex-wrap gap-2"><Button disabled={!adjustment.amount || !adjustment.reason || mutations.credit.isPending} onClick={() => void mutations.credit.mutateAsync({id: invoice.data.id, input: {branch_id: invoice.data.branch_id, expected_version: invoice.data.version, idempotency_key: crypto.randomUUID(), occurred_at: new Date().toISOString(), amount: adjustment.amount, reason_code: adjustment.reason}})}>Apply credit</Button><Button variant="secondary" disabled={!adjustment.amount || !adjustment.reason || mutations.writeOff.isPending} onClick={() => void mutations.writeOff.mutateAsync({id: invoice.data.id, input: {branch_id: invoice.data.branch_id, expected_version: invoice.data.version, idempotency_key: crypto.randomUUID(), occurred_at: new Date().toISOString(), amount: adjustment.amount, reason_code: adjustment.reason}})}>Record write-off</Button></div>
        </CardContent></Card>
      )}
    </div>
  );
}
