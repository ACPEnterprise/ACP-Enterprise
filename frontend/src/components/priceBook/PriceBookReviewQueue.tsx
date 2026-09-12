import { useMemo, useState } from "react";

import { usePriceBookMutations, usePriceBookReview } from "../../hooks/usePriceBook";
import type { PriceBookCategory, TaxClassification } from "../../types/priceBook";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Select } from "../../ui";

interface BranchChoice { id: string; name: string }

export function PriceBookReviewQueue({ categories, taxes, branches }: { readonly categories: PriceBookCategory[]; readonly taxes: TaxClassification[]; readonly branches: BranchChoice[] }) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [branch, setBranch] = useState("");
  const [classification, setClassification] = useState("");
  const queue = usePriceBookReview(branch || undefined, category || undefined, classification || undefined, search || undefined);
  const mutations = usePriceBookMutations();
  const [selected, setSelected] = useState<string[]>([]);
  const [bulkCategory, setBulkCategory] = useState("");
  const [bulkBranch, setBulkBranch] = useState("");
  const [bulkTax, setBulkTax] = useState("");
  const [bulkEffective, setBulkEffective] = useState("");
  const rows = useMemo(() => queue.data?.rows ?? [], [queue.data?.rows]);
  const selectedRows = useMemo(() => rows.filter((row) => selected.includes(row.price_version_id)), [rows, selected]);
  const toggle = (id: string) => setSelected((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  const targets = selectedRows.map((row) => ({ service_item_id: row.service_item_id, price_version_id: row.price_version_id, expected_item_version: row.item_version, expected_price_version: row.price_version }));
  const applyBulk = async (individualReview = false) => {
    await mutations.bulkReview.mutateAsync({
      targets,
      category_id: bulkCategory || undefined,
      branch_id: bulkBranch || undefined,
      tax_classification_id: bulkTax || undefined,
      effective_at: bulkEffective ? new Date(bulkEffective).toISOString() : undefined,
      mark_for_individual_review: individualReview,
      reason: individualReview ? "Management selected rows for individual review." : "Management applied reviewed non-price metadata.",
    });
    setSelected([]);
  };
  const decide = async (id: string, version: number, decision: "REVIEW_COMPLETE" | "RETURN_FOR_CORRECTION") => {
    await mutations.reviewDecision.mutateAsync({ id, data: { expected_price_version: version, decision, reason: decision === "REVIEW_COMPLETE" ? "Management completed individual review." : "Management returned the draft for correction." } });
  };

  return <Card><CardHeader><CardTitle>All County management review</CardTitle><CardDescription>Review draft evidence and safe metadata in batches. Price, cost, and activation are never bulk actions.</CardDescription></CardHeader><CardContent className="space-y-5">
    {(queue.isError || mutations.bulkReview.isError || mutations.reviewDecision.isError) && <Alert variant="danger">Review authority changed or validation failed. Refresh before retrying; no activation occurred.</Alert>}
    <div className="grid gap-3 md:grid-cols-4"><Input aria-label="Search review queue" placeholder="Search code, name, or description" value={search} onChange={(event) => setSearch(event.target.value)} /><Select aria-label="Review category filter" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All categories</option>{categories.map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select><Select aria-label="Review Branch filter" value={branch} onChange={(event) => setBranch(event.target.value)}><option value="">All Branches</option>{branches.map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select><Select aria-label="Review classification filter" value={classification} onChange={(event) => setClassification(event.target.value)}><option value="">All review states</option>{["DRAFT_CANDIDATE", "INCOMPLETE", "CONFLICTING", "READY_FOR_REVIEW", "READY_FOR_ACTIVATION"].map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</Select></div>
    {selectedRows.length > 0 && <section aria-label="Bulk review controls" className="rounded-lg border border-stroke p-4"><p className="mb-3 font-semibold">{selectedRows.length} selected · non-activation metadata only</p><div className="grid gap-3 md:grid-cols-4"><Select aria-label="Bulk category" value={bulkCategory} onChange={(event) => setBulkCategory(event.target.value)}><option value="">Keep categories</option>{categories.filter((value) => value.status === "active").map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select><Select aria-label="Bulk Branch" value={bulkBranch} onChange={(event) => setBulkBranch(event.target.value)}><option value="">Keep Branches</option>{branches.map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select><Select aria-label="Bulk tax classification" value={bulkTax} onChange={(event) => setBulkTax(event.target.value)}><option value="">Keep tax treatment</option>{taxes.filter((value) => value.status === "active").map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select><Input aria-label="Bulk effective date" type="datetime-local" value={bulkEffective} onChange={(event) => setBulkEffective(event.target.value)} /></div><div className="mt-3 flex flex-wrap gap-2"><Button disabled={!bulkCategory && !bulkBranch && !bulkTax && !bulkEffective} loading={mutations.bulkReview.isPending} onClick={() => void applyBulk()}>Apply reviewed metadata</Button><Button variant="secondary" loading={mutations.bulkReview.isPending} onClick={() => void applyBulk(true)}>Mark for individual review</Button></div></section>}
    <div className="space-y-3">{rows.map((row) => <article key={row.price_version_id} className="rounded-lg border border-stroke p-4"><div className="flex flex-wrap items-start gap-3"><label className="flex min-h-11 items-center gap-2"><input aria-label={`Select ${row.code}`} type="checkbox" checked={selected.includes(row.price_version_id)} onChange={() => toggle(row.price_version_id)} />Select</label><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{row.code} · {row.name}</h3><Badge variant={row.activation_readiness === "READY_FOR_ACTIVATION" ? "success" : row.candidate_state === "CONFLICTING" ? "danger" : "warning"}>{row.activation_readiness.replaceAll("_", " ")}</Badge></div><p className="text-sm text-content-muted">{row.category_name ?? "Category missing"} · {row.branch_name} · {row.tax_classification_name ?? "Tax treatment missing"}</p><p className="mt-2">{row.currency} {row.proposed_price} · effective {new Date(row.effective_at).toLocaleString()}</p><p className="text-sm">Labor {row.labor_quantity ?? "missing"} · Materials {row.material_quantity ?? "missing"}</p><p className="text-sm">Internal cost: labor {row.labor_cost ?? "missing"} · materials {row.material_cost ?? "missing"}</p>{[...row.missing_evidence_reasons, ...row.conflict_reasons].map((reason) => <p key={reason} className="mt-1 text-sm text-status-warning">{reason}</p>)}</div><div className="flex flex-wrap gap-2">{row.activation_readiness === "READY_FOR_REVIEW" && <Button onClick={() => void decide(row.price_version_id, row.price_version, "REVIEW_COMPLETE")}>Complete review</Button>}<Button variant="secondary" onClick={() => void decide(row.price_version_id, row.price_version, "RETURN_FOR_CORRECTION")}>Return for correction</Button></div></div></article>)}</div>
    {!queue.isLoading && rows.length === 0 && <p className="text-content-muted">No draft candidates match these review filters.</p>}
    <p className="text-sm text-content-muted">Activation remains an explicit per-version action under Price Book activation authority.</p>
  </CardContent></Card>;
}
