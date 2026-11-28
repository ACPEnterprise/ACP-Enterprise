import { useState, type FormEvent } from "react";
import { ChevronLeft, ChevronRight, Plus, Search, Star } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { getOperatorApiError } from "../../api/errors";
import { useHasPermission } from "../../auth";
import {
  useCustomerMutations,
  useCustomerSearch,
} from "../../hooks/useCustomers";
import { customerDetailPath } from "../../routing/paths";
import { type CustomerInput, type DuplicateMatch } from "../../types/customers";
import { Alert, Button, Card, EmptyState, Input, Spinner } from "../../ui";
import { CustomerForm } from "./CustomerForm";
import { HistoricalCustomerSearch } from "./HistoricalCustomerSearch";

const PAGE_SIZE = 20;

export function CustomerManagement() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryFromUrl = searchParams.get("query") ?? "";
  const canManage = useHasPermission("COMPANY_CUSTOMER_MANAGE");
  const [searchInput, setSearchInput] = useState(queryFromUrl);
  const [search, setSearch] = useState(queryFromUrl);
  const [status, setStatus] = useState("");
  const [customerType, setCustomerType] = useState("");
  const [recordState, setRecordState] = useState<"current" | "archived" | "all">("current");
  const [page, setPage] = useState(1);
  const [isCreating, setIsCreating] = useState(false);
  const [duplicateWarnings, setDuplicateWarnings] = useState<DuplicateMatch[]>([]);

  // Global search can navigate to this already-mounted route. Keep its query
  // authoritative while preserving the existing submit-to-search behavior.
  const [syncedQuery, setSyncedQuery] = useState(queryFromUrl);
  if (queryFromUrl !== syncedQuery) {
    setSyncedQuery(queryFromUrl);
    setSearchInput(queryFromUrl);
    setSearch(queryFromUrl);
    setPage(1);
  }
  const customers = useCustomerSearch({
    query: search || undefined,
    status: status ? status as "prospect" | "active" | "inactive" : undefined,
    customer_type: customerType ? customerType as "residential" | "commercial" | "municipal" | "hoa" | "property_management" : undefined,
    sort_by: "updated_at",
    sort_direction: "desc",
    record_state: recordState,
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
    setSearchInput(""); setSearch(""); setStatus(""); setCustomerType(""); setRecordState("current"); setPage(1);
  };

  return <div className="space-y-6">
    <section className="flex flex-col items-stretch gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0"><p className="text-sm font-medium text-action-primary">CRM</p><h2 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Customers</h2><p className="mt-2 text-content-muted">Search the complete customer directory and open any customer’s service history.</p></div>
      {canManage && <Button type="button" onClick={() => { setDuplicateWarnings([]); setIsCreating(true); }} leadingIcon={<Plus size={18} />}>New Customer</Button>}
    </section>

    {canManage && isCreating && <Card className="p-ui-4 sm:p-ui-6"><h3 className="text-xl font-semibold">Create customer</h3><p className="mt-1 text-sm text-content-muted">Create the Customer record first, then add Service Locations and Contacts.</p><div className="mt-6"><CustomerForm duplicateWarnings={duplicateWarnings} isSaving={mutations.create.isPending} isCheckingDuplicates={mutations.duplicateCheck.isPending} error={mutations.create.error ?? mutations.duplicateCheck.error} onCancel={() => setIsCreating(false)} onCheckDuplicates={(input) => mutations.duplicateCheck.mutate({ first_name: input.first_name, last_name: input.last_name, business_name: input.business_name, phone: input.primary_phone, email: input.email }, { onSuccess: setDuplicateWarnings })} onSubmit={(input: CustomerInput) => mutations.create.mutate(input, { onSuccess: (result) => { setDuplicateWarnings(result.duplicate_warnings); setIsCreating(false); navigate(customerDetailPath(result.customer.id)); } })} /></div></Card>}

    <Card>
      <div className="border-b border-stroke p-ui-4 sm:p-ui-5">
        <form onSubmit={submitSearch} className="flex flex-col gap-3 sm:flex-row">
          <label className="relative min-w-0"><span className="sr-only">Search customers and history</span><Search size={18} className="pointer-events-none absolute left-3 top-3 text-content-muted" /><Input aria-label="Search customers" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Name, number, contact, phone, email, or address" className="pl-10" /></label>
          <Button type="submit" variant="primary">Search</Button>
        </form>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-content-muted">Search name, phone, email, address, or Customer number.</span>
          <details className="relative">
            <summary className="cursor-pointer text-xs font-semibold text-action-primary">More filters</summary>
            <div className="absolute left-0 z-10 mt-2 grid min-w-64 gap-2 rounded-lg border border-stroke bg-surface p-3 shadow-lg">
              <select aria-label="Customer status" className="min-h-10 rounded-lg border border-stroke-strong bg-surface px-3 text-sm" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">All statuses</option><option value="prospect">Prospect</option><option value="active">Active</option><option value="inactive">Inactive</option></select>
              <select aria-label="Customer type" className="min-h-10 rounded-lg border border-stroke-strong bg-surface px-3 text-sm" value={customerType} onChange={(event) => { setCustomerType(event.target.value); setPage(1); }}><option value="">All types</option><option value="residential">Residential</option><option value="commercial">Commercial</option><option value="municipal">Municipal</option><option value="hoa">HOA</option><option value="property_management">Property management</option></select>
              <select aria-label="Customer record state" className="min-h-10 rounded-lg border border-stroke-strong bg-surface px-3 text-sm" value={recordState} onChange={(event) => { setRecordState(event.target.value as "current" | "archived" | "all"); setPage(1); }}><option value="current">Current records</option><option value="archived">Archived records</option><option value="all">Current and archived</option></select>
            </div>
          </details>
          {(search || status || customerType || recordState !== "current") && <Button type="button" variant="ghost" onClick={clearFilters}>Clear filters</Button>}
        </div>
      </div>

      {customers.isLoading && <div className="flex justify-center p-ui-8"><Spinner label="Loading customers" /></div>}
      {customers.isError && (() => { const error = getOperatorApiError(customers.error, "Customer roster"); return <div className="p-ui-4"><Alert variant="danger" title={error.title} action={error.retryable ? <Button variant="outline" onClick={() => void customers.refetch()}>Retry</Button> : undefined}>{error.message}</Alert></div>; })()}
      {customers.data && customers.data.items.length === 0 && customers.data.total_count > 0 && <EmptyState title="This roster page is no longer available." description="The authoritative result set changed. Return to the first page and refresh the current roster." primaryAction={<Button type="button" variant="outline" onClick={() => setPage(1)}>Return to first page</Button>} />}
      {customers.data && customers.data.items.length === 0 && customers.data.total_count === 0 && <EmptyState title={search || status || customerType || recordState !== "current" ? "No Customers match these filters." : "No Customer records are available."} description={search || status || customerType || recordState !== "current" ? "Change the search or filters." : "Customer history may still be importing or reconciling."} />}
      {customers.data && customers.data.items.length > 0 && <div className="divide-y divide-stroke"><div className="hidden grid-cols-[minmax(14rem,1.5fr)_minmax(14rem,1.4fr)_minmax(8rem,1fr)_minmax(12rem,1.2fr)_auto] gap-3 bg-surface-subtle px-ui-4 py-ui-2 text-overline uppercase tracking-wide text-content-muted sm:grid"><span>Customer</span><span>Primary location</span><span>Phone</span><span>Email</span><span>Status</span></div>{customers.data.items.map((customer) => <Link key={customer.id} to={customerDetailPath(customer.id)} className="grid min-h-11 w-full min-w-0 gap-2 p-ui-3 text-left transition hover:bg-surface-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus sm:grid-cols-[minmax(14rem,1.5fr)_minmax(14rem,1.4fr)_minmax(8rem,1fr)_minmax(12rem,1.2fr)_auto] sm:items-center sm:gap-3">
      <div className="min-w-0"><div className="flex min-w-0 items-center gap-2"><p className="truncate font-semibold text-content">{customer.display_name || customer.business_name || `${customer.first_name ?? ""} ${customer.last_name ?? ""}`.trim() || "Name unavailable"}</p>{customer.is_vip && <Star size={15} className="shrink-0 fill-amber-400 text-amber-400" />}</div><p className="mt-1 truncate text-xs text-content-muted">{customer.customer_number || "Number unavailable"} · {customer.customer_type}</p></div>
        <p className="truncate text-sm text-content-secondary">{customer.primary_location ? `${customer.primary_location.address_line_1}, ${customer.primary_location.city}, ${customer.primary_location.state} ${customer.primary_location.postal_code}` : "Location unavailable"}</p><p className="truncate text-sm text-content-secondary">{customer.primary_phone || "No phone"}</p><p className="truncate text-sm text-content-muted">{customer.email ?? "No email"}</p><span className={`w-fit rounded-full px-2.5 py-1 text-xs ${customer.archived_at || customer.status === "inactive" ? "bg-status-warning/15 text-status-warning" : "bg-status-success/15 text-status-success"}`}>{customer.archived_at ? "archived" : customer.status.replaceAll("_", " ")}</span>
      </Link>)}</div>}
      {customers.data && customers.data.total_count > 0 && <div className="flex flex-col gap-3 border-t border-stroke p-ui-4 text-sm text-content-muted sm:flex-row sm:items-center sm:justify-between"><span>Showing {(customers.data.page - 1) * customers.data.page_size + 1}–{Math.min(customers.data.page * customers.data.page_size, customers.data.total_count)} of {customers.data.total_count} Customers · page {customers.data.page} of {customers.data.total_pages}</span><div className="flex gap-2"><Button type="button" variant="outline" disabled={page === 1} onClick={() => setPage((value) => Math.max(1, value - 1))} leadingIcon={<ChevronLeft size={16} />}>Previous</Button><Button type="button" variant="outline" disabled={page >= customers.data.total_pages} onClick={() => setPage((value) => value + 1)} trailingIcon={<ChevronRight size={16} />}>Next</Button></div></div>}
      <HistoricalCustomerSearch query={search} nativeItems={customers.data?.items ?? []} />
    </Card>
  </div>;
}
