import { ArrowLeft } from "lucide-react";
import { Link, useLocation, useParams } from "react-router";

import { useFinancial, usePayment } from "../hooks/useFinancials";

const money = (amount: string, currency: string) =>
  new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(amount));

export function FinancialDetailRoute() {
  const location = useLocation();
  const { financialId } = useParams();
  const payments = location.pathname.startsWith("/payments");
  const kind = location.pathname.startsWith("/estimates") ? "estimates" : "invoices";
  const document = useFinancial(kind, payments ? undefined : financialId);
  const payment = usePayment(payments ? financialId : undefined);
  const query = payments ? payment : document;
  if (query.isLoading) return <p className="text-content-muted">Loading financial detail…</p>;
  if (query.isError || !query.data) return <p className="text-status-danger">Unable to load financial detail.</p>;
  if (payments && "invoice_id" in query.data) {
    const item = query.data;
    return <div className="min-w-0 space-y-6"><Link className="inline-flex min-h-11 items-center gap-2 text-action-primary" to="/payments"><ArrowLeft size={16} />Back to Payments</Link><header><p className="text-sm text-content-muted">Historical payment</p><h2 className="break-all text-2xl font-bold sm:text-3xl">{money(item.amount, item.currency)}</h2></header><dl className="grid min-w-0 gap-4 rounded-xl border border-stroke bg-surface p-ui-5 sm:grid-cols-2"><div><dt className="text-sm text-content-muted">Status</dt><dd>{item.status}</dd></div><div><dt className="text-sm text-content-muted">Method</dt><dd>{item.method ?? "Unavailable"}</dd></div><div><dt className="text-sm text-content-muted">Paid</dt><dd>{item.paid_at ? new Date(item.paid_at).toLocaleString() : "Unavailable"}</dd></div><div className="min-w-0"><dt className="text-sm text-content-muted">Invoice</dt><dd className="break-all">{item.invoice_id}</dd></div></dl></div>;
  }
  if (!("number" in query.data)) return null;
  const item = query.data;
  return <div className="min-w-0 space-y-6"><Link className="inline-flex min-h-11 items-center gap-2 text-action-primary" to={`/${kind}`}><ArrowLeft size={16} />Back to {kind === "estimates" ? "Estimates" : "Invoices"}</Link><header><p className="text-sm text-content-muted">{kind === "estimates" ? "Estimate" : "Invoice"}</p><h2 className="break-all text-2xl font-bold sm:text-3xl">{item.number}</h2><p className="mt-2 break-words text-content-muted">{item.customer_display_name} · {item.job_number}</p></header><dl className="grid gap-4 rounded-xl border border-stroke bg-surface p-ui-5 sm:grid-cols-3"><div><dt className="text-sm text-content-muted">Status</dt><dd>{item.status}</dd></div><div><dt className="text-sm text-content-muted">Subtotal</dt><dd>{money(item.subtotal_amount, item.currency)}</dd></div><div><dt className="text-sm text-content-muted">Tax</dt><dd>{money(item.tax_amount, item.currency)}</dd></div><div><dt className="text-sm text-content-muted">Total</dt><dd className="font-semibold">{money(item.total_amount, item.currency)}</dd></div></dl><section className="overflow-hidden rounded-xl border border-stroke bg-surface"><h3 className="p-ui-4 text-lg font-semibold">Line items</h3><div className="divide-y divide-stroke">{item.line_items.map((line) => <div key={line.id} className="grid min-w-0 gap-1 p-ui-4 sm:grid-cols-[1fr_auto]"><span className="break-words">{line.description}</span><span>{money(line.total_amount, item.currency)}</span><span className="text-sm text-content-muted">Quantity {line.quantity} · Unit {money(line.unit_price, item.currency)}</span></div>)}</div></section>{item.payments.length > 0 && <section className="overflow-hidden rounded-xl border border-stroke bg-surface"><h3 className="p-ui-4 text-lg font-semibold">Payments</h3><div className="divide-y divide-stroke">{item.payments.map((value) => <Link key={value.id} className="grid gap-1 p-ui-4 sm:grid-cols-[1fr_auto]" to={`/payments/${value.id}`}><span>{value.method ?? "Payment"}</span><span>{money(value.amount, value.currency)}</span></Link>)}</div></section>}</div>;
}
