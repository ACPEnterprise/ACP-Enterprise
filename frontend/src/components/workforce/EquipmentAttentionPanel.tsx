import { useEquipmentAttention } from "../../hooks/useEquipmentReadiness";
import { Alert, Badge, Card, Spinner } from "../../ui";

export function EquipmentAttentionPanel({ branchId, authorized }: { readonly branchId?: string; readonly authorized: boolean }) {
  const attention = useEquipmentAttention(branchId, authorized);
  if (!authorized) return null;
  if (attention.isLoading) return <Spinner label="Loading Field Operations attention" />;
  if (attention.isError) return <Alert variant="warning" title="Field Operations attention unavailable">No equipment state was inferred.</Alert>;
  const items = attention.data ?? [];
  if (!items.length) return <Alert variant="success" title="Field Operations ✓">No equipment issues requiring attention.</Alert>;
  return <section aria-label="Field Operations needs attention">
    <h3 className="text-lg font-semibold">Needs Attention ({items.length})</h3>
    <div className="mt-3 grid gap-3 md:grid-cols-2">{items.map((item) => <Card className="p-4" key={item.id}><div className="flex justify-between gap-3"><strong>{item.title}</strong><Badge variant={item.priority === "critical" || item.priority === "high" ? "danger" : "warning"}>{item.priority.replaceAll("_", " ")}</Badge></div><p className="mt-2 text-sm">{item.explanation}</p><p className="mt-2 text-xs text-content-muted">Responsible: {item.responsibility_code.replaceAll("_", " ").toLowerCase()} · observed {new Date(item.first_observed_at).toLocaleString()}</p></Card>)}</div>
  </section>;
}
