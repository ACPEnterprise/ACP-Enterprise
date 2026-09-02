import { useState } from "react";
import { Link, useParams } from "react-router";
import { useHasPermission } from "../auth";
import { InvoiceSummary } from "../components/invoices/InvoiceSummary";
import { useCustomerBalance, useInvoice, useInvoiceMutations, useInvoiceOfficeDetail } from "../hooks/useInvoices";
import { Alert, Button, Card, CardContent, CardHeader, CardTitle, Input, Spinner } from "../ui";

export function InvoiceDetailRoute() {
  const { invoiceId = "" } = useParams();
  const canRead = useHasPermission("COMPANY_INVOICE_READ");
  const invoice = useInvoice(invoiceId, canRead);
  const today = new Date().toISOString().slice(0, 10);
  const officeDetail = useInvoiceOfficeDetail(invoiceId, today, canRead);
  const customerBalance = useCustomerBalance(officeDetail.data?.customer_id ?? "", today, canRead && Boolean(officeDetail.data));
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
      {officeDetail.data && <Card><CardHeader><CardTitle>Commercial context</CardTitle></CardHeader><CardContent><dl className="grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-content-muted">Customer</dt><dd><Link className="font-semibold text-action-primary" to={`/customers/${officeDetail.data.customer_id}`}>{officeDetail.data.customer_display_name}</Link> · {officeDetail.data.customer_number}</dd></div><div><dt className="text-content-muted">Service location</dt><dd>{officeDetail.data.service_location_label}</dd></div><div><dt className="text-content-muted">Authorized work</dt><dd><Link className="font-semibold text-action-primary" to={`/jobs/${officeDetail.data.job_id}`}>{officeDetail.data.job_number}</Link>{officeDetail.data.estimate_id ? " · accepted Estimate snapshot retained" : ""}</dd></div><div><dt className="text-content-muted">Terms and due state</dt><dd>{officeDetail.data.terms} · due {officeDetail.data.due_date}{officeDetail.data.age_days > 0 ? ` · ${officeDetail.data.age_days} days overdue` : ""}</dd></div><div><dt className="text-content-muted">Last AR evidence</dt><dd>{officeDetail.data.last_ar_activity_type?.replaceAll("_", " ") ?? "No AR activity recorded"}</dd></div><div><dt className="text-content-muted">Delivery</dt><dd>Not asserted by Invoice authority</dd></div></dl></CardContent></Card>}
      {customerBalance.data && <Card><CardHeader><CardTitle>Customer receivable position</CardTitle></CardHeader><CardContent><dl className="grid gap-3 text-sm sm:grid-cols-3"><div><dt className="text-content-muted">Open balance</dt><dd className="font-bold">{customerBalance.data.open_balance} {customerBalance.data.currency}</dd></div><div><dt className="text-content-muted">Applied Payment evidence</dt><dd>{customerBalance.data.applied_payment_total} {customerBalance.data.currency}</dd></div><div><dt className="text-content-muted">Unapplied receipt evidence</dt><dd>{customerBalance.data.unapplied_receipt_total} {customerBalance.data.currency}</dd></div></dl><p className="mt-3 text-xs text-content-muted">Payment evidence is not bank settlement or cash. This projection includes admitted native ACP authority only.</p></CardContent></Card>}
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
