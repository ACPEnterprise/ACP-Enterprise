import { useState, type FormEvent } from "react";
import { ArrowLeft, Edit3, MapPin, Plus, Star, UserRound } from "lucide-react";

import { getApiErrorMessage } from "../../api/errors";
import { useCustomerDetail, useCustomerMutations } from "../../hooks/useCustomers";
import type { CustomerContact, CustomerProperty } from "../../types/customers";
import { ContactForm } from "./ContactForm";
import { CustomerForm } from "./CustomerForm";
import { PropertyForm } from "./PropertyForm";

interface CustomerDetailViewProps {
  customerId: string;
  onBack: () => void;
}

function displayName(customer: {
  first_name: string | null;
  last_name: string | null;
  business_name: string | null;
}) {
  return customer.business_name || `${customer.first_name ?? ""} ${customer.last_name ?? ""}`.trim();
}

export function CustomerDetailView({ customerId, onBack }: CustomerDetailViewProps) {
  const detail = useCustomerDetail(customerId);
  const mutations = useCustomerMutations(customerId);
  const [isEditingCustomer, setIsEditingCustomer] = useState(false);
  const [editingProperty, setEditingProperty] = useState<CustomerProperty | "new" | null>(null);
  const [editingContact, setEditingContact] = useState<CustomerContact | "new" | null>(null);
  const [noteBody, setNoteBody] = useState("");
  const [actionError, setActionError] = useState<unknown>(null);

  if (detail.isLoading) {
    return <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8 text-slate-400">Loading customer…</div>;
  }
  if (detail.isError || !detail.data) {
    return (
      <div className="rounded-2xl border border-red-900 bg-red-950/40 p-6 text-red-300">
        Unable to load customer. {getApiErrorMessage(detail.error)}
        <button type="button" onClick={onBack} className="mt-4 block text-sm underline">Return to customer list</button>
      </div>
    );
  }

  const customer = detail.data;
  const archived = Boolean(customer.archived_at);

  const addNote = (event: FormEvent) => {
    event.preventDefault();
    if (!noteBody.trim()) return;
    setActionError(null);
    mutations.addNote.mutate(noteBody.trim(), {
      onSuccess: () => setNoteBody(""),
      onError: setActionError,
    });
  };

  return (
    <div className="space-y-6">
      <button type="button" onClick={onBack} className="flex items-center gap-2 text-sm text-blue-400 hover:text-blue-300"><ArrowLeft size={17} /> Back to customers</button>

      <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-2xl font-bold text-white">{displayName(customer)}</h2>
              {customer.is_vip && <Star size={19} className="fill-amber-400 text-amber-400" aria-label="VIP customer" />}
            </div>
            <p className="mt-2 text-sm text-slate-400">{customer.primary_phone}{customer.email ? ` · ${customer.email}` : ""}</p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <span className="rounded-full bg-slate-800 px-3 py-1 text-slate-300">{customer.customer_type}</span>
              <span className={`rounded-full px-3 py-1 ${archived ? "bg-red-950 text-red-300" : "bg-emerald-950 text-emerald-300"}`}>{archived ? "archived" : customer.status.replaceAll("_", " ")}</span>
              <span className="rounded-full bg-blue-950 px-3 py-1 text-blue-300">Source: {customer.source.replaceAll("_", " ")}</span>
            </div>
          </div>
          {!archived && (
            <div className="flex gap-3">
              <button type="button" onClick={() => setIsEditingCustomer(true)} className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200"><Edit3 size={16} /> Edit</button>
              <button
                type="button"
                disabled={mutations.archive.isPending}
                onClick={() => {
                  if (window.confirm("Archive this customer? They will be removed from normal search and cannot be edited.")) {
                    mutations.archive.mutate(undefined, { onError: setActionError });
                  }
                }}
                className="rounded-lg border border-red-900 px-3 py-2 text-sm text-red-300 disabled:opacity-50"
              >Archive</button>
            </div>
          )}
        </div>
        {customer.internal_notes && <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/60 p-4 text-sm text-slate-300"><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Internal context</p>{customer.internal_notes}</div>}
        {isEditingCustomer && (
          <div className="mt-6 border-t border-slate-800 pt-6">
            <CustomerForm
              key={customer.updated_at}
              customer={customer}
              isSaving={mutations.update.isPending}
              error={mutations.update.error}
              onCancel={() => setIsEditingCustomer(false)}
              onSubmit={(input) => mutations.update.mutate(input, { onSuccess: () => setIsEditingCustomer(false) })}
            />
          </div>
        )}
      </section>

      {Boolean(actionError) && <div className="rounded-xl border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">{getApiErrorMessage(actionError)}</div>}

      <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <div className="flex items-center justify-between"><div><p className="text-sm text-blue-400">Service locations</p><h3 className="mt-1 text-xl font-semibold">Properties</h3></div>{!archived && <button type="button" onClick={() => setEditingProperty("new")} className="flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm"><Plus size={16} /> Add property</button>}</div>
        {customer.properties.length === 0 && editingProperty === null && <p className="mt-5 rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-500">No service properties have been added.</p>}
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {customer.properties.map((property) => (
            <article key={property.id} className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
              <div className="flex justify-between gap-3"><div className="flex gap-3"><MapPin size={18} className="mt-0.5 text-blue-400" /><div><p className="font-medium">{property.address_line_1}</p>{property.address_line_2 && <p className="text-sm text-slate-400">{property.address_line_2}</p>}<p className="text-sm text-slate-400">{property.city}, {property.state} {property.postal_code}</p></div></div>{property.is_primary && <span className="h-fit rounded-full bg-blue-950 px-2 py-1 text-xs text-blue-300">Primary</span>}</div>
              <p className="mt-3 text-xs text-slate-500">{property.property_type.replaceAll("_", " ")} · {property.sewer_septic ?? "waste system unknown"}</p>
              {!archived && <button type="button" onClick={() => setEditingProperty(property)} className="mt-3 text-sm text-blue-400">Edit property</button>}
            </article>
          ))}
        </div>
        {editingProperty && <PropertyForm key={editingProperty === "new" ? "new" : editingProperty.id} property={editingProperty === "new" ? undefined : editingProperty} isSaving={mutations.addProperty.isPending || mutations.updateProperty.isPending} onCancel={() => setEditingProperty(null)} onSubmit={(input) => { setActionError(null); if (editingProperty === "new") mutations.addProperty.mutate(input, { onSuccess: () => setEditingProperty(null), onError: setActionError }); else mutations.updateProperty.mutate({ propertyId: editingProperty.id, input }, { onSuccess: () => setEditingProperty(null), onError: setActionError }); }} />}
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <div className="flex items-center justify-between"><div><p className="text-sm text-blue-400">Customer relationships</p><h3 className="mt-1 text-xl font-semibold">Contacts</h3></div>{!archived && <button type="button" onClick={() => setEditingContact("new")} className="flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm"><Plus size={16} /> Add contact</button>}</div>
        {customer.contacts.length === 0 && editingContact === null && <p className="mt-5 rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-500">No additional contacts have been added.</p>}
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {customer.contacts.map((contact) => (
            <article key={contact.id} className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
              <div className="flex gap-3"><UserRound size={18} className="mt-0.5 text-blue-400" /><div><p className="font-medium">{contact.first_name} {contact.last_name ?? ""}</p><p className="text-sm text-slate-400">{contact.relationship_or_role ?? "Contact"}</p><p className="mt-2 text-sm text-slate-300">{contact.phone ?? contact.email}</p></div></div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">{contact.is_preferred && <span className="rounded-full bg-blue-950 px-2 py-1 text-blue-300">Preferred</span>}{contact.can_approve_work && <span className="rounded-full bg-emerald-950 px-2 py-1 text-emerald-300">May approve work</span>}</div>
              {!archived && <button type="button" onClick={() => setEditingContact(contact)} className="mt-3 text-sm text-blue-400">Edit contact</button>}
            </article>
          ))}
        </div>
        {editingContact && <ContactForm key={editingContact === "new" ? "new" : editingContact.id} contact={editingContact === "new" ? undefined : editingContact} isSaving={mutations.addContact.isPending || mutations.updateContact.isPending} onCancel={() => setEditingContact(null)} onSubmit={(input) => { setActionError(null); if (editingContact === "new") mutations.addContact.mutate(input, { onSuccess: () => setEditingContact(null), onError: setActionError }); else mutations.updateContact.mutate({ contactId: editingContact.id, input }, { onSuccess: () => setEditingContact(null), onError: setActionError }); }} />}
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <p className="text-sm text-blue-400">Internal history</p><h3 className="mt-1 text-xl font-semibold">Notes</h3>
        {!archived && <form onSubmit={addNote} className="mt-5"><textarea value={noteBody} onChange={(event) => setNoteBody(event.target.value)} required maxLength={4000} placeholder="Add operational context for internal staff…" className="min-h-24 w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-sm outline-none focus:border-blue-500" /><div className="mt-2 flex justify-end"><button disabled={mutations.addNote.isPending} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold disabled:opacity-50">{mutations.addNote.isPending ? "Adding…" : "Add note"}</button></div></form>}
        {customer.notes.length === 0 ? <p className="mt-5 rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-500">No internal notes have been added.</p> : <div className="mt-5 space-y-3">{[...customer.notes].sort((a, b) => b.created_at.localeCompare(a.created_at)).map((note) => <article key={note.id} className="rounded-xl border border-slate-800 bg-slate-950/60 p-4"><p className="whitespace-pre-wrap text-sm text-slate-200">{note.body}</p><p className="mt-2 text-xs text-slate-500">{new Date(note.created_at).toLocaleString()} · {note.author_user_id ? "Authenticated user" : "Author unavailable"}</p></article>)}</div>}
      </section>
    </div>
  );
}
