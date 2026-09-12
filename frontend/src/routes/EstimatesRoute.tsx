import { useState, type FormEvent } from "react";
import axios from "axios";
import { useSearchParams } from "react-router";
import { useAuth, useHasPermission } from "../auth";
import { useEstimate, useEstimateMutations, useEstimates } from "../hooks/useEstimates";
import { useCustomerList } from "../hooks/useCustomers";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Select, Spinner } from "../ui";
import { EstimateDecisionControls } from "../components/estimates/EstimateDecisionControls";
import { EstimatePriceBookPicker } from "../components/estimates/EstimatePriceBookPicker";
import type { EffectivePriceBookItem } from "../types/priceBook";

function money(value: string, currency = "USD") {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(value));
}

function estimateRecoveryMessage(error: unknown) {
  if (axios.isAxiosError(error)) {
    const recovery = (error.response?.data as { detail?: { recovery?: string } })?.detail?.recovery;
    if (recovery === "RETRY_AFTER_REFRESH") return "Estimate authority changed. Refresh before continuing.";
    if (recovery === "USER_CORRECTION_REQUIRED") return "Estimate evidence requires correction. Review the retained proposal inputs.";
    if (recovery === "OWNER_ADMIN_ACTION_REQUIRED") return "The Estimate requires owner or administrator action before continuing.";
    if (recovery === "TEMPORARILY_UNAVAILABLE") return "Estimates are temporarily unavailable. Your proposal inputs were retained.";
  }
  return "The Estimate was not created. Review authoritative state before retrying.";
}

