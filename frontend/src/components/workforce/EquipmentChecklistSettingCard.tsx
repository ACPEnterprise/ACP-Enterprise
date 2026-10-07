import { useEquipmentChecklistSetting, useSetEquipmentChecklistSetting } from "../../hooks/useEquipmentReadiness";
import { Alert, Card, Spinner } from "../../ui";

export function EquipmentChecklistSettingCard({ employeeId, canManage }: { readonly employeeId: string; readonly canManage: boolean }) {
  const setting = useEquipmentChecklistSetting(employeeId);
  const update = useSetEquipmentChecklistSetting(employeeId);
  if (setting.isLoading) return <Card className="p-4"><Spinner label="Loading equipment checklist setting" /></Card>;
  if (setting.isError || !setting.data) return <Alert variant="warning" title="Equipment checklist unavailable">The qualified Equipment Readiness service is not available in this environment. No setting was inferred.</Alert>;
  return <section id="employee-field-operations" className="mt-5 scroll-mt-4 rounded-xl border border-stroke p-4" aria-labelledby="equipment-checklist-heading">
    <h4 id="equipment-checklist-heading" className="font-semibold">Field Operations</h4>
    <p className="mt-1 text-sm text-content-muted">Equipment Checklist</p>
    <fieldset className="mt-3 space-y-2" disabled={!canManage || update.isPending}>
      <legend className="sr-only">Equipment Checklist requirement</legend>
      {[{ value: "not_required", label: "Not required" }, { value: "required_at_clock_in", label: "Required at clock-in" }].map((option) => <label className="flex min-h-11 items-center gap-3 rounded-lg border border-stroke px-3" key={option.value}><input type="radio" name="equipment-checklist" value={option.value} checked={setting.data.equipment_checklist_requirement === option.value} onChange={() => update.mutate(option.value as "not_required" | "required_at_clock_in")} />{option.label}</label>)}
    </fieldset>
    {!canManage && <p className="mt-2 text-xs text-content-muted">Management authority is required to change this setting.</p>}
    {update.isError && <Alert className="mt-3" variant="danger">The setting changed or could not be saved. Refresh before trying again.</Alert>}
    <div className="mt-4 border-t border-stroke pt-3"><p className="text-sm font-semibold">Assigned Vehicle</p><p className="text-sm text-content-muted">Vehicle assignment is unavailable in the current Employee projection. It remains separate from checklist responsibility.</p></div>
  </section>;
}
