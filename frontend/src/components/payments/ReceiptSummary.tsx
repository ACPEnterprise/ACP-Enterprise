import type { PaymentReceipt } from "../../types/payments";
import { Card, CardContent, CardHeader, CardTitle } from "../../ui";

export function ReceiptSummary({ receipt }: { receipt: PaymentReceipt }) {
  return <Card><CardHeader><CardTitle>Receipt {receipt.id.slice(0, 8)}</CardTitle></CardHeader><CardContent>
    <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
      <div><dt className="text-content-muted">Provider-captured evidence</dt><dd>{receipt.captured_amount} {receipt.currency}</dd></div>
      <div><dt className="text-content-muted">Available</dt><dd>{receipt.available_amount}</dd></div>
      <div><dt className="text-content-muted">Applied</dt><dd>{receipt.applied_amount}</dd></div>
      <div><dt className="text-content-muted">Status</dt><dd>{receipt.status}</dd></div>
    </dl>
    <p className="mt-4 text-xs text-content-muted">This receipt does not by itself prove settlement, deposit, or bank cash.</p>
  </CardContent></Card>;
}