export function EstimatesRoute() {
  const { activeCompany } = useAuth();
  const [params, setParams] = useSearchParams();
  const canRead = useHasPermission("COMPANY_ESTIMATE_READ");
  const canManage = useHasPermission("COMPANY_ESTIMATE_MANAGE");
  const canSelectPriceBook = useHasPermission("COMPANY_PRICE_BOOK_READ");
  const id = params.get("id") ?? "";
  const estimate = useEstimate(id, canRead && Boolean(id));
  const mutations = useEstimateMutations();
  const [statusFilter, setStatusFilter] = useState("");
  const estimates = useEstimates(statusFilter || undefined, undefined, canRead);
  const [lookup, setLookup] = useState(id);
  const defaultBranch = activeCompany?.default_branch_id ?? activeCompany?.branches[0]?.id ?? "";
  const [form, setForm] = useState({ branch: defaultBranch, customer: "", customerName: "", customerSearch: "", title: "", discountType: "", discountValue: "", effectiveAt: new Date().toISOString().slice(0, 16) });
  const [lines, setLines] = useState<Array<{ snapshotId: string; title: string; description: string; quantity: string; total: string; currency: string }>>([]);
  const customers = useCustomerList(form.customerSearch, 8, 0, canManage && Boolean(form.customerSearch));

  if (!canRead) return <Alert variant="danger">You are not authorized to view Estimates.</Alert>;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const created = await mutations.create.mutateAsync({
        branch_id: form.branch,
        customer_id: form.customer,
        proposal_title: form.title,
        lines: lines.map((line) => ({ snapshot_id: line.snapshotId, title: line.title, description: line.description })),
        discount_type: form.discountType ? form.discountType as "fixed" | "percentage" : undefined,
        discount_value: form.discountValue || undefined,
      });
      setParams({ id: created.id });
    } catch {
      // React Query retains the governed error; proposal evidence remains editable.
    }
  };
  const addPriceBookItem = async (item: EffectivePriceBookItem, quantity: string, option?: { groupId: string; optionId: string }) => {
    const snapshot = await mutations.snapshotPriceBookItem.mutateAsync({
      itemId: item.item_id,
      input: {
        branch_id: form.branch,
        quantity,
        currency: item.currency,
        effective_at: new Date(form.effectiveAt).toISOString(),
        idempotency_key: `estimate-picker:${crypto.randomUUID()}`,
        option_group_id: option?.groupId,
        option_id: option?.optionId,
      },
    });
    setLines((current) => [...current, { snapshotId: snapshot.id, title: item.item_name, description: item.customer_description, quantity: snapshot.quantity, total: snapshot.extended_amount, currency: snapshot.currency }]);
  };
  return <div className="mx-auto max-w-5xl space-y-6 pb-12">
    <header><p className="text-sm font-semibold text-action-primary">Sales / Commercial Operations</p><h1 className="mt-1 text-2xl font-bold sm:text-3xl">Estimates</h1><p className="mt-2 text-content-muted">Customer-ready proposals backed by immutable Price Book evidence.</p></header>
    <Card><CardHeader><div className="flex flex-wrap items-end justify-between gap-3"><div><CardTitle>Estimate pipeline</CardTitle><CardDescription>Select authoritative proposal evidence without copying an identifier.</CardDescription></div><Select aria-label="Estimate status filter" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">All states</option><option value="draft">Draft</option><option value="sent">Sent</option><option value="viewed">Viewed</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="expired">Expired</option></Select></div></CardHeader><CardContent>{estimates.isPending ? <Spinner label="Loading Estimate pipeline" /> : estimates.isError ? <Alert variant="danger">Estimate pipeline could not be loaded.</Alert> : estimates.data?.items.length ? <div className="overflow-x-auto"><table className="w-full min-w-[44rem] text-left text-sm"><thead className="text-content-muted"><tr><th className="pb-3">Estimate</th><th className="pb-3">Proposal</th><th className="pb-3">State</th><th className="pb-3 text-right">Total</th><th className="pb-3"><span className="sr-only">Open</span></th></tr></thead><tbody>{estimates.data.items.map((item) => <tr key={item.id} className="border-t border-stroke"><td className="py-3 font-medium">{item.estimate_number}</td><td className="py-3">{item.proposal_title}</td><td className="py-3"><Badge variant="neutral">{item.status}</Badge></td><td className="py-3 text-right">{money(item.total_amount, item.currency)}</td><td className="py-3 text-right"><Button type="button" variant="ghost" onClick={() => { setLookup(item.id); setParams({ id: item.id }); }}>Open</Button></td></tr>)}</tbody></table></div> : <p className="rounded-lg border border-dashed border-stroke p-5 text-sm text-content-muted">No Estimates match this queue.</p>}</CardContent></Card>
    <Card><CardHeader><CardTitle>Open by identity</CardTitle><CardDescription>Use this recovery path when an Estimate is not in the current queue.</CardDescription></CardHeader><CardContent><form className="flex flex-col gap-3 sm:flex-row" onSubmit={(event) => { event.preventDefault(); setParams({ id: lookup }); }}><Input aria-label="Estimate ID" value={lookup} onChange={(event) => setLookup(event.target.value)} required /><Button type="submit">Open</Button></form></CardContent></Card>
    {id && (estimate.isPending ? <Spinner label="Loading Estimate" /> : estimate.isError ? <Alert variant="danger">Estimate could not be loaded.</Alert> : estimate.data && <Card><CardHeader><div className="flex flex-wrap items-center justify-between gap-2"><CardTitle>{estimate.data.current_revision.proposal_title}</CardTitle><Badge variant="neutral">{estimate.data.status}</Badge></div><CardDescription>{estimate.data.estimate_number} · Revision {estimate.data.current_revision.revision_number}</CardDescription></CardHeader><CardContent className="space-y-5"><ul className="space-y-3">{estimate.data.current_revision.lines.map((line) => <li key={line.id} className="rounded-lg border border-stroke p-4"><div className="flex justify-between gap-4"><div><strong>{line.title}</strong>{line.description && <p className="text-sm text-content-muted">{line.description}</p>}{line.option_id && <p className="text-xs text-content-muted">Selected customer option</p>}</div><span>{money(line.line_total, line.currency)}</span></div></li>)}</ul><dl className="ml-auto grid max-w-sm grid-cols-2 gap-2 text-right"><dt>Subtotal</dt><dd>{money(estimate.data.current_revision.subtotal_amount)}</dd><dt>Discount</dt><dd>−{money(estimate.data.current_revision.discount_amount)}</dd><dt>Tax</dt><dd>{money(estimate.data.current_revision.tax_amount)}</dd><dt className="font-bold">Total</dt><dd className="font-bold">{money(estimate.data.current_revision.total_amount)}</dd></dl>{canManage && <EstimateDecisionControls estimate={estimate.data} mutations={mutations} />}</CardContent></Card>)}
    {canManage && <Card><CardHeader><CardTitle>Create proposal</CardTitle><CardDescription>Choose a Customer and effective Price Book services. Pricing evidence is frozen when each service is added.</CardDescription></CardHeader><CardContent className="space-y-4">{!canSelectPriceBook && <Alert variant="danger">Price Book read access is required to select governed Estimate services.</Alert>}{mutations.create.isError && <Alert variant="danger" role="alert" aria-live="assertive">{estimateRecoveryMessage(mutations.create.error)}</Alert>}{mutations.snapshotPriceBookItem.isError && <Alert variant="danger" role="alert" aria-live="assertive">The selected service was not added. Refresh the effective Price Book and try again.</Alert>}<form className="grid gap-3 sm:grid-cols-2" onSubmit={(event) => void submit(event)}><Select aria-label="Estimate Branch" value={form.branch} onChange={(event) => { setForm({ ...form, branch: event.target.value }); setLines([]); }} required><option value="">Select Branch</option>{activeCompany?.branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</Select><Input aria-label="Price effective date" type="datetime-local" value={form.effectiveAt} onChange={(event) => { setForm({ ...form, effectiveAt: event.target.value }); setLines([]); }} required /><div className="space-y-2 sm:col-span-2"><Input aria-label="Find Customer" placeholder="Search Customer name, phone, or email" value={form.customerSearch} onChange={(event) => setForm({ ...form, customerSearch: event.target.value, customer: "", customerName: "" })} />{form.customer ? <div className="flex items-center justify-between rounded-lg border border-stroke p-3"><span><strong>{form.customerName}</strong><span className="ml-2 text-xs text-content-muted">Selected Customer</span></span><Button type="button" variant="ghost" onClick={() => setForm({ ...form, customer: "", customerName: "", customerSearch: "" })}>Change</Button></div> : form.customerSearch && <div className="grid gap-2">{customers.data?.items.map((customer) => <Button key={customer.id} type="button" variant="outline" onClick={() => setForm({ ...form, customer: customer.id, customerName: customer.display_name || customer.business_name || customer.customer_number || "Customer", customerSearch: customer.display_name || customer.business_name || "Selected Customer" })}>{customer.display_name || customer.business_name || customer.customer_number || "Customer"}</Button>)}</div>}</div><Input aria-label="Proposal title" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required /><div />{canSelectPriceBook && <EstimatePriceBookPicker branchId={form.branch} effectiveAt={form.effectiveAt ? new Date(form.effectiveAt).toISOString() : ""} onAdd={addPriceBookItem} pending={mutations.snapshotPriceBookItem.isPending} />}{lines.length > 0 && <div className="space-y-2 sm:col-span-2"><p className="font-semibold">Estimate services</p>{lines.map((line, index) => <div key={line.snapshotId} className="flex items-center justify-between gap-3 rounded-lg border border-stroke p-3"><div><strong>{line.title}</strong><p className="text-xs text-content-muted">{line.quantity} × frozen Price Book service</p></div><div className="flex items-center gap-3"><span>{money(line.total, line.currency)}</span><Button type="button" variant="ghost" onClick={() => setLines((current) => current.filter((_, candidate) => candidate !== index))}>Remove</Button></div></div>)}</div>}<Select aria-label="Discount type" value={form.discountType} onChange={(event) => setForm({ ...form, discountType: event.target.value })}><option value="">No discount</option><option value="fixed">Fixed amount</option><option value="percentage">Percentage</option></Select><Input aria-label="Discount value" type="number" min="0" step="0.01" disabled={!form.discountType} value={form.discountValue} onChange={(event) => setForm({ ...form, discountValue: event.target.value })} /><Button fullWidth type="submit" loading={mutations.create.isPending} disabled={!form.customer || lines.length === 0}>Create immutable revision</Button></form></CardContent></Card>}
  </div>;
}
