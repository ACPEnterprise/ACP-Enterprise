import { useState, type FormEvent } from "react";
import { ChevronLeft, ChevronRight, Plus, Search, Star } from "lucide-react";

import { getApiErrorMessage } from "../../api/errors";
import { useCustomerList, useCustomerMutations } from "../../hooks/useCustomers";
import type { CustomerInput, DuplicateMatch } from "../../types/customers";
import { Alert, Button, Card, EmptyState, Input, Spinner } from "../../ui";
import { CustomerDetailView } from "./CustomerDetailView";
import { CustomerForm } from "./CustomerForm";

const PAGE_SIZE = 20;

function displayName(customer: { first_name: string | null; last_name: string | null; business_name: string | null }) {
  return "display_name" in customer && typeof customer.display_name === "string" ? customer.display_name : customer.business_name || `${customer.first_name ?? ""} ${customer.last_name ?? ""}`.trim();
}
const label = (value: string | null | undefined) => value ? value.replaceAll("_", " ") : "Unknown";
export function CustomerManagement() {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [duplicateWarnings, setDuplicateWarnings] = useState<DuplicateMatch[]>([]);
  const customers = useCustomerList(search, PAGE_SIZE, offset);
  const mutations = useCustomerMutations();

  if (selectedCustomerId) {
    return <CustomerDetailView customerId={selectedCustomerId} onBack={() => setSelectedCustomerId(null)} />;
  }

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    setOffset(0);
    setSearch(searchInput.trim());
  };

  return (
    <div className="space-y-6">
      <section className="flex flex-col items-stretch gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0"><p className="text-sm font-medium text-action-primary">CRM</p><h2 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Customers</h2><p className="mt-2 text-content-muted">Customer, service-property, contact, and internal service records.</p></div>
        <Button type="button" onClick={() => { setDuplicateWarnings([]); setIsCreating(true); }} leadingIcon={<Plus size={18} />}>New customer</Button>
      </section>

      {isCreating && (
        <Card className="p-ui-4 sm:p-ui-6">
          <h3 className="text-xl font-semibold">Create customer</h3><p className="mt-1 text-sm text-slate-400">Create the customer record first, then add service properties and contacts.</p>
          <div className="mt-6"><CustomerForm duplicateWarnings={duplicateWarnings} isSaving={mutations.create.isPending} isCheckingDuplicates={mutations.duplicateCheck.isPending} error={mutations.create.error ?? mutations.duplicateCheck.error} onCancel={() => setIsCreating(false)} onCheckDuplicates={(input) => mutations.duplicateCheck.mutate({ first_name: input.first_name, last_name: input.last_name, business_name: input.business_name, phone: input.primary_phone, email: input.email }, { onSuccess: setDuplicateWarnings })} onSubmit={(input: CustomerInput) => mutations.create.mutate(input, { onSuccess: (result) => { setDuplicateWarnings(result.duplicate_warnings); setIsCreating(false); setSelectedCustomerId(result.customer.id); } })} /></div>
        </Card>
      )}

      <Card>
        <div className="border-b border-stroke p-ui-4 sm:p-ui-5">
          <form onSubmit={submitSearch} className="grid gap-3 sm:grid-cols-[1fr_auto]">
            <label className="relative min-w-0"><span className="sr-only">Search customers</span><Search size={18} className="pointer-events-none absolute left-3 top-3 text-content-muted" /><Input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search name, phone, email, or street address" className="pl-10" /></label>
            <Button type="submit" variant="outline">Search</Button>
          </form>
          {search && <Button type="button" variant="ghost" onClick={() => { setSearchInput(""); setSearch(""); setOffset(0); }} className="mt-2">Clear search for “{search}”</Button>}
        </div>

        {customers.isLoading && <div className="flex justify-center p-ui-8"><Spinner label="Loading customers" /></div>}
        {customers.isError && <div className="p-ui-4"><Alert variant="danger" title="Unable to load customers" action={<Button variant="outline" onClick={() => void customers.refetch()}>Retry</Button>}>{getApiErrorMessage(customers.error)}</Alert></div>}
        {customers.data && customers.data.items.length === 0 && <EmptyState title={search ? "No customers match this search." : "No customers yet."} description={search ? "Try a different name, phone, email, or address." : "Create the first customer to begin the service record."} />}
        {customers.data && customers.data.items.length > 0 && (
          <div className="divide-y divide-slate-800">
            {customers.data.items.map((customer) => (
              <button key={customer.id} type="button" onClick={() => setSelectedCustomerId(customer.id)} className="grid min-h-11 w-full min-w-0 gap-3 p-ui-4 text-left transition hover:bg-surface-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus sm:grid-cols-[1.5fr_1fr_1fr_auto] sm:items-center sm:p-ui-5">
                <div className="min-w-0"><div className="flex min-w-0 items-center gap-2"><p className="break-words font-semibold text-content">{displayName(customer)}</p>{customer.is_vip && <Star size={15} className="shrink-0 fill-amber-400 text-amber-400" />}</div><p className="mt-1 break-words text-xs text-content-muted">{customer.customer_type} · {label(customer.source)}</p></div>
                <p className="break-words text-sm text-content-secondary">{customer.primary_phone}</p><p className="break-all text-sm text-content-muted">{customer.email ?? "No email"}</p><span className={`w-fit rounded-full px-2.5 py-1 text-xs ${customer.status === "do_not_service" ? "bg-status-danger/15 text-status-danger" : "bg-status-success/15 text-status-success"}`}>{customer.status.replaceAll("_", " ")}</span>
              </button>
            ))}
          </div>
        )}
        {customers.data && customers.data.total > 0 && <div className="flex flex-col gap-3 border-t border-stroke p-ui-4 text-sm text-content-muted sm:flex-row sm:items-center sm:justify-between"><span>Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, customers.data.total)} of {customers.data.total}</span><div className="grid grid-cols-2 gap-2 sm:flex"><Button type="button" variant="outline" aria-label="Previous page" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}><ChevronLeft size={17} /></Button><Button type="button" variant="outline" aria-label="Next page" disabled={offset + PAGE_SIZE >= customers.data.total} onClick={() => setOffset(offset + PAGE_SIZE)}><ChevronRight size={17} /></Button></div></div>}
      </Card>
    </div>
  );
}
