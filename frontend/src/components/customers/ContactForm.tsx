import { useState, type FormEvent } from "react";

import type { CustomerContact, CustomerContactInput } from "../../types/customers";

const inputClass = "mt-1 min-h-11 w-full rounded-lg border border-stroke-strong bg-surface px-3 py-2 text-sm text-content outline-none focus:border-action-primary";

interface ContactFormProps {
  contact?: CustomerContact;
  isSaving: boolean;
  onSubmit: (input: CustomerContactInput) => void;
  onCancel: () => void;
}
export function ContactForm({ contact, isSaving, onSubmit, onCancel }: ContactFormProps) {
  const [form, setForm] = useState<CustomerContactInput>(() => ({
    first_name: contact?.first_name ?? "",
    last_name: contact?.last_name ?? "",
    relationship_or_role: contact?.relationship_or_role ?? "",
    phone: contact?.phone ?? "",
    email: contact?.email ?? "",
    is_preferred: contact?.is_preferred ?? false,
    can_approve_work: contact?.can_approve_work ?? false,
  }));
  const [error, setError] = useState<string | null>(null);
  const update = <Key extends keyof CustomerContactInput>(key: Key, value: CustomerContactInput[Key]) => setForm((current) => ({ ...current, [key]: value }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!form.phone?.trim() && !form.email?.trim()) {
      setError("A contact requires a phone number or email address.");
      return;
    }
    setError(null);
    onSubmit({ ...form, last_name: form.last_name?.trim() || null, relationship_or_role: form.relationship_or_role?.trim() || null, phone: form.phone?.trim() || null, email: form.email?.trim() || null });
  };
  return (
    <form onSubmit={submit} className="mt-4 rounded-xl border border-stroke bg-surface-subtle p-4">
      <div className="grid gap-4 md:grid-cols-2">
        <label className="text-sm text-content-secondary">First name<input className={inputClass} required value={form.first_name} onChange={(event) => update("first_name", event.target.value)} /></label>
        <label className="text-sm text-content-secondary">Last name<input className={inputClass} value={form.last_name ?? ""} onChange={(event) => update("last_name", event.target.value)} /></label>
        <label className="text-sm text-content-secondary">Relationship or role<input className={inputClass} value={form.relationship_or_role ?? ""} onChange={(event) => update("relationship_or_role", event.target.value)} /></label>
        <label className="text-sm text-content-secondary">Phone<input className={inputClass} type="tel" value={form.phone ?? ""} onChange={(event) => update("phone", event.target.value)} /></label>
        <label className="text-sm text-content-secondary md:col-span-2">Email<input className={inputClass} type="email" value={form.email ?? ""} onChange={(event) => update("email", event.target.value)} /></label>
      </div>
      <div className="mt-4 grid gap-2 text-sm text-content-secondary sm:grid-cols-2">
        <label className="flex min-h-11 items-center gap-2"><input className="h-5 w-5" type="checkbox" checked={form.is_preferred} onChange={(event) => update("is_preferred", event.target.checked)} /> Preferred contact</label>
        <label className="flex min-h-11 items-center gap-2"><input className="h-5 w-5" type="checkbox" checked={form.can_approve_work} onChange={(event) => update("can_approve_work", event.target.checked)} /> Authorized to approve work</label>
      </div>
      {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
      <div className="mt-4 grid gap-3 sm:flex sm:justify-end"><button type="button" onClick={onCancel} className="min-h-11 rounded-lg border border-stroke-strong px-3 py-2 text-sm">Cancel</button><button disabled={isSaving} className="min-h-11 rounded-lg bg-action-primary px-4 py-2 text-sm font-semibold text-content-inverse disabled:opacity-50">{isSaving ? "Saving…" : "Save contact"}</button></div>
    </form>
  );
}
