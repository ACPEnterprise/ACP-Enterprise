import type { JobMaterials } from "../../types/inventory";
import { Alert, Card, CardContent, CardHeader, CardTitle } from "../../ui";

const label = (value: string) => value.toLowerCase().replaceAll("_", " ");

export function JobMaterialsCard({ materials }: { readonly materials: JobMaterials }) {
  return (
    <Card>
      <CardHeader><CardTitle>Job materials</CardTitle></CardHeader>
      <CardContent>
      <p className="mb-3 text-sm text-content-muted">
        Expected parts come from the approved Estimate snapshot. Expected, reserved,
        and consumed quantities remain separate.
      </p>
      {materials.blockers.length > 0 ? (
        <Alert variant="warning">{materials.blockers.map(label).join("; ")}</Alert>
      ) : null}
      {materials.requirements.length === 0 ? (
        <p className="mt-3 text-sm text-content-muted">No expected material parts are defined.</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr><th>Part</th><th>Expected</th><th>Available</th><th>Reserved</th><th>Consumed</th><th>State</th></tr></thead>
            <tbody>
              {materials.requirements.map((part, index) => (
                <tr key={`${part.component_code ?? "unbound"}-${index}`} className="border-t border-border-subtle">
                  <td className="py-2"><span className="font-medium">{part.label}</span>{part.component_code ? <span className="block text-xs text-content-muted">{part.component_code}</span> : null}</td>
                  <td>{part.expected_quantity} {part.stocking_unit ?? "unit(s)"}</td>
                  <td>{part.available_quantity ?? "Unknown"}</td>
                  <td>{part.reserved_quantity ?? "Unknown"}</td>
                  <td>{part.consumed_quantity ?? "Unknown"}</td>
                  <td>{label(part.readiness_state)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      </CardContent>
    </Card>
  );
}
