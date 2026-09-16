import type { InventoryItem, MaterialCostReadiness } from "../types/inventory";
import { Alert, Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui";

const operatorLabel = (value: string) => value.toLowerCase().replaceAll("_", " ");

export function MaterialCostReadinessCard({
  data,
  items,
}: {
  readonly data: MaterialCostReadiness;
  readonly items: readonly InventoryItem[];
}) {
  const itemName = (id: string) => items.find((item) => item.id === id)?.name ?? id;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Material cost and valuation readiness</CardTitle>
        <CardDescription>
          Receipt cost is source evidence. It is not an Accounting valuation or posting.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {data.readiness.some((row) => row.blockers.includes("VALUATION_METHOD_POLICY_REQUIRED")) ? (
          <Alert variant="warning">Owner/accountant valuation-method policy is still required.</Alert>
        ) : null}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr><th className="p-2">Item</th><th className="p-2">On hand</th><th className="p-2">Receipt cost</th><th className="p-2">State</th></tr></thead>
            <tbody>{data.readiness.map((row) => (
              <tr key={row.inventory_item_id} className="border-t border-stroke">
                <td className="p-2">{itemName(row.inventory_item_id)}</td>
                <td className="p-2">{row.on_hand_quantity}</td>
                <td className="p-2">{row.actual_receipt_cost_available ? "Available" : "Missing"}</td>
                <td className="p-2"><Badge>{operatorLabel(row.readiness_state)}</Badge><div className="text-xs text-content-muted">{row.blockers.map(operatorLabel).join("; ") || "No blocker"}</div></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <div>
          <h3 className="font-semibold">Actual receipt cost history</h3>
          {data.evidence.length === 0 ? <p className="text-sm text-content-muted">No authoritative receipt-cost evidence is available.</p> : (
            <ul className="mt-2 space-y-2">{data.evidence.map((row) => (
              <li key={row.receipt_line_id} className="rounded-lg border border-stroke p-3 text-sm">
                <strong>{itemName(row.inventory_item_id)}</strong> — {row.accepted_quantity} {row.unit} at {row.unit_cost} {row.currency}
                <div className="text-content-muted">{row.vendor_name} · received {new Date(row.received_at).toLocaleString()} · actual receipt</div>
              </li>
            ))}</ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
