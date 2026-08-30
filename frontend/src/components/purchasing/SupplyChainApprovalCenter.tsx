import { useState, type FormEvent } from "react";
import type { OperationalVendor, PurchaseRequisition } from "../../types/purchasing";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Select } from "../../ui";
import { usePurchasingMutations } from "../../hooks/usePurchasing";

interface Props {
  branches: readonly { id: string; name: string }[];
  vendors: readonly OperationalVendor[];
  requisitions: readonly PurchaseRequisition[];
  canManage: boolean;
  canApprove: boolean;
}

export function SupplyChainApprovalCenter({ branches, vendors, requisitions, canManage, canApprove }: Props) {
  const mutations = usePurchasingMutations();
  const [request, setRequest] = useState({ branch_id: "", request_number: "", description: "", quantity: "1", unit: "each", need_by: "", source_type: "manual" as const, source_reference: "operator", reason: "", suggested_vendor_id: "" });
  const [conversion, setConversion] = useState({ vendor_id: "", po_number: "", currency: "USD", unit_cost: "0" });
  const [error, setError] = useState<string | null>(null);
  const pending = Boolean(mutations.createRequisition?.isPending || mutations.transitionRequisition?.isPending);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(null);
    try {
      if (!mutations.createRequisition) throw new Error("Requisition mutation unavailable");
      await mutations.createRequisition.mutateAsync({ ...request, need_by: request.need_by || null, suggested_vendor_id: request.suggested_vendor_id || null, reason: request.reason, idempotency_key: crypto.randomUUID() });
      setRequest({ branch_id: "", request_number: "", description: "", quantity: "1", unit: "each", need_by: "", source_type: "manual", source_reference: "operator", reason: "", suggested_vendor_id: "" });
    } catch { setError("The purchase request was not recorded. Review authoritative Branch, item, and Vendor evidence."); }
  };
  const transition = async (item: PurchaseRequisition, action: "submit" | "approve" | "reject" | "convert" | "cancel") => {
    setError(null);
    try {
      if (!mutations.transitionRequisition) throw new Error("Requisition transition unavailable");
      await mutations.transitionRequisition.mutateAsync({ id: item.id, action, input: { expected_version: item.version, reason: `Authorized ${action} disposition`, ...(action === "convert" ? conversion : {}), idempotency_key: crypto.randomUUID() } });
    } catch { setError("The request changed or the disposition is not authorized. Server truth was refreshed; no outcome was assumed."); }
  };
  return <section className="space-y-4" aria-labelledby="supply-chain-approvals">
    <header><h2 id="supply-chain-approvals" className="text-xl font-bold">Supply Chain approval center</h2><p className="text-content-muted">Demand remains separate from Purchase Order approval, receiving, AP, and Accounting.</p></header>
    {error && <Alert variant="danger">{error}</Alert>}
    {canManage && <Card><CardHeader><CardTitle>Create purchase request</CardTitle><CardDescription>Capture manual, replenishment, Job, location, or approved emergency demand with provenance.</CardDescription></CardHeader><CardContent><form className="grid gap-3 md:grid-cols-3" onSubmit={(event) => void submit(event)}>
      <Select aria-label="Request Branch" value={request.branch_id} onChange={(event) => setRequest({ ...request, branch_id: event.target.value })} required><option value="">Branch</option>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</Select>
      <Input aria-label="Request number" value={request.request_number} onChange={(event) => setRequest({ ...request, request_number: event.target.value })} required />
      <Select aria-label="Demand source" value={request.source_type} onChange={(event) => setRequest({ ...request, source_type: event.target.value as typeof request.source_type })}><option value="manual">Manual</option><option value="replenishment">Replenishment</option><option value="job_material">Job material</option><option value="stock_location">Stock location</option><option value="emergency_exception">Emergency exception</option></Select>
      <Input aria-label="Requested description" value={request.description} onChange={(event) => setRequest({ ...request, description: event.target.value })} required />
      <Input aria-label="Requested quantity" type="number" min="0.000001" step="any" value={request.quantity} onChange={(event) => setRequest({ ...request, quantity: event.target.value })} required />
      <Input aria-label="Requested unit" value={request.unit} onChange={(event) => setRequest({ ...request, unit: event.target.value })} required />
      <Input aria-label="Need by" type="date" value={request.need_by} onChange={(event) => setRequest({ ...request, need_by: event.target.value })} />
      <Select aria-label="Suggested Vendor" value={request.suggested_vendor_id} onChange={(event) => setRequest({ ...request, suggested_vendor_id: event.target.value })}><option value="">No Vendor suggestion</option>{vendors.filter((vendor) => vendor.status === "active").map((vendor) => <option key={vendor.id} value={vendor.id}>{vendor.display_name}</option>)}</Select>
      <Input aria-label="Request reason" value={request.reason} onChange={(event) => setRequest({ ...request, reason: event.target.value })} required />
      <Button type="submit" loading={pending}>Record request</Button>
    </form></CardContent></Card>}
    <div className="grid gap-3">
      {requisitions.length === 0 ? <Alert>No purchase requests are in the authorized scope.</Alert> : requisitions.map((item) => <Card key={item.id}><CardContent className="space-y-3 pt-6">
        <div className="flex flex-wrap items-center justify-between gap-2"><div><p className="font-semibold">{item.request_number} · {item.description}</p><p className="text-sm text-content-muted">{item.quantity} {item.unit} · {item.source_type} · {item.source_reference}</p></div><Badge>{item.status}</Badge></div>
        <p className="break-all text-xs text-content-muted">Evidence {item.evidence_digest}</p>
        <div className="flex flex-wrap gap-2">
          {canManage && item.status === "draft" && <Button size="small" disabled={pending} onClick={() => void transition(item, "submit")}>Submit</Button>}
          {canApprove && item.status === "submitted" && <><Button size="small" disabled={pending} onClick={() => void transition(item, "approve")}>Approve</Button><Button size="small" variant="secondary" disabled={pending} onClick={() => void transition(item, "reject")}>Reject</Button></>}
        </div>
        {canApprove && item.status === "approved" && <div className="grid gap-2 md:grid-cols-5"><Select aria-label={`Vendor for ${item.request_number}`} value={conversion.vendor_id} onChange={(event) => setConversion({ ...conversion, vendor_id: event.target.value })}><option value="">Vendor</option>{vendors.filter((vendor) => vendor.status === "active").map((vendor) => <option key={vendor.id} value={vendor.id}>{vendor.display_name}</option>)}</Select><Input aria-label={`PO number for ${item.request_number}`} value={conversion.po_number} onChange={(event) => setConversion({ ...conversion, po_number: event.target.value })} /><Input aria-label={`Currency for ${item.request_number}`} value={conversion.currency} onChange={(event) => setConversion({ ...conversion, currency: event.target.value.toUpperCase() })} /><Input aria-label={`Unit cost for ${item.request_number}`} type="number" min="0" step="0.0001" value={conversion.unit_cost} onChange={(event) => setConversion({ ...conversion, unit_cost: event.target.value })} /><Button disabled={pending || !conversion.vendor_id || !conversion.po_number} onClick={() => void transition(item, "convert")}>Create draft PO</Button></div>}
      </CardContent></Card>)}
    </div>
  </section>;
}
