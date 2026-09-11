import { useState, type FormEvent } from "react";
import { ChevronLeft, ChevronRight, Plus, Search, Star } from "lucide-react";
import { Link, useNavigate } from "react-router";

import { getOperatorApiError } from "../../api/errors";
import { useHasPermission } from "../../auth";
import { useCustomerMutations, useCustomerSearch } from "../../hooks/useCustomers";
import { customerDetailPath } from "../../routing/paths";
import { formatCustomerSource, type CustomerInput, type DuplicateMatch } from "../../types/customers";
import { Alert, Button, Card, EmptyState, Input, Spinner } from "../../ui";
import { CustomerForm } from "./CustomerForm";

const PAGE_SIZE = 20;

export function CustomerManagement() {
  const navigate = useNavigate();
  const canManage = useHasPermission("COMPANY_CUSTOMER_MANAGE");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [customerType, setCustomerType] = useState("");
  const [page, setPage] = useState(1);
  const [isCreating, setIsCreating] = useState(false);
  const [duplicateWarnings, setDuplicateWarnings] = useState<DuplicateMatch[]>([]);
  const customers = useCustomerSearch({
    query: search || undefined,
    status: status ? status as "prospect" | "active" | "inactive" : undefined,
    customer_type: customerType ? customerType as "residential" | "commercial" | "municipal" | "hoa" | "property_management" : undefined,
    sort_by: "updated_at",
    sort_direction: "desc",
    page,
    page_size: PAGE_SIZE,
  });
  const mutations = useCustomerMutations();

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    setPage(1);
    setSearch(searchInput.trim());
  };
  const clearFilters = () => {
    setSearchInput(""); setSearch(""); setStatus(""); setCustomerType(""); setPage(1);
  };

  return <div className="space-y-6">
    <section className="flex flex-col items-stretch gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0"><p className="text-sm font-medium text-action-primary">CRM</p><h2 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Customers</h2><p className="mt-2 text-content-muted">Search the admitted Customer roster and continue into locations, contacts, and related work.</p></div>
      {canManage && <Button type="button" onClick={() => { setDuplicateWarnings([]); setIsCreating(true); }} leadingIcon={<Plus size={18} />}>New customer</Button>}
    </section>

    {canManage && isCreating && <Card className="p-ui-4 sm:p-ui-6"><h3 className="text-xl font-semibold">Create customer</h3><p className="mt-1 text-sm text-content-muted">Create the Customer record first, then add Service Locations and Contacts.</p><div className="mt-6"><CustomerForm duplicateWarnings={duplicateWarnings} isSaving={mutations.create.isPending} isCheckingDuplicates={mutations.duplicateCheck.isPending} error={mutations.create.error ?? mutations.duplicateCheck.error} onCancel={() => setIsCreating(false)} onCheckDuplicates={(input) => mutations.duplicateCheck.mutate({ first_name: input.first_name, last_name: input.last_name, business_name: input.business_name, phone: input.primary_phone, email: input.email }, { onSuccess: setDuplicateWarnings })} onSubmit={(input: CustomerInput) => mutations.create.mutate(input, { onSuccess: (result) => { setDuplicateWarnings(result.duplicate_warnings); setIsCreating(false); navigate(customerDetailPath(result.customer.id)); } })} /></div></Card>}

    <Card>
      <div className="border-b border-stroke p-ui-4 sm:p-ui-5">
        <form onSubmit={submitSearch} className="grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_auto_auto_auto]">
          <label className="relative min-w-0"><span className="sr-only">Search customers</span><Search size={18} className="pointer-events-none absolute left-3 top-3 text-content-muted" /><Input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Name, number, contact, phone, email, or address" className="pl-10" /></label>
          <select aria-label="Customer status" className="min-h-11 rounded-lg border border-stroke-strong bg-surface px-3" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">All statuses</option><option value="prospect">Prospect</option><option value="active">Active</option><option value="inactive">Inactive</option></select>
          <select aria-label="Customer type" className="min-h-11 rounded-lg border border-stroke-strong bg-surface px-3" value={customerType} onChange={(event) => { setCustomerType(event.target.value); setPage(1); }}><option value="">All types</option><option value="residential">Residential</option><option value="commercial">Commercial</option><option value="municipal">Municipal</option><option value="hoa">HOA</option><option value="property_management">Property management</option></select>
          <Button type="submit" variant="outline">Search</Button>
        </form>
        {(search || status || customerType) && <Button type="button" variant="ghost" onClick={clearFilters} className="mt-2">Clear roster filters</Button>}
        <p className="mt-3 text-xs text-content-muted">Totals cover Customer records currently admitted to native ACP authority. Migration-held or not-yet-admitted source records are not counted; completeness cannot be inferred from this page.</p>
      </div>

      {customers.isLoading && <div className="flex justify-center p-ui-8"><Spinner label="Loading customers" /></div>}
      {customers.isError && (() => { const error = getOperatorApiError(customers.error, "Customer roster"); return <div className="p-ui-4"><Alert variant="danger" title={error.title} action={error.retryable ? <Button variant="outline" onClick={() => void customers.refetch()}>Retry</Button> : undefined}>{error.message}</Alert></div>; })()}
      {customers.data && customers.data.items.length === 0 && customers.data.total_count > 0 && <EmptyState title="This roster page is no longer available." description="The authoritative result set changed. Return to the first page and refresh the current roster." primaryAction={<Button type="button" variant="outline" onClick={() => setPage(1)}>Return to first page</Button>} />}
      {customers.data && customers.data.items.length === 0 && customers.data.total_count === 0 && <EmptyState title={search || status || customerType ? "No admitted Customers match these filters." : "No Customer records are currently admitted."} description={search || status || customerType ? "Change the search or filters. Records held by Migration are outside this result." : "This is an empty native-authority result, not proof that upstream source data is empty or complete."} />}
      {customers.data && customers.data.items.length > 0 && <div className="divide-y divide-stroke">{customers.data.items.map((customer) => <Link key={customer.id} to={customerDetailPath(customer.id)} className="grid min-h-11 w-full min-w-0 gap-3 p-ui-4 text-left transition hover:bg-surface-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus sm:grid-cols-[1.5fr_1fr_1fr_auto] sm:items-center sm:p-ui-5">
        <div className="min-w-0"><div className="flex min-w-0 items-center gap-2"><p className="break-words font-semibold text-content">{customer.display_name || customer.business_name || `${customer.first_name ?? ""} ${customer.last_name ?? ""}`.trim() || "Unnamed customer"}</p>{customer.is_vip && <Star size={15} className="shrink-0 fill-amber-400 text-amber-400" />}</div><p className="mt-1 break-words text-xs text-content-muted">{customer.customer_number || "Number unavailable"} · {customer.customer_type} · {formatCustomerSource(customer.source)}</p><p className="mt-1 text-xs text-content-muted">Record updated {customer.updated_at ? new Date(customer.updated_at).toLocaleDateString() : "date unavailable"}</p></div>
        <p className="break-words text-sm text-content-secondary">{customer.primary_phone || "No phone"}</p><p className="break-all text-sm text-content-muted">{customer.email ?? "No email"}</p><span className={`w-fit rounded-full px-2.5 py-1 text-xs ${customer.status === "inactive" ? "bg-status-warning/15 text-status-warning" : "bg-status-success/15 text-status-success"}`}>{customer.status.replaceAll("_", " ")}</span>
      </Link>)}</div>}
      {customers.data && customers.data.total_count > 0 && <div className="flex flex-col gap-3 border-t border-stroke p-ui-4 text-sm text-content-muted sm:flex-row sm:items-center sm:justify-between"><span>Showing {(customers.data.page - 1) * customers.data.page_size + 1}–{Math.min(customers.data.page * customers.data.page_size, customers.data.total_count)} of {customers.data.total_count} admitted Customers · page {customers.data.page} of {customers.data.total_pages}</span><div className="flex gap-2"><Button type="button" variant="outline" disabled={page === 1} onClick={() => setPage((value) => Math.max(1, value - 1))} leadingIcon={<ChevronLeft size={16} />}>Previous</Button><Button type="button" variant="outline" disabled={page >= customers.data.total_pages} onClick={() => setPage((value) => value + 1)} trailingIcon={<ChevronRight size={16} />}>Next</Button></div></div>}
    </Card>
  </div>;
}
