import { useState, type FormEvent } from "react";
import { ArrowLeft, Clock3, Edit3, MapPin, Plus, RotateCcw, Star, UserRound } from "lucide-react";

import { getApiErrorMessage, getOperatorApiError } from "../../api/errors";
import { useHasPermission } from "../../auth";
import { useCustomerConsents, useCustomerDetail, useCustomerMutations, useCustomerTimeline } from "../../hooks/useCustomers";
import {
  formatCustomerSource,
  type CustomerContact,
  type CustomerProperty,
  type DuplicateMatch,
} from "../../types/customers";
import {
  Alert,
  Button,
  Card,
  ConfirmationDialog,
  Textarea,
} from "../../ui";
import { ContactForm } from "./ContactForm";
import { CustomerCommunicationHistory } from "./CustomerCommunicationHistory";
import { CustomerOperationsPanel } from "./CustomerOperationsPanel";
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
  const consents = useCustomerConsents(customerId);
  const timeline = useCustomerTimeline(customerId);
  const canReadCommunications = useHasPermission("COMPANY_COMMUNICATIONS_READ");
  const [isEditingCustomer, setIsEditingCustomer] = useState(false);
  const [editingProperty, setEditingProperty] = useState<CustomerProperty | "new" | null>(null);
  const [editingContact, setEditingContact] = useState<CustomerContact | "new" | null>(null);
  const [noteBody, setNoteBody] = useState("");
  const [actionError, setActionError] = useState<unknown>(null);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [consentChannel, setConsentChannel] = useState<"sms" | "email">("sms");
  const [duplicateMatches, setDuplicateMatches] = useState<DuplicateMatch[] | null>(null);

  if (detail.isLoading) {
    return <Card className="p-ui-5 text-content-muted">Loading customer…</Card>;
  }
  if (detail.isError || !detail.data) {
    const error = getOperatorApiError(detail.error, "customer");
    return (
      <Alert
        variant="danger"
        title={error.title}
        action={error.retryable ? <Button type="button" variant="outline" onClick={() => void detail.refetch()}>Retry</Button> : undefined}
      >
        {error.message}
        <Button type="button" variant="ghost" onClick={onBack} className="mt-ui-4">Return to customer list</Button>
      </Alert>
    );
  }

  const customer = detail.data;
  const archived = Boolean(customer.archived_at);
  const latestConsent = (channel: "sms" | "email") =>
    [...(consents.data ?? [])]
      .filter((item) => item.channel === channel)
      .sort((a, b) => b.recorded_at.localeCompare(a.recorded_at))[0];
  const smsConsent = latestConsent("sms");
  const emailConsent = latestConsent("email");

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
      <Button type="button" variant="ghost" onClick={onBack} leadingIcon={<ArrowLeft size={17} />}>Back to customers</Button>

      <Card className="p-ui-4 sm:p-ui-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <h2 className="min-w-0 break-words text-2xl font-bold text-content">{displayName(customer)}</h2>
              {customer.is_vip && <Star size={19} className="fill-amber-400 text-amber-400" aria-label="VIP customer" />}
            </div>
            <p className="mt-2 break-words text-sm text-content-muted">{customer.primary_phone}{customer.email ? ` · ${customer.email}` : ""}</p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <span className="rounded-full bg-slate-800 px-3 py-1 text-content-secondary">{customer.customer_type}</span>
              <span className={`rounded-full px-3 py-1 ${archived ? "bg-red-950 text-red-300" : "bg-emerald-950 text-emerald-300"}`}>{archived ? "archived" : customer.status.replaceAll("_", " ")}</span>
              <span className="rounded-full bg-blue-950 px-3 py-1 text-blue-300">Source: {formatCustomerSource(customer.source)}</span>
            </div>
          </div>
          {!archived ? (
            <div className="grid w-full gap-3 sm:flex sm:w-auto">
              <Button type="button" variant="outline" onClick={() => setIsEditingCustomer(true)} leadingIcon={<Edit3 size={16} />}>Edit</Button>
              <Button
                type="button"
                variant="destructive"
                disabled={mutations.archive.isPending}
                onClick={() => setConfirmArchive(true)}
              >Archive</Button>
            </div>
          ) : (
            <Button
              type="button"
              variant="outline"
              disabled={mutations.restore.isPending}
              onClick={() => mutations.restore.mutate(undefined, { onError: setActionError })}
              leadingIcon={<RotateCcw size={16} />}
            >Restore customer</Button>
          )}
        </div>
        {customer.internal_notes && <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/60 p-4 text-sm text-content-secondary"><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-content-muted">Internal context</p>{customer.internal_notes}</div>}
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
      </Card>

      <CustomerOperationsPanel customerId={customerId} />
      {canReadCommunications && <CustomerCommunicationHistory customerId={customerId} />}

      <Card className="p-ui-4 sm:p-ui-6">
        <p className="text-sm text-action-primary">Identity quality</p>
        <h3 className="mt-1 text-xl font-semibold">Duplicate review</h3>
        <p className="mt-2 text-sm text-content-muted">Compare normalized identity evidence. A match is a review candidate, never an automatic merge.</p>
        <Button
          type="button"
          variant="outline"
          className="mt-4"
          disabled={mutations.duplicateCheck.isPending}
          onClick={() => {
            const primaryProperty = customer.properties.find((item) => item.is_primary) ?? customer.properties[0];
            mutations.duplicateCheck.mutate({
              first_name: customer.first_name,
              last_name: customer.last_name,
              business_name: customer.business_name,
              phone: customer.primary_phone,
              email: customer.email,
              address_line_1: primaryProperty?.address_line_1,
              address_line_2: primaryProperty?.address_line_2,
              city: primaryProperty?.city,
              state: primaryProperty?.state,
              postal_code: primaryProperty?.postal_code,
            }, {
              onSuccess: (matches) => setDuplicateMatches(matches.filter((match) => match.id !== customer.id)),
              onError: setActionError,
            });
          }}
        >{mutations.duplicateCheck.isPending ? "Checking…" : "Check for possible duplicates"}</Button>
        {duplicateMatches !== null && duplicateMatches.length === 0 && <p className="mt-4 text-sm text-content-muted">No other candidate records matched the accepted comparison evidence.</p>}
        <div className="mt-4 space-y-3">
          {(duplicateMatches ?? []).map((match) => (
            <article key={match.id} className="rounded-xl border border-status-warning/40 bg-status-warning/5 p-4">
              <p className="font-medium">{displayName(match)}</p>
              <p className="mt-1 text-sm text-content-muted">{match.primary_phone}{match.email ? ` · ${match.email}` : ""}</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-content-muted">
                {match.reasons.map((reason) => <li key={reason}>{reason.replaceAll("_", " ")}</li>)}
              </ul>
              <p className="mt-3 text-xs font-medium text-status-warning">Native consolidation authority is not available; review only.</p>
            </article>
          ))}
        </div>
      </Card>

      <Card className="p-ui-4 sm:p-ui-6">
        <p className="text-sm text-action-primary">Customer history</p>
        <h3 className="mt-1 text-xl font-semibold">Authoritative timeline</h3>
        {timeline.isError && <Alert variant="danger" title="Timeline unavailable">{getApiErrorMessage(timeline.error)}</Alert>}
        {timeline.isLoading && <p className="mt-4 text-sm text-content-muted">Loading customer history…</p>}
        <ol className="mt-5 space-y-3" aria-label="Customer timeline">
          {(timeline.data?.items ?? []).map((entry) => (
            <li key={entry.id} className="flex gap-3 rounded-xl border border-stroke bg-surface-subtle p-4">
              <Clock3 size={17} className="mt-0.5 shrink-0 text-action-primary" aria-hidden="true" />
              <div className="min-w-0">
                <p className="font-medium text-content">{entry.summary}</p>
                <p className="mt-1 text-xs text-content-muted">
                  {new Date(entry.timestamp).toLocaleString()} · {entry.actor?.display_name ?? "System"}
                </p>
              </div>
            </li>
          ))}
        </ol>
        {timeline.isSuccess && timeline.data.items.length === 0 && <p className="mt-4 text-sm text-content-muted">No authoritative customer events are available.</p>}
      </Card>

      <Card className="p-ui-4 sm:p-ui-6">
        <p className="text-sm text-action-primary">Communication consent</p>
        <h3 className="mt-1 text-xl font-semibold">Consent-safe history</h3>
        <div className="mt-4 grid gap-3 md:grid-cols-2" aria-label="Communication readiness">
          <div className="rounded-xl border border-stroke p-4">
            <p className="font-medium">Email readiness</p>
            <p className="mt-1 text-sm text-content-muted">{!customer.email ? "Missing recipient" : emailConsent?.decision === "granted" ? "Recipient and recorded preference available" : emailConsent?.decision === "withdrawn" ? "Recorded preference unavailable" : "Preference not established"}</p>
          </div>
          <div className="rounded-xl border border-stroke p-4">
            <p className="font-medium">SMS readiness</p>
            <p className="mt-1 text-sm text-content-muted">{!customer.primary_phone ? "Missing recipient" : smsConsent?.decision === "granted" ? "Recipient and recorded preference available" : smsConsent?.decision === "withdrawn" ? "Recorded preference unavailable" : "Preference not established"}</p>
          </div>
        </div>
        {!archived && (
          <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto_auto]">
            <select className="min-h-11 rounded-lg border border-stroke-strong bg-surface px-3" value={consentChannel} onChange={(event) => setConsentChannel(event.target.value as "sms" | "email")} aria-label="Consent channel">
              <option value="sms">SMS</option><option value="email">Email</option>
            </select>
            <Button type="button" disabled={mutations.recordConsent.isPending} onClick={() => mutations.recordConsent.mutate({ channel: consentChannel, decision: "granted", source: "staff_confirmed", reason: null })}>Record consent</Button>
            <Button type="button" variant="outline" disabled={mutations.recordConsent.isPending} onClick={() => mutations.recordConsent.mutate({ channel: consentChannel, decision: "withdrawn", source: "customer_request", reason: null })}>Record withdrawal</Button>
          </div>
        )}
        {consents.isError && <Alert variant="danger" title="Consent history unavailable">{getApiErrorMessage(consents.error)}</Alert>}
        <div className="mt-4 space-y-2">
          {(consents.data ?? []).map((consent) => <div key={consent.id} className="rounded-lg border border-stroke p-3 text-sm"><span className="font-medium uppercase">{consent.channel}</span> · {consent.decision.replaceAll("_", " ")}<p className="mt-1 text-xs text-content-muted">{new Date(consent.recorded_at).toLocaleString()} · {consent.source.replaceAll("_", " ")}</p></div>)}
          {consents.isSuccess && consents.data.length === 0 && <p className="text-sm text-content-muted">No consent decisions have been recorded.</p>}
        </div>
      </Card>

      {Boolean(actionError) && <Alert variant="danger" title="Customer update failed">{getApiErrorMessage(actionError)}</Alert>}

      <Card className="p-ui-4 sm:p-ui-6">
        <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-sm text-action-primary">Service locations</p><h3 className="mt-1 text-xl font-semibold">Properties</h3></div>{!archived && <Button type="button" onClick={() => setEditingProperty("new")} leadingIcon={<Plus size={16} />}>Add property</Button>}</div>
        {customer.properties.length === 0 && editingProperty === null && <p className="mt-5 rounded-xl border border-dashed border-stroke p-5 text-sm text-content-muted">No service properties have been added.</p>}
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {customer.properties.map((property) => (
            <article key={property.id} className="min-w-0 rounded-xl border border-stroke bg-surface-subtle p-4">
              <div className="flex min-w-0 flex-wrap justify-between gap-3"><div className="flex min-w-0 gap-3"><MapPin size={18} className="mt-0.5 shrink-0 text-action-primary" /><div className="min-w-0 break-words"><p className="font-medium">{property.address_line_1}</p>{property.address_line_2 && <p className="text-sm text-content-muted">{property.address_line_2}</p>}<p className="text-sm text-content-muted">{property.city}, {property.state} {property.postal_code}</p></div></div>{property.is_primary && <span className="h-fit rounded-full bg-status-information/15 px-2 py-1 text-xs text-status-information">Primary</span>}</div>
              <p className="mt-3 text-xs text-content-muted">{property.property_type.replaceAll("_", " ")} · {property.sewer_septic ?? "waste system unknown"}</p>
              {!archived && <button type="button" onClick={() => setEditingProperty(property)} className="mt-3 text-sm text-action-primary">Edit property</button>}
            </article>
          ))}
        </div>
        {editingProperty && <PropertyForm key={editingProperty === "new" ? "new" : editingProperty.id} property={editingProperty === "new" ? undefined : editingProperty} isSaving={mutations.addProperty.isPending || mutations.updateProperty.isPending} onCancel={() => setEditingProperty(null)} onSubmit={(input) => { setActionError(null); if (editingProperty === "new") mutations.addProperty.mutate(input, { onSuccess: () => setEditingProperty(null), onError: setActionError }); else mutations.updateProperty.mutate({ propertyId: editingProperty.id, input }, { onSuccess: () => setEditingProperty(null), onError: setActionError }); }} />}
      </Card>

      <Card className="p-ui-4 sm:p-ui-6">
        <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-sm text-action-primary">Customer relationships</p><h3 className="mt-1 text-xl font-semibold">Contacts</h3></div>{!archived && <Button type="button" onClick={() => setEditingContact("new")} leadingIcon={<Plus size={16} />}>Add contact</Button>}</div>
        {customer.contacts.length === 0 && editingContact === null && <p className="mt-5 rounded-xl border border-dashed border-stroke p-5 text-sm text-content-muted">No additional contacts have been added.</p>}
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {customer.contacts.map((contact) => (
            <article key={contact.id} className="min-w-0 rounded-xl border border-stroke bg-surface-subtle p-4">
              <div className="flex min-w-0 gap-3"><UserRound size={18} className="mt-0.5 shrink-0 text-action-primary" /><div className="min-w-0 break-words"><p className="font-medium">{contact.first_name} {contact.last_name ?? ""}</p><p className="text-sm text-content-muted">{contact.relationship_or_role ?? "Contact"}</p><p className="mt-2 break-all text-sm text-content-secondary">{contact.phone ?? contact.email}</p></div></div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">{contact.is_preferred && <span className="rounded-full bg-blue-950 px-2 py-1 text-blue-300">Preferred</span>}{contact.can_approve_work && <span className="rounded-full bg-emerald-950 px-2 py-1 text-emerald-300">May approve work</span>}</div>
              {!archived && <button type="button" onClick={() => setEditingContact(contact)} className="mt-3 text-sm text-action-primary">Edit contact</button>}
            </article>
          ))}
        </div>
        {editingContact && <ContactForm key={editingContact === "new" ? "new" : editingContact.id} contact={editingContact === "new" ? undefined : editingContact} isSaving={mutations.addContact.isPending || mutations.updateContact.isPending} onCancel={() => setEditingContact(null)} onSubmit={(input) => { setActionError(null); if (editingContact === "new") mutations.addContact.mutate(input, { onSuccess: () => setEditingContact(null), onError: setActionError }); else mutations.updateContact.mutate({ contactId: editingContact.id, input }, { onSuccess: () => setEditingContact(null), onError: setActionError }); }} />}
      </Card>

      <Card className="p-ui-4 sm:p-ui-6">
        <p className="text-sm text-action-primary">Internal history</p><h3 className="mt-1 text-xl font-semibold">Notes</h3>
        {!archived && <form onSubmit={addNote} className="mt-5"><Textarea value={noteBody} onChange={(event) => setNoteBody(event.target.value)} required maxLength={4000} placeholder="Add operational context for internal staff…" /><div className="mt-2"><Button fullWidth disabled={mutations.addNote.isPending} loading={mutations.addNote.isPending}>{mutations.addNote.isPending ? "Adding…" : "Add note"}</Button></div></form>}
        {customer.notes.length === 0 ? <p className="mt-5 rounded-xl border border-dashed border-stroke p-5 text-sm text-content-muted">No internal notes have been added.</p> : <div className="mt-5 space-y-3">{[...customer.notes].sort((a, b) => b.created_at.localeCompare(a.created_at)).map((note) => <article key={note.id} className="rounded-xl border border-slate-800 bg-slate-950/60 p-4"><p className="whitespace-pre-wrap text-sm text-slate-200">{note.body}</p><p className="mt-2 text-xs text-content-muted">{new Date(note.created_at).toLocaleString()} · {note.author_user_id ? "Authenticated user" : "Author unavailable"}</p></article>)}</div>}
      </Card>
      {confirmArchive && (
        <ConfirmationDialog
          title="Archive this customer?"
          description="They will be removed from normal search and cannot be edited."
          confirmLabel="Archive customer"
          destructive
          pending={mutations.archive.isPending}
          onCancel={() => setConfirmArchive(false)}
          onConfirm={() => {
            setActionError(null);
            mutations.archive.mutate(undefined, {
              onSuccess: () => setConfirmArchive(false),
              onError: setActionError,
            });
          }}
        >
          <p className="break-words font-semibold">{displayName(customer)}</p>
        </ConfirmationDialog>
      )}
    </div>
  );
}
