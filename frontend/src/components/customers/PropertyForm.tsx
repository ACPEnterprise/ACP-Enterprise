import { useState, type FormEvent } from "react";

import type {
  CustomerProperty,
  CustomerPropertyInput,
} from "../../types/customers";

const inputClass =
  "mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-blue-500";

interface PropertyFormProps {
  property?: CustomerProperty;
  isSaving: boolean;
  onSubmit: (input: CustomerPropertyInput) => void;
  onCancel: () => void;
}
export function PropertyForm({ property, isSaving, onSubmit, onCancel }: PropertyFormProps) {
  const [form, setForm] = useState<CustomerPropertyInput>(() => ({
    address_line_1: property?.address_line_1 ?? "",
    address_line_2: property?.address_line_2 ?? "",
    city: property?.city ?? "",
    state: property?.state ?? "FL",
    postal_code: property?.postal_code ?? "",
    property_type: property?.property_type ?? "single_family",
    gate_access_instructions: property?.gate_access_instructions ?? "",
    water_shutoff_location: property?.water_shutoff_location ?? "",
    sewer_septic: property?.sewer_septic ?? "unknown",
    property_notes: property?.property_notes ?? "",
    is_primary: property?.is_primary ?? false,
  }));
  const update = <Key extends keyof CustomerPropertyInput>(
    key: Key,
    value: CustomerPropertyInput[Key],
  ) => setForm((current) => ({ ...current, [key]: value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit({
      ...form,
      address_line_2: form.address_line_2?.trim() || null,
      gate_access_instructions: form.gate_access_instructions?.trim() || null,
      water_shutoff_location: form.water_shutoff_location?.trim() || null,
      property_notes: form.property_notes?.trim() || null,
    });
  };

  return (
    <form onSubmit={submit} className="mt-4 rounded-xl border border-slate-700 bg-slate-950/60 p-4">
      <div className="grid gap-4 md:grid-cols-2">
        <label className="text-sm text-slate-300 md:col-span-2">
          Address line 1
          <input className={inputClass} required value={form.address_line_1} onChange={(event) => update("address_line_1", event.target.value)} />
        </label>
        <label className="text-sm text-slate-300 md:col-span-2">
          Address line 2
          <input className={inputClass} value={form.address_line_2 ?? ""} onChange={(event) => update("address_line_2", event.target.value)} />
        </label>
        <label className="text-sm text-slate-300">City<input className={inputClass} required value={form.city} onChange={(event) => update("city", event.target.value)} /></label>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm text-slate-300">State<input className={inputClass} required maxLength={2} value={form.state} onChange={(event) => update("state", event.target.value.toUpperCase())} /></label>
          <label className="text-sm text-slate-300">ZIP<input className={inputClass} required value={form.postal_code} onChange={(event) => update("postal_code", event.target.value)} /></label>
        </div>
        <label className="text-sm text-slate-300">Property type
          <select className={inputClass} value={form.property_type} onChange={(event) => update("property_type", event.target.value as CustomerPropertyInput["property_type"])}>
            <option value="single_family">Single family</option><option value="multi_family">Multi-family</option><option value="commercial">Commercial</option><option value="condo">Condo</option><option value="townhome">Townhome</option><option value="mobile_home">Mobile home</option><option value="other">Other</option>
          </select>
        </label>
        <label className="text-sm text-slate-300">Waste system
          <select className={inputClass} value={form.sewer_septic ?? "unknown"} onChange={(event) => update("sewer_septic", event.target.value as CustomerPropertyInput["sewer_septic"])}>
            <option value="unknown">Unknown</option><option value="sewer">Sewer</option><option value="septic">Septic</option>
          </select>
        </label>
        <label className="text-sm text-slate-300 md:col-span-2">Gate or access instructions<textarea className={inputClass} value={form.gate_access_instructions ?? ""} onChange={(event) => update("gate_access_instructions", event.target.value)} /></label>
        <label className="text-sm text-slate-300">Water shutoff location<textarea className={inputClass} value={form.water_shutoff_location ?? ""} onChange={(event) => update("water_shutoff_location", event.target.value)} /></label>
        <label className="text-sm text-slate-300">Property notes<textarea className={inputClass} value={form.property_notes ?? ""} onChange={(event) => update("property_notes", event.target.value)} /></label>
      </div>
      <label className="mt-4 flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={form.is_primary} onChange={(event) => update("is_primary", event.target.checked)} /> Primary property</label>
      <div className="mt-4 flex justify-end gap-3"><button type="button" onClick={onCancel} className="rounded-lg border border-slate-700 px-3 py-2 text-sm">Cancel</button><button disabled={isSaving} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold disabled:opacity-50">{isSaving ? "Saving…" : "Save property"}</button></div>
    </form>
  );
}
