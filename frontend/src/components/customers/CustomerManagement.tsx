import { useState, type FormEvent } from "react";
import { ChevronLeft, ChevronRight, Plus, Search, Star } from "lucide-react";

import { getApiErrorMessage } from "../../api/errors";
import { useCustomerList, useCustomerMutations } from "../../hooks/useCustomers";
import type { CustomerInput, DuplicateMatch } from "../../types/customers";
import { CustomerDetailView } from "./CustomerDetailView";
import { CustomerForm } from "./CustomerForm";

const PAGE_SIZE = 20;

function displayName(customer: { first_name: string | null; last_name: string | null; business_name: string | null }) {
  return customer.business_name || `${customer.first_name ?? ""} ${customer.last_name ?? ""}`.trim();
}
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
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="text-sm font-medium text-blue-400">CRM</p><h2 className="mt-1 text-3xl font-bold tracking-tight">Customers</h2><p className="mt-2 text-slate-400">Customer, service-property, contact, and internal service records.</p></div>
        <button type="button" onClick={() => { setDuplicateWarnings([]); setIsCreating(true); }} className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold"><Plus size={18} /> New customer</button>
      </section>

      {isCreating && (
        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
          <h3 className="text-xl font-semibold">Create customer</h3><p className="mt-1 text-sm text-slate-400">Create the customer record first, then add service properties and contacts.</p>
          <div className="mt-6"><CustomerForm duplicateWarnings={duplicateWarnings} isSaving={mutations.create.isPending} isCheckingDuplicates={mutations.duplicateCheck.isPending} error={mutations.create.error ?? mutations.duplicateCheck.error} onCancel={() => setIsCreating(false)} onCheckDuplicates={(input) => mutations.duplicateCheck.mutate({ first_name: input.first_name, last_name: input.last_name, business_name: input.business_name, phone: input.primary_phone, email: input.email }, { onSuccess: setDuplicateWarnings })} onSubmit={(input: CustomerInput) => mutations.create.mutate(input, { onSuccess: (result) => { setDuplicateWarnings(result.duplicate_warnings); setIsCreating(false); setSelectedCustomerId(result.customer.id); } })} /></div>
        </section>
      )}

      <section className="rounded-2xl border border-slate-800 bg-slate-900">
        <div className="border-b border-slate-800 p-5">
          <form onSubmit={submitSearch} className="flex gap-3">
            <label className="relative flex-1"><span className="sr-only">Search customers</span><Search size={18} className="absolute left-3 top-3 text-slate-500" /><input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search name, phone, email, or street address" className="w-full rounded-xl border border-slate-700 bg-slate-950 py-2.5 pl-10 pr-3 text-sm outline-none focus:border-blue-500" /></label>
            <button className="rounded-xl border border-slate-700 px-4 py-2 text-sm font-medium">Search</button>
          </form>
          {search && <button type="button" onClick={() => { setSearchInput(""); setSearch(""); setOffset(0); }} className="mt-2 text-xs text-blue-400">Clear search for “{search}”</button>}
        </div>

        {customers.isLoading && <div className="p-8 text-slate-400">Loading customers…</div>}
        {customers.isError && <div className="m-5 rounded-xl border border-red-900 bg-red-950/40 p-5 text-red-300">Unable to load customers. {getApiErrorMessage(customers.error)}<button type="button" onClick={() => customers.refetch()} className="ml-2 underline">Retry</button></div>}
        {customers.data && customers.data.items.length === 0 && <div className="p-10 text-center"><p className="font-medium text-slate-300">{search ? "No customers match this search." : "No customers yet."}</p><p className="mt-1 text-sm text-slate-500">{search ? "Try a different name, phone, email, or address." : "Create the first customer to begin the service record."}</p></div>}
        {customers.data && customers.data.items.length > 0 && (
          <div className="divide-y divide-slate-800">
            {customers.data.items.map((customer) => (
              <button key={customer.id} type="button" onClick={() => setSelectedCustomerId(customer.id)} className="grid w-full gap-3 p-5 text-left transition hover:bg-slate-800/50 sm:grid-cols-[1.5fr_1fr_1fr_auto] sm:items-center">
                <div><div className="flex items-center gap-2"><p className="font-semibold text-white">{displayName(customer)}</p>{customer.is_vip && <Star size={15} className="fill-amber-400 text-amber-400" />}</div><p className="mt-1 text-xs text-slate-500">{customer.customer_type} · {customer.source.replaceAll("_", " ")}</p></div>
                <p className="text-sm text-slate-300">{customer.primary_phone}</p><p className="truncate text-sm text-slate-400">{customer.email ?? "No email"}</p><span className={`w-fit rounded-full px-2.5 py-1 text-xs ${customer.status === "do_not_service" ? "bg-red-950 text-red-300" : "bg-emerald-950 text-emerald-300"}`}>{customer.status.replaceAll("_", " ")}</span>
              </button>
            ))}
          </div>
        )}
        {customers.data && customers.data.total > 0 && <div className="flex items-center justify-between border-t border-slate-800 p-4 text-sm text-slate-400"><span>Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, customers.data.total)} of {customers.data.total}</span><div className="flex gap-2"><button type="button" aria-label="Previous page" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} className="rounded-lg border border-slate-700 p-2 disabled:opacity-30"><ChevronLeft size={17} /></button><button type="button" aria-label="Next page" disabled={offset + PAGE_SIZE >= customers.data.total} onClick={() => setOffset(offset + PAGE_SIZE)} className="rounded-lg border border-slate-700 p-2 disabled:opacity-30"><ChevronRight size={17} /></button></div></div>}
      </section>
    </div>
  );
}
