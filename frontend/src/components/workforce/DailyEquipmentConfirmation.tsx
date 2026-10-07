import { useState } from "react";
import type { EquipmentConfirmationState } from "../../api/equipmentReadiness";
import { useConfirmDailyEquipment } from "../../hooks/useEquipmentReadiness";
import { Alert, Button, Card, Select, Textarea } from "../../ui";

const choices: { value: EquipmentConfirmationState; label: string }[] = [
  { value: "present_ready", label: "Present and ready" }, { value: "transferred", label: "Transferred" }, { value: "left_at_shop", label: "Left at shop" }, { value: "in_repair", label: "In repair" }, { value: "missing_or_unknown", label: "Missing / location unknown" }, { value: "incomplete_set", label: "Incomplete set" }, { value: "broken_or_out_of_service", label: "Broken / out of service" }, { value: "other", label: "Other" },
];

export function DailyEquipmentConfirmation({ employeeId, workDate, items, onContinue }: { readonly employeeId: string; readonly workDate: string; readonly items: readonly { catalog_item_id: string; placement_id: string | null; display_name: string; default_state: EquipmentConfirmationState }[]; readonly onContinue: () => Promise<void> }) {
  const confirm = useConfirmDailyEquipment(employeeId, workDate);
  const [states, setStates] = useState<Record<string, EquipmentConfirmationState>>(() => Object.fromEntries(items.map((item) => [item.catalog_item_id, item.default_state || "present_ready"])));
  const [note, setNote] = useState("");
  const submit = async () => {
    await confirm.mutateAsync({ employee_id: employeeId, work_date: workDate, confirmed_at: new Date().toISOString(), idempotency_key: `equipment-clock-in:${employeeId}:${workDate}`, items: items.map((item) => ({ catalog_item_id: item.catalog_item_id, placement_id: item.placement_id, state: states[item.catalog_item_id] ?? "present_ready", missing_components: [], note: note.trim() || null, receiving_employee_id: null, receiving_location_kind: null, receiving_location_entity_id: null })) });
    await onContinue();
  };
  return <Card className="p-4" aria-label="Equipment confirmation"><h3 className="text-lg font-semibold">Confirm today’s equipment</h3><p className="mt-1 text-sm text-content-muted">Tap only what changed, then continue to Clock In.</p><div className="mt-3 space-y-2">{items.map((item) => <label className="grid min-h-14 gap-1 rounded-lg border border-stroke p-3 sm:grid-cols-[1fr_15rem] sm:items-center" key={item.catalog_item_id}><strong>{item.display_name}</strong><Select aria-label={`${item.display_name} condition`} value={states[item.catalog_item_id]} onChange={(event) => setStates((current) => ({ ...current, [item.catalog_item_id]: event.target.value as EquipmentConfirmationState }))}>{choices.map((choice) => <option value={choice.value} key={choice.value}>{choice.label}</option>)}</Select></label>)}</div><label className="mt-3 block text-sm font-medium">Note (only if needed)<Textarea className="mt-1" value={note} onChange={(event) => setNote(event.target.value)} /></label>{Object.values(states).includes("transferred") && <Alert className="mt-3" variant="warning">Transfer requires a governed recipient or Location. The current prompt does not expose that selector, so confirmation remains unavailable.</Alert>}<Button className="mt-4" fullWidth size="large" disabled={confirm.isPending || Object.values(states).includes("transferred") || (Object.values(states).includes("incomplete_set"))} onClick={() => void submit()}>Confirm &amp; Clock In</Button>{confirm.isError && <Alert className="mt-3" variant="danger">Equipment confirmation was not saved. Clock In was not submitted.</Alert>}</Card>;
}
