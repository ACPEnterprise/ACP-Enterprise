import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { useHasPermission } from "../auth";
import { useInvoiceMutations, useInvoiceWorkspace } from "../hooks/useInvoices";
import type { InvoiceWorkspaceState } from "../types/invoices";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Spinner,
} from "../ui";

export function InvoicesRoute() {
  const canRead = useHasPermission("COMPANY_INVOICE_READ");
  const canManage = useHasPermission("COMPANY_INVOICE_MANAGE");
  const today = new Date().toISOString().slice(0, 10);
  const mutations = useInvoiceMutations();
  const [form, setForm] = useState({
    branch: "",
    estimate: "",
    job: "",
    due: "",
    terms: "Net 30",
  });
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<InvoiceWorkspaceState>("open");
  const invoices = useInvoiceWorkspace({ asOf: today, state: statusFilter, query: query.trim() || undefined }, canRead);
  if (!canRead)
    return (
      <Alert variant="danger">You are not authorized to view Invoices.</Alert>
    );
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await mutations.create.mutateAsync({
      branch_id: form.branch,
      estimate_id: form.estimate,
      job_id: form.job,
      due_date: form.due,
      terms: form.terms,
      idempotency_key: crypto.randomUUID(),
    });
  };
  const rows = invoices.data ?? [];
  const openTotal = rows.reduce((sum, invoice) => sum + Number(invoice.open_amount), 0);
  return (
    <div className="mx-auto max-w-5xl space-y-6 pb-12">
      <header>
        <p className="text-sm font-semibold text-action-primary">
          Financial Operations
        </p>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">
          Invoices and receivables
        </h1>
        <p className="mt-2 text-content-muted">
          Authoritative customer obligations from completed accepted work.
        </p>
      </header>
      {invoices.isPending ? (
        <Spinner label="Loading Invoices" />
      ) : invoices.isError ? (
        <Alert variant="danger">Invoices could not be loaded.</Alert>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Open items</CardTitle>
            <CardDescription>{rows.length} invoices · {openTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} open across the filtered set. Invoice value is not recognized revenue.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="mb-4 grid gap-3 sm:grid-cols-2">
              <Input aria-label="Search invoices" placeholder="Customer, Invoice, or Job" value={query} onChange={(event) => setQuery(event.target.value)} />
              <label className="grid gap-1 text-sm"><span>View</span><select aria-label="Invoice status" className="rounded-lg border border-stroke bg-surface px-3 py-2" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as InvoiceWorkspaceState)}><option value="open">Open balance</option><option value="overdue">Overdue</option><option value="needs_attention">Needs attention</option><option value="all">All</option><option value="draft">Draft</option><option value="issued">Issued</option><option value="partially_paid">Partial</option><option value="paid">Paid</option><option value="adjusted">Adjusted</option><option value="voided">Voided</option></select></label>
            </div>
            <ul className="space-y-2">
              {rows.map((invoice) => (
                <li key={invoice.id}>
                  <Link
                    className="grid gap-2 rounded-lg border border-stroke p-3 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto] sm:items-center"
                    to={`/invoices/${invoice.id}`}
                  >
                    <span><strong>{invoice.invoice_number}</strong><span className="block truncate text-sm text-content-muted">{invoice.customer_display_name} · {invoice.customer_number}</span></span>
                    <span className="text-sm"><span className="block">{invoice.job_number}</span><span className="block truncate text-content-muted">{invoice.service_location_label}</span></span>
                    <span className="text-left sm:text-right"><strong>{Number(invoice.open_amount).toLocaleString(undefined, { style: "currency", currency: invoice.currency })}</strong><span className="block text-xs text-content-muted">{invoice.status.replaceAll("_", " ")} · due {invoice.due_date}{invoice.age_days > 0 ? ` · ${invoice.age_days}d overdue` : ""}</span>{invoice.attention_reasons.length > 0 && <span className="block text-xs font-semibold text-status-warning">{invoice.attention_reasons.map((reason) => reason.replaceAll("_", " ").toLowerCase()).join(" · ")}</span>}</span>
                  </Link>
                </li>
              ))}
              {rows.length === 0 && <li className="text-sm text-content-muted">No invoices match these filters.</li>}
            </ul>
          </CardContent>
        </Card>
      )}
      {canManage && (
        <Card>
          <CardHeader>
            <CardTitle>Create from accepted work</CardTitle>
            <CardDescription>
              The API verifies accepted Estimate and completed Job authority.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-3 sm:grid-cols-2"
              onSubmit={(event) => void submit(event)}
            >
              <Input
                aria-label="Branch ID"
                required
                value={form.branch}
                onChange={(event) =>
                  setForm({ ...form, branch: event.target.value })
                }
              />
              <Input
                aria-label="Estimate ID"
                required
                value={form.estimate}
                onChange={(event) =>
                  setForm({ ...form, estimate: event.target.value })
                }
              />
              <Input
                aria-label="Job ID"
                required
                value={form.job}
                onChange={(event) =>
                  setForm({ ...form, job: event.target.value })
                }
              />
              <Input
                aria-label="Due date"
                type="date"
                required
                value={form.due}
                onChange={(event) =>
                  setForm({ ...form, due: event.target.value })
                }
              />
              <Input
                aria-label="Terms"
                required
                value={form.terms}
                onChange={(event) =>
                  setForm({ ...form, terms: event.target.value })
                }
              />
              <Button type="submit" loading={mutations.create.isPending}>
                Create draft Invoice
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
