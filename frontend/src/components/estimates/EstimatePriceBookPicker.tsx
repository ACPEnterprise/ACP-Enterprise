import { useMemo, useState } from "react";
import type { EffectivePriceBookItem } from "../../types/priceBook";
import { useEffectivePriceBook } from "../../hooks/usePriceBook";
import { Alert, Button, Card, CardContent, Input, Select, Spinner } from "../../ui";

function money(value: string, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(value));
}

export function EstimatePriceBookPicker({ branchId, effectiveAt, onAdd, pending }: { readonly branchId: string; readonly effectiveAt: string; readonly onAdd: (item: EffectivePriceBookItem, quantity: string, option?: { groupId: string; optionId: string }) => Promise<void>; readonly pending: boolean }) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [option, setOption] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const catalog = useEffectivePriceBook(branchId, effectiveAt, category || undefined, search || undefined, Boolean(branchId));
  const categories = useMemo(() => Array.from(new Map((catalog.data?.items ?? []).map((item) => [item.category_id, item.category_name]))), [catalog.data]);
  const selected = catalog.data?.items.find((item) => item.item_id === selectedId);
  const requiredOption = selected?.options.some((candidate) => candidate.minimum_selections > 0) ?? false;

  return <div className="space-y-4 sm:col-span-2">
    <div className="grid gap-3 sm:grid-cols-2">
      <Input aria-label="Search Price Book" placeholder="Search service name, code, or description" value={search} onChange={(event) => { setSearch(event.target.value); setSelectedId(""); setOption(""); }} />
      <Select aria-label="Price Book category" value={category} onChange={(event) => { setCategory(event.target.value); setSelectedId(""); setOption(""); }}><option value="">All categories</option>{categories.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</Select>
    </div>
    {!branchId ? <Alert>Select a Branch to browse effective Price Book items.</Alert> : catalog.isPending ? <Spinner label="Resolving effective Price Book" /> : catalog.isError ? <Alert variant="danger">Effective Price Book items could not be resolved for this date and Branch.</Alert> : !catalog.data?.items.length ? <p className="rounded-lg border border-dashed border-stroke p-4 text-sm text-content-muted">No active Price Book service is effective for this scope and date.</p> : <div className="grid gap-3 sm:grid-cols-2">{catalog.data.items.map((item) => <Card key={item.item_id} className={selectedId === item.item_id ? "border-action-primary" : undefined}><CardContent className="space-y-2 p-4"><div className="flex items-start justify-between gap-3"><div><p className="font-semibold">{item.item_name}</p><p className="text-xs text-content-muted">{item.item_code} · {item.category_name}</p></div><strong>{money(item.unit_price, item.currency)}</strong></div><p className="text-sm text-content-muted">{item.customer_description}</p><p className="text-xs text-content-muted">{item.taxable ? item.tax_classification_name : "Not taxable"}</p><Button type="button" variant={selectedId === item.item_id ? "primary" : "secondary"} onClick={() => { setSelectedId(item.item_id); setOption(""); }}>{selectedId === item.item_id ? "Selected" : "Select service"}</Button></CardContent></Card>)}</div>}
    {selected && <div className="rounded-lg border border-stroke bg-surface-subtle p-4"><p className="font-semibold">Configure {selected.item_name}</p><div className="mt-3 grid gap-3 sm:grid-cols-2"><Input aria-label="Service quantity" type="number" min="0.01" step="0.01" value={quantity} onChange={(event) => setQuantity(event.target.value)} />{selected.options.length > 0 && <Select aria-label="Service option" required={requiredOption} value={option} onChange={(event) => setOption(event.target.value)}><option value="">{requiredOption ? "Select required option" : "No option"}</option>{selected.options.map((candidate) => <option key={candidate.option_id} value={`${candidate.group_id}:${candidate.option_id}`}>{candidate.group_name}: {candidate.option_label}</option>)}</Select>}</div><Button className="mt-3" type="button" loading={pending} disabled={requiredOption && !option} onClick={() => { const [groupId, optionId] = option.split(":"); void onAdd(selected, quantity, option ? { groupId, optionId } : undefined); }}>Add to Estimate</Button></div>}
  </div>;
}
