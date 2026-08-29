import { useState, type FormEvent } from "react";
import type { ReplenishmentWorkbench as Result } from "../../types/purchasing";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "../../ui";

interface Props {
  pending: boolean;
  result: Result | undefined;
  error: boolean;
  onRun: (branchId: string, itemId: string, target: string) => Promise<unknown>;
}

export function ReplenishmentWorkbench({ pending, result, error, onRun }: Props) {
  const [branchId, setBranchId] = useState("");
  const [itemId, setItemId] = useState("");
  const [target, setTarget] = useState("0");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void onRun(branchId.trim(), itemId.trim(), target);
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>Replenishment workbench</CardTitle>
        <CardDescription>Read-only Purchasing recommendations from authoritative branch inventory evidence and open POs. This does not create a PO or mutate Inventory.</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="grid gap-3 sm:grid-cols-4" onSubmit={submit}>
          <Input required aria-label="Replenishment branch ID" value={branchId} onChange={(event) => setBranchId(event.target.value)} placeholder="Branch ID" />
          <Input required aria-label="Replenishment inventory item ID" value={itemId} onChange={(event) => setItemId(event.target.value)} placeholder="Inventory item ID" />
          <Input required aria-label="Target available quantity" type="number" min="0" step="0.000001" value={target} onChange={(event) => setTarget(event.target.value)} />
          <Button type="submit" loading={pending}>Calculate</Button>
        </form>
        {error && <Alert variant="danger">Recommendation evidence was incomplete or inaccessible. No quantity was assumed.</Alert>}
        {result?.recommendations.map((item) => (
          <div key={`${item.branch_id}:${item.inventory_item_id}`} className="mt-3 rounded border border-stroke p-3 text-sm">
            <div className="flex gap-2"><strong>{item.item_code} — {item.item_name}</strong><Badge>{item.recommendation_state}</Badge></div>
            <div>Available {item.available_quantity} · open PO {item.open_purchase_order_quantity} · target {item.target_available_quantity}</div>
            <div><strong>Recommended {item.recommended_order_quantity} {item.stocking_unit}</strong></div>
            <div className="text-content-muted">Evidence {item.evidence_digest.slice(0, 12)} · as of {new Date(result.as_of).toLocaleString()}</div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
