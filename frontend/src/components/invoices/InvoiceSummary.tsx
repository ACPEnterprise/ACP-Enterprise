import type { Invoice } from "../../types/invoices";
import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../../ui";

const money = (value: string, currency: string) =>
  new Intl.NumberFormat(undefined, { style: "currency", currency }).format(
    Number(value),
  );

export function InvoiceSummary({ invoice }: { invoice: Invoice }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>{invoice.invoice_number}</CardTitle>
          <Badge variant="neutral">{invoice.status}</Badge>
        </div>
        <CardDescription>
          Due {invoice.due_date} · Accounting {invoice.accounting_status}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-2 text-right">
          <dt>Subtotal</dt>
          <dd>{money(invoice.subtotal_amount, invoice.currency)}</dd>
          <dt>Discount</dt>
          <dd>−{money(invoice.discount_amount, invoice.currency)}</dd>
          <dt>Tax</dt>
          <dd>{money(invoice.tax_amount, invoice.currency)}</dd>
          <dt className="font-bold">Open receivable</dt>
          <dd className="font-bold">
            {money(invoice.open_amount, invoice.currency)}
          </dd>
        </dl>
        {invoice.legacy_evidence_missing && (
          <p className="mt-4 text-sm text-status-warning">
            Legacy evidence requires reconciliation; missing facts are not
            treated as zero.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
