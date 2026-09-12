import { useState } from "react";

import { usePriceBookMutations } from "../../hooks/usePriceBook";
import type { BulkDraftCandidate, BulkDraftValidation, PriceBookCategory, TaxClassification } from "../../types/priceBook";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Select, Textarea } from "../../ui";

interface DraftRow {
  ref: string; code: string; name: string; category: string; customerDescription: string;
  internalDescription: string; price: string; tax: string; effective: string;
  laborQuantity: string; laborCost: string; materialQuantity: string; materialCost: string;
}

const emptyRow = (): DraftRow => ({ ref: crypto.randomUUID(), code: "", name: "", category: "", customerDescription: "", internalDescription: "", price: "", tax: "", effective: "", laborQuantity: "", laborCost: "", materialQuantity: "", materialCost: "" });

export function BulkDraftWorkspace({ branchId, categories, taxes }: { readonly branchId: string; readonly categories: PriceBookCategory[]; readonly taxes: TaxClassification[] }) {
  const mutations = usePriceBookMutations();
  const [rows, setRows] = useState<DraftRow[]>([emptyRow()]);
  const [paste, setPaste] = useState("");
  const [validation, setValidation] = useState<BulkDraftValidation | null>(null);
  const [saved, setSaved] = useState(0);
  const update = (index: number, patch: Partial<DraftRow>) => { setRows((current) => current.map((row, candidate) => candidate === index ? { ...row, ...patch } : row)); setValidation(null); setSaved(0); };
  const payload = (): BulkDraftCandidate[] => rows.map((row) => ({
    client_ref: row.ref, branch_id: branchId || undefined, category_id: row.category || undefined,
    code: row.code, name: row.name, customer_description: row.customerDescription,
    internal_description: row.internalDescription || undefined, tax_classification_id: row.tax || undefined,
    currency: "USD", unit_price: row.price || undefined,
    effective_at: row.effective ? new Date(row.effective).toISOString() : undefined,
    components: [
      ...(row.laborQuantity ? [{ component_type: "labor" as const, label: "Labor", quantity: row.laborQuantity, unit_cost: row.laborCost || undefined }] : []),
      ...(row.materialQuantity ? [{ component_type: "material" as const, label: "Materials", quantity: row.materialQuantity, unit_cost: row.materialCost || undefined }] : []),
    ],
  }));
  const importRows = () => {
    const imported = paste.trim().split(/\r?\n/).filter(Boolean).map((line) => {
      const [code = "", name = "", description = "", price = "", labor = "", material = ""] = line.split("\t");
      return { ...emptyRow(), code: code.trim(), name: name.trim(), customerDescription: description.trim(), price: price.trim(), laborQuantity: labor.trim(), materialQuantity: material.trim() };
    });
    if (imported.length) { setRows(imported.slice(0, 100)); setPaste(""); setValidation(null); }
  };
  const validate = async () => { try { setValidation(await mutations.validateBulk.mutateAsync(payload())); } catch { /* Safe error state is rendered below. */ } };
  const save = async () => { try { const result = await mutations.createBulk.mutateAsync(payload()); setSaved(result.created.length); setRows([emptyRow()]); setValidation(null); } catch { /* Safe error state is rendered below. */ } };

  return <Card><CardHeader><CardTitle>All County draft builder</CardTitle><CardDescription>Build up to 100 draft services at once. Validation never activates pricing; incomplete cost evidence remains explicit.</CardDescription></CardHeader><CardContent className="space-y-5">
    {saved > 0 && <Alert variant="success">{saved} service drafts were created for review. No prices were activated.</Alert>}
    {(mutations.validateBulk.isError || mutations.createBulk.isError) && <Alert variant="danger">The draft batch was not saved. Refresh Price Book authority and review the validation results.</Alert>}
    <div className="space-y-2"><Textarea aria-label="Paste draft services" placeholder={"Paste tab-separated rows: code, name, customer description, proposed price, labor quantity, material quantity"} value={paste} onChange={(event) => setPaste(event.target.value)} /><Button type="button" variant="secondary" disabled={!paste.trim()} onClick={importRows}>Load pasted rows</Button></div>
    <div className="space-y-4">{rows.map((row, index) => { const result = validation?.rows.find((value) => value.client_ref === row.ref); return <fieldset key={row.ref} className="rounded-lg border border-stroke p-4"><legend className="px-2 font-semibold">Draft service {index + 1}</legend><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><Input aria-label={`Service code ${index + 1}`} placeholder="Code" value={row.code} onChange={(event) => update(index, { code: event.target.value })} /><Input aria-label={`Service name ${index + 1}`} placeholder="Service name" value={row.name} onChange={(event) => update(index, { name: event.target.value })} /><Select aria-label={`Service category ${index + 1}`} value={row.category} onChange={(event) => update(index, { category: event.target.value })}><option value="">Choose category</option>{categories.filter((value) => value.status === "active").map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select><Select aria-label={`Tax classification ${index + 1}`} value={row.tax} onChange={(event) => update(index, { tax: event.target.value })}><option value="">Choose tax treatment</option>{taxes.filter((value) => value.status === "active").map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select><Textarea aria-label={`Customer description ${index + 1}`} placeholder="Customer-facing description" value={row.customerDescription} onChange={(event) => update(index, { customerDescription: event.target.value })} /><Textarea aria-label={`Internal description ${index + 1}`} placeholder="Internal description" value={row.internalDescription} onChange={(event) => update(index, { internalDescription: event.target.value })} /><Input aria-label={`Proposed price ${index + 1}`} type="number" min="0" step="0.01" placeholder="Proposed sell price" value={row.price} onChange={(event) => update(index, { price: event.target.value })} /><Input aria-label={`Effective date ${index + 1}`} type="datetime-local" value={row.effective} onChange={(event) => update(index, { effective: event.target.value })} /><Input aria-label={`Labor quantity ${index + 1}`} type="number" min="0.0001" step="0.0001" placeholder="Labor quantity" value={row.laborQuantity} onChange={(event) => update(index, { laborQuantity: event.target.value })} /><Input aria-label={`Labor unit cost ${index + 1}`} type="number" min="0" step="0.0001" placeholder="Labor unit cost" value={row.laborCost} onChange={(event) => update(index, { laborCost: event.target.value })} /><Input aria-label={`Material quantity ${index + 1}`} type="number" min="0.0001" step="0.0001" placeholder="Material quantity" value={row.materialQuantity} onChange={(event) => update(index, { materialQuantity: event.target.value })} /><Input aria-label={`Material unit cost ${index + 1}`} type="number" min="0" step="0.0001" placeholder="Material unit cost" value={row.materialCost} onChange={(event) => update(index, { materialCost: event.target.value })} /></div><div className="mt-3 flex flex-wrap items-center gap-2">{result && <Badge variant={result.readiness === "READY_FOR_REVIEW" ? "success" : "warning"}>{result.readiness === "READY_FOR_REVIEW" ? "Ready for review" : "Incomplete"}</Badge>}{result?.issues.map((issue) => <span key={`${issue.code}:${issue.field}`} className="text-xs text-status-warning">{issue.message}</span>)}<Button className="ml-auto" type="button" variant="ghost" disabled={rows.length === 1} onClick={() => { setRows((current) => current.filter((_, candidate) => candidate !== index)); setValidation(null); }}>Remove row</Button></div></fieldset>; })}</div>
    <div className="flex flex-wrap gap-3"><Button type="button" variant="secondary" disabled={rows.length >= 100} onClick={() => setRows((current) => [...current, emptyRow()])}>Add another service</Button><Button type="button" loading={mutations.validateBulk.isPending} onClick={() => void validate()}>Validate drafts</Button><Button type="button" loading={mutations.createBulk.isPending} disabled={!validation?.can_save} onClick={() => void save()}>Save validated drafts</Button></div>
  </CardContent></Card>;
}
