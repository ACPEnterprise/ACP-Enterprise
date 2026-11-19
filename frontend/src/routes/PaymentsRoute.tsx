import { Link } from "react-router";
import { useHasPermission } from "../auth";
import { usePayments } from "../hooks/usePayments";
import { Alert, Card, CardContent, CardDescription, CardHeader, CardTitle, Spinner } from "../ui";
import { humanizeCommercialState } from "../presentation/commercialLabels";

export function PaymentsRoute() {
  const canRead = useHasPermission("COMPANY_PAYMENT_READ");
  const receipts = usePayments(canRead);
  if (!canRead) return <Alert variant="danger">You are not authorized to view Payments.</Alert>;
  return <div className="mx-auto max-w-5xl space-y-6 pb-12"><header><p className="text-sm font-semibold text-action-primary">Financial Operations</p><h1 className="mt-1 text-2xl font-bold sm:text-3xl">Payment evidence</h1><p className="mt-2 text-content-muted">Review office payment records and apply them to an Invoice. A receipt is not bank settlement or cash.</p></header>
    {receipts.isPending ? <Spinner label="Loading payment evidence" /> : receipts.isError ? <Alert variant="danger">Payment evidence could not be loaded.</Alert> : <Card><CardHeader><CardTitle>Payment receipts</CardTitle><CardDescription>Each receipt shows what is available to apply; bank settlement is not inferred.</CardDescription></CardHeader><CardContent><ul className="space-y-2">{receipts.data?.map((receipt) => <li key={receipt.id}><Link className="flex flex-wrap justify-between gap-2 rounded-lg border border-stroke p-3" to={`/payments/${receipt.id}`}><span>Receipt {receipt.id.slice(0, 8)}</span><span>{humanizeCommercialState(receipt.status)} · {receipt.available_amount} {receipt.currency} available to apply</span></Link></li>)}</ul></CardContent></Card>}
    {receipts.isError && receipts.data && <Alert variant="warning">Payment evidence may be stale because refresh failed. Verify current authority before acting.</Alert>}
    <Card><CardHeader><CardTitle>Record payment evidence from an invoice</CardTitle><CardDescription>Use an issued Invoice to record office-observed payment evidence without charging a card, debiting a bank, or sending money to a provider.</CardDescription></CardHeader><CardContent><p className="text-sm text-content-secondary">Open the invoice, choose <strong>Record and apply payment</strong>, and enter the amount, method, and office reference. The invoice balance and customer receivable view update from that evidence.</p><Link className="mt-4 inline-flex min-h-11 items-center rounded-md bg-action-primary px-4 text-sm font-semibold text-content-inverse" to="/invoices">Open invoices</Link></CardContent></Card></div>;
}
