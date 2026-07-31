import { useState, type FormEvent } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { Link, useLocation } from "react-router";

import { useFinancials, usePayments } from "../hooks/useFinancials";
import { Button, Input } from "../ui";

const money = (amount: string, currency: string) =>
  new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(amount));

export function FinancialListRoute() {
  const location = useLocation();
  const kind = location.pathname.startsWith("/estimates") ? "estimates" : "invoices";
  const payments = location.pathname.startsWith("/payments");
  const [input, setInput] = useState("");
  const [searchText, setSearchText] = useState("");
  const [page, setPage] = useState(1);
  const documents = useFinancials(kind, { searchText, page, pageSize: 20 });
  const paymentQuery = usePayments({ searchText, page, pageSize: 20 });
  const query = payments ? paymentQuery : documents;
  const title = payments ? "Payments" : kind === "estimates" ? "Estimates" : "Invoices";
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setPage(1);
    setSearchText(input.trim());
  };
  return (
    <div className="min-w-0 space-y-6">
      <header>
        <p className="text-sm font-medium text-action-primary">Financial history</p>
        <h2 className="mt-1 text-2xl font-bold sm:text-3xl">{title}</h2>
        <nav className="mt-3 flex flex-wrap gap-4 text-sm">
          <Link className="text-action-primary" to="/estimates">Estimates</Link>
          <Link className="text-action-primary" to="/invoices">Invoices</Link>
          <Link className="text-action-primary" to="/payments">Payments</Link>
        </nav>
      </header>
      <form onSubmit={submit} className="flex flex-col gap-3 rounded-xl border border-stroke bg-surface p-ui-4 sm:flex-row">
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">Search {title}</span>
          <Search className="absolute left-3 top-3 text-content-muted" size={18} />
          <Input className="pl-10" value={input} onChange={(event) => setInput(event.target.value)} placeholder={`Search ${title.toLowerCase()}`} />
        </label>
        <Button type="submit">Search</Button>
      </form>
      <section className="overflow-hidden rounded-xl border border-stroke bg-surface">
        {query.isLoading && <p className="p-ui-5 text-content-muted">Loading {title.toLowerCase()}…</p>}
        {query.isError && <p className="p-ui-5 text-status-danger">Unable to load {title.toLowerCase()}.</p>}
        {query.data?.items.length === 0 && <p className="p-ui-5 text-content-muted">No {title.toLowerCase()} are available.</p>}
        {query.data && query.data.items.length > 0 && (
          <div className="divide-y divide-stroke">
            {query.data.items.map((item) => {
              if (payments && "invoice_id" in item) {
                return <Link key={item.id} to={`/payments/${item.id}`} className="grid min-w-0 gap-1 p-ui-4 hover:bg-surface-subtle sm:grid-cols-[1fr_auto]"><span className="min-w-0 break-words font-medium">{item.method ?? "Payment"}</span><span>{money(item.amount, item.currency)}</span><span className="text-sm text-content-muted">{item.status} · {item.paid_at ? new Date(item.paid_at).toLocaleString() : "Date unavailable"}</span></Link>;
              }
              if (!("number" in item)) return null;
              return <Link key={item.id} to={`/${kind}/${item.id}`} className="grid min-w-0 gap-1 p-ui-4 hover:bg-surface-subtle sm:grid-cols-[1fr_auto]"><span className="min-w-0 break-all font-medium">{item.number}</span><span>{money(item.total_amount, item.currency)}</span><span className="min-w-0 break-words text-sm text-content-muted">{item.customer_display_name} · {item.job_number} · {item.status}</span></Link>;
            })}
          </div>
        )}
        {query.data && query.data.total_pages > 0 && <footer className="flex flex-col gap-3 border-t border-stroke p-ui-4 text-sm text-content-muted sm:flex-row sm:items-center sm:justify-between"><span>Page {query.data.page} of {query.data.total_pages} · {query.data.total_count} {title}</span><div className="flex gap-2"><Button variant="outline" aria-label="Previous page" disabled={page === 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={17} /></Button><Button variant="outline" aria-label="Next page" disabled={page >= query.data.total_pages} onClick={() => setPage((value) => value + 1)}><ChevronRight size={17} /></Button></div></footer>}
      </section>
    </div>
  );
}
