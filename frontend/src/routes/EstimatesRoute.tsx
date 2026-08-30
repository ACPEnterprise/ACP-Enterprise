import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { useHasPermission } from "../auth";
import { useEstimate, useEstimateMutations, useEstimates } from "../hooks/useEstimates";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Select, Spinner } from "../ui";
import { EstimateDecisionControls } from "../components/estimates/EstimateDecisionControls";
import { getEstimateArtifact } from "../api/estimates";

function money(value: string, currency = "USD") {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(value));
}

export function EstimatesRoute() {
  const [params, setParams] = useSearchParams();
  const canRead = useHasPermission("COMPANY_ESTIMATE_READ");
  const canManage = useHasPermission("COMPANY_ESTIMATE_MANAGE");
  const id = params.get("id") ?? "";
  const estimate = useEstimate(id, canRead && Boolean(id));
  const mutations = useEstimateMutations();
  const [statusFilter, setStatusFilter] = useState("");
  const estimates = useEstimates(statusFilter || undefined);
  const [lookup, setLookup] = useState(id);
  const [form, setForm] = useState({ branch: "", customer: "", snapshot: "", title: "", discountType: "", discountValue: "" });
  const openArtifact = async (estimateId: string) => {
    const artifact = await getEstimateArtifact(estimateId);
    const url = URL.createObjectURL(new Blob([artifact.content], { type: artifact.media_type }));
    window.open(url, "_blank", "noopener,noreferrer");
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  };

  if (!canRead) return <Alert variant="danger">You are not authorized to view Estimates.</Alert>;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const created = await mutations.create.mutateAsync({
      branch_id: form.branch,
      customer_id: form.customer,
      proposal_title: form.title,
      lines: [{ snapshot_id: form.snapshot, title: form.title }],
      discount_type: form.discountType ? form.discountType as "fixed" | "percentage" : undefined,
      discount_value: form.discountValue || undefined,
    });
    setParams({ id: created.id });
  };
  return <div className="mx-auto max-w-5xl space-y-6 pb-12">
    <header><p className="text-sm font-semibold text-action-primary">Sales / Commercial Operations</p><h1 className="mt-1 text-2xl font-bold sm:text-3xl">Estimates</h1><p className="mt-2 text-content-muted">Customer-ready proposals backed by immutable Price Book evidence.</p></header>
    <Card><CardHeader><div className="flex flex-wrap items-end justify-between gap-3"><div><CardTitle>Estimate pipeline</CardTitle><CardDescription>Select authoritative proposal evidence without copying an identifier.</CardDescription></div><Select aria-label="Estimate status filter" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">All states</option><option value="draft">Draft</option><option value="sent">Sent</option><option value="viewed">Viewed</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="expired">Expired</option></Select></div></CardHeader><CardContent>{estimates.isPending ? <Spinner label="Loading Estimate pipeline" /> : estimates.isError ? <Alert variant="danger">Estimate pipeline could not be loaded.</Alert> : estimates.data?.items.length ? <div className="overflow-x-auto"><table className="w-full min-w-[44rem] text-left text-sm"><thead className="text-content-muted"><tr><th className="pb-3">Estimate</th><th className="pb-3">Proposal</th><th className="pb-3">State</th><th className="pb-3 text-right">Total</th><th className="pb-3"><span className="sr-only">Open</span></th></tr></thead><tbody>{estimates.data.items.map((item) => <tr key={item.id} className="border-t border-stroke"><td className="py-3 font-medium">{item.estimate_number}</td><td className="py-3">{item.proposal_title}</td><td className="py-3"><Badge variant="neutral">{item.status}</Badge></td><td className="py-3 text-right">{money(item.total_amount, item.currency)}</td><td className="py-3 text-right"><Button type="button" variant="ghost" onClick={() => { setLookup(item.id); setParams({ id: item.id }); }}>Open</Button></td></tr>)}</tbody></table></div> : <p className="rounded-lg border border-dashed border-stroke p-5 text-sm text-content-muted">No Estimates match this queue.</p>}</CardContent></Card>
    <Card><CardHeader><CardTitle>Open by identity</CardTitle><CardDescription>Use this recovery path when an Estimate is not in the current queue.</CardDescription></CardHeader><CardContent><form className="flex flex-col gap-3 sm:flex-row" onSubmit={(event) => { event.preventDefault(); setParams({ id: lookup }); }}><Input aria-label="Estimate ID" value={lookup} onChange={(event) => setLookup(event.target.value)} required /><Button type="submit">Open</Button></form></CardContent></Card>
    {id && (estimate.isPending ? <Spinner label="Loading Estimate" /> : estimate.isError ? <Alert variant="danger">Estimate could not be loaded.</Alert> : estimate.data && <Card><CardHeader><div className="flex flex-wrap items-center justify-between gap-2"><CardTitle>{estimate.data.current_revision.proposal_title}</CardTitle><div className="flex gap-2"><Badge variant="neutral">{estimate.data.status}</Badge><Button variant="secondary" onClick={() => void openArtifact(estimate.data.id)}>{estimate.data.status === "draft" ? "Preview document" : "Print estimate"}</Button></div></div><CardDescription>{estimate.data.estimate_number} · Revision {estimate.data.current_revision.revision_number}</CardDescription></CardHeader><CardContent className="space-y-5"><ul className="space-y-3">{estimate.data.current_revision.lines.map((line) => <li key={line.id} className="rounded-lg border border-stroke p-4"><div className="flex justify-between gap-4"><div><strong>{line.title}</strong>{line.description && <p className="text-sm text-content-muted">{line.description}</p>}{line.option_id && <p className="text-xs text-content-muted">Selected customer option</p>}</div><span>{money(line.line_total, line.currency)}</span></div></li>)}</ul><dl className="ml-auto grid max-w-sm grid-cols-2 gap-2 text-right"><dt>Subtotal</dt><dd>{money(estimate.data.current_revision.subtotal_amount)}</dd><dt>Discount</dt><dd>−{money(estimate.data.current_revision.discount_amount)}</dd><dt>Tax</dt><dd>{money(estimate.data.current_revision.tax_amount)}</dd><dt className="font-bold">Total</dt><dd className="font-bold">{money(estimate.data.current_revision.total_amount)}</dd></dl>{canManage && <EstimateDecisionControls estimate={estimate.data} mutations={mutations} />}</CardContent></Card>)}
    {canManage && <Card><CardHeader><CardTitle>Create proposal</CardTitle><CardDescription>Select immutable commercial snapshot evidence. Option-group constraints are enforced by the API.</CardDescription></CardHeader><CardContent><form className="grid gap-3 sm:grid-cols-2" onSubmit={(event) => void submit(event)}><Input aria-label="Branch ID" value={form.branch} onChange={(event) => setForm({ ...form, branch: event.target.value })} required /><Input aria-label="Customer ID" value={form.customer} onChange={(event) => setForm({ ...form, customer: event.target.value })} required /><Input aria-label="Commercial snapshot ID" value={form.snapshot} onChange={(event) => setForm({ ...form, snapshot: event.target.value })} required /><Input aria-label="Proposal title" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required /><Select aria-label="Discount type" value={form.discountType} onChange={(event) => setForm({ ...form, discountType: event.target.value })}><option value="">No discount</option><option value="fixed">Fixed amount</option><option value="percentage">Percentage</option></Select><Input aria-label="Discount value" type="number" min="0" step="0.01" disabled={!form.discountType} value={form.discountValue} onChange={(event) => setForm({ ...form, discountValue: event.target.value })} /><Button fullWidth type="submit" loading={mutations.create.isPending}>Create immutable revision</Button></form></CardContent></Card>}
  </div>;
}
