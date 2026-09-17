import { useState, type FormEvent } from "react";
import axios from "axios";
import { Link, useSearchParams } from "react-router";
import { useAuth, useHasPermission } from "../auth";
import { useCustomerDetail, useCustomerSearch } from "../hooks/useCustomers";
import {
  useEstimate,
  useEstimateMutations,
  useEstimates,
} from "../hooks/useEstimates";
import { usePriceBook, usePriceBookMutations } from "../hooks/usePriceBook";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Field,
  Input,
  Select,
  Spinner,
} from "../ui";
import { EstimateDecisionControls } from "../components/estimates/EstimateDecisionControls";
import { customerReturnPath } from "../routing/paths";

function money(value: string, currency = "USD") {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
  }).format(Number(value));
}

function estimateRecoveryMessage(error: unknown) {
  if (axios.isAxiosError(error)) {
    const recovery = (
      error.response?.data as { detail?: { recovery?: string } }
    )?.detail?.recovery;
    if (recovery === "RETRY_AFTER_REFRESH")
      return "Estimate authority changed. Refresh before continuing.";
    if (recovery === "USER_CORRECTION_REQUIRED")
      return "Estimate evidence requires correction. Review the retained proposal inputs.";
    if (recovery === "OWNER_ADMIN_ACTION_REQUIRED")
      return "The Estimate requires owner or administrator action before continuing.";
    if (recovery === "TEMPORARILY_UNAVAILABLE")
      return "Estimates are temporarily unavailable. Your proposal inputs were retained.";
  }
  return "The Estimate was not created. Review authoritative state before retrying.";
}

export function EstimatesRoute() {
  const { activeCompany } = useAuth();
  const [params, setParams] = useSearchParams();
  const canRead = useHasPermission("COMPANY_ESTIMATE_READ");
  const canManage = useHasPermission("COMPANY_ESTIMATE_MANAGE");
  const canReadPriceBook = useHasPermission("COMPANY_PRICE_BOOK_READ");
  const canReadCustomers = useHasPermission("COMPANY_CUSTOMER_READ");
  const id = params.get("id") ?? "";
  const returnTo = customerReturnPath(params.get("returnTo"));
  const estimate = useEstimate(id, canRead && Boolean(id));
  const mutations = useEstimateMutations();
  const priceBookMutations = usePriceBookMutations();
  const [statusFilter, setStatusFilter] = useState("");
  const [estimateOffset, setEstimateOffset] = useState(0);
  const estimatePageSize = 25;
  const estimates = useEstimates(
    statusFilter || undefined,
    undefined,
    canRead,
    estimatePageSize,
    estimateOffset,
  );
  const [lookup, setLookup] = useState(id);
  const [form, setForm] = useState({
    branch:
      activeCompany?.default_branch_id ?? activeCompany?.branches[0]?.id ?? "",
    customer: "",
    serviceLocation: "",
    serviceItem: "",
    optionGroup: "",
    option: "",
    quantity: "1",
    title: "",
    customerMessage: "",
    terms: "",
    expiresAt: "",
    discountType: "",
    discountValue: "",
  });
  const [proposalLines, setProposalLines] = useState<
    Array<{
      serviceItem: string;
      serviceName: string;
      customerDescription: string;
      option: string;
      optionGroup?: string;
      optionLabel?: string;
      quantity: string;
    }>
  >([]);
  const [serviceSearch, setServiceSearch] = useState("");
  const [serviceCategory, setServiceCategory] = useState("");
  const [customerSearchInput, setCustomerSearchInput] = useState("");
  const [customerSearch, setCustomerSearch] = useState("");
  const [customerPage, setCustomerPage] = useState(1);
  const customers = useCustomerSearch(
    {
      query: customerSearch || undefined,
      sort_by: "display_name",
      sort_direction: "asc",
      record_state: "current",
      page: customerPage,
      page_size: 25,
    },
    canManage && canReadCustomers,
  );
  const selectedCustomer = useCustomerDetail(
    form.customer || null,
    canManage && canReadCustomers,
  );
  const priceBook = usePriceBook(
    form.branch || undefined,
    canManage && canReadPriceBook && form.branch.length === 36,
    {
      search: serviceSearch.trim() || undefined,
      categoryId: serviceCategory || undefined,
      itemStatus: "active",
    },
  );
  const activeServices =
    priceBook.data?.service_items.filter(
      (item) => item.status === "active" && item.current_version_id,
    ) ?? [];

  if (!canRead)
    return (
      <Alert variant="danger">You are not authorized to view Estimates.</Alert>
    );
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const selectedService = priceBook.data?.service_items.find(
        (item) => item.id === form.serviceItem,
      );
      const selectedOption = priceBook.data?.options.find(
        (option) => option.id === form.option,
      );
      const requestedLines = selectedService
        ? [
            ...proposalLines,
            {
              serviceItem: selectedService.id,
              serviceName: selectedService.name,
              customerDescription: selectedService.customer_description,
              option: selectedOption?.id ?? "",
              optionGroup: selectedOption?.option_group_id,
              optionLabel: selectedOption?.label,
              quantity: form.quantity,
            },
          ]
        : proposalLines;
      if (!requestedLines.length) return;
      const lines = [];
      for (const requested of requestedLines) {
        const snapshot = await priceBookMutations.snapshot.mutateAsync({
          itemId: requested.serviceItem,
          data: {
            branch_id: form.branch,
            quantity: requested.quantity,
            currency: "USD",
            effective_at: new Date().toISOString(),
            idempotency_key: `estimate-${crypto.randomUUID()}`,
            option_group_id: requested.optionGroup,
            option_id: requested.option || undefined,
          },
        });
        lines.push({
          snapshot_id: snapshot.id,
          title: requested.optionLabel
            ? `${requested.optionLabel} · ${requested.serviceName}`
            : requested.serviceName,
          description: requested.customerDescription,
        });
      }
      const created = await mutations.create.mutateAsync({
        branch_id: form.branch,
        customer_id: form.customer,
        service_location_id: form.serviceLocation || undefined,
        proposal_title: form.title || lines[0].title,
        customer_message: form.customerMessage || undefined,
        terms: form.terms || undefined,
        expires_at: form.expiresAt
          ? new Date(form.expiresAt).toISOString()
          : undefined,
        lines,
        discount_type: form.discountType
          ? (form.discountType as "fixed" | "percentage")
          : undefined,
        discount_value: form.discountValue || undefined,
      });
      setProposalLines([]);
      setParams({ id: created.id });
    } catch {
      // React Query retains the governed error; proposal evidence remains editable.
    }
  };
  return (
    <div className="mx-auto max-w-5xl space-y-6 pb-12">
      <header>
        <p className="text-sm font-semibold text-action-primary">
          Sales / Commercial Operations
        </p>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">Estimates</h1>
        <p className="mt-2 text-content-muted">
          Customer-ready proposals backed by immutable Price Book evidence.
        </p>
      </header>
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <CardTitle>Estimate pipeline</CardTitle>
              <CardDescription>
                Select authoritative proposal evidence without copying an
                identifier.
              </CardDescription>
            </div>
            <Select
              aria-label="Estimate status filter"
              value={statusFilter}
              onChange={(event) => {
                setStatusFilter(event.target.value);
                setEstimateOffset(0);
              }}
            >
              <option value="">All states</option>
              <option value="draft">Draft</option>
              <option value="sent">Sent</option>
              <option value="viewed">Viewed</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="expired">Expired</option>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {estimates.isPending ? (
            <Spinner label="Loading Estimate pipeline" />
          ) : estimates.isError ? (
            <Alert variant="danger">
              Estimate pipeline could not be loaded.
            </Alert>
          ) : estimates.data?.items.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[44rem] text-left text-sm">
                <thead className="text-content-muted">
                  <tr>
                    <th className="pb-3">Estimate</th>
                    <th className="pb-3">Proposal</th>
                    <th className="pb-3">State</th>
                    <th className="pb-3 text-right">Total</th>
                    <th className="pb-3">
                      <span className="sr-only">Open</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {estimates.data.items.map((item) => (
                    <tr key={item.id} className="border-t border-stroke">
                      <td className="py-3 font-medium">
                        {item.estimate_number}
                      </td>
                      <td className="py-3">{item.proposal_title}</td>
                      <td className="py-3">
                        <Badge variant="neutral">{item.status}</Badge>
                      </td>
                      <td className="py-3 text-right">
                        {money(item.total_amount, item.currency)}
                      </td>
                      <td className="py-3 text-right">
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => {
                            setLookup(item.id);
                            setParams({ id: item.id });
                          }}
                        >
                          Open
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-content-muted">
                  Showing {estimateOffset + 1}–{Math.min(estimateOffset + estimates.data.items.length, estimates.data.total)} of {estimates.data.total} Estimates.
                </p>
                <div className="flex gap-2">
                  <Button type="button" variant="ghost" disabled={estimateOffset === 0} onClick={() => setEstimateOffset((offset) => Math.max(0, offset - estimatePageSize))}>Previous Estimates</Button>
                  <Button type="button" variant="ghost" disabled={estimateOffset + estimates.data.items.length >= estimates.data.total} onClick={() => setEstimateOffset((offset) => offset + estimatePageSize)}>Next Estimates</Button>
                </div>
              </div>
            </div>
          ) : (
            <p className="rounded-lg border border-dashed border-stroke p-5 text-sm text-content-muted">
              No Estimates match this queue.
            </p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Open by identity</CardTitle>
          <CardDescription>
            Use this recovery path when an Estimate is not in the current queue.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-3 sm:flex-row"
            onSubmit={(event) => {
              event.preventDefault();
              setParams({ id: lookup });
            }}
          >
            <Input
              aria-label="Estimate ID"
              value={lookup}
              onChange={(event) => setLookup(event.target.value)}
              required
            />
            <Button type="submit">Open</Button>
          </form>
        </CardContent>
      </Card>
      {id &&
        (estimate.isPending ? (
          <Spinner label="Loading Estimate" />
        ) : estimate.isError ? (
          <Alert variant="danger">Estimate could not be loaded.</Alert>
        ) : (
          estimate.data && (
            <Card>
              <CardHeader>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm">
                  {returnTo ? <Link className="text-action-primary hover:underline" to={returnTo}>← Back to Customer</Link> : <Link className="text-action-primary hover:underline" to={`/customers/${estimate.data.customer_id}`}>Open Customer</Link>}
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle>
                    {estimate.data.current_revision.proposal_title}
                  </CardTitle>
                  <Badge variant="neutral">{estimate.data.status}</Badge>
                </div>
                <CardDescription>
                  {estimate.data.estimate_number} · Immutable revision{" "}
                  {estimate.data.current_revision.revision_number}
                  {estimate.data.current_revision.expires_at
                    ? ` · Expires ${new Date(estimate.data.current_revision.expires_at).toLocaleDateString()}`
                    : ""}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                {estimate.data.current_revision.customer_message && (
                  <p className="rounded-lg bg-surface-subtle p-4">
                    {estimate.data.current_revision.customer_message}
                  </p>
                )}
                <ul className="space-y-3">
                  {estimate.data.current_revision.lines.map((line) => (
                    <li
                      key={line.id}
                      className="rounded-lg border border-stroke p-4"
                    >
                      <div className="flex justify-between gap-4">
                        <div>
                          <strong>{line.title}</strong>
                          {line.description && (
                            <p className="text-sm text-content-muted">
                              {line.description}
                            </p>
                          )}
                          <p className="text-xs text-content-muted">
                            {line.quantity} × {money(line.unit_price, line.currency)} each
                          </p>
                          {line.option_id && (
                            <p className="text-xs text-content-muted">
                              Selected customer option
                            </p>
                          )}
                        </div>
                        <span>{money(line.line_total, line.currency)}</span>
                      </div>
                    </li>
                  ))}
                </ul>
                <dl className="ml-auto grid max-w-sm grid-cols-2 gap-2 text-right">
                  <dt>Subtotal</dt>
                  <dd>
                    {money(estimate.data.current_revision.subtotal_amount)}
                  </dd>
                  <dt>Discount</dt>
                  <dd>
                    −{money(estimate.data.current_revision.discount_amount)}
                  </dd>
                  <dt>Tax</dt>
                  <dd>{money(estimate.data.current_revision.tax_amount)}</dd>
                  <dt className="font-bold">Total</dt>
                  <dd className="font-bold">
                    {money(estimate.data.current_revision.total_amount)}
                  </dd>
                </dl>
                {estimate.data.current_revision.terms && (
                  <p className="border-t border-stroke pt-4 text-sm text-content-muted">
                    <strong>Terms:</strong>{" "}
                    {estimate.data.current_revision.terms}
                  </p>
                )}
                {estimate.data.customer_decision && (
                  <p className="text-sm text-content-muted">
                    Customer decision recorded for{" "}
                    {estimate.data.customer_decision.customer_name} at{" "}
                    {new Date(
                      estimate.data.customer_decision.occurred_at,
                    ).toLocaleString()}
                    .
                  </p>
                )}
                {canManage && (
                  <EstimateDecisionControls
                    estimate={estimate.data}
                    mutations={mutations}
                  />
                )}
              </CardContent>
            </Card>
          )
        ))}
      {canManage && (
        <Card>
          <CardHeader>
            <CardTitle>Create proposal</CardTitle>
            <CardDescription>
              Build a customer-ready proposal from active services or a governed
              option set. ACP seals every selected line before the Estimate is
              created.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!canReadPriceBook && (
              <Alert variant="danger">
                Price Book read permission is required to select commercial
                services.
              </Alert>
            )}
            {!canReadCustomers && (
              <Alert variant="danger">
                Customer read permission is required to select a Customer and Service Location.
              </Alert>
            )}
            {(mutations.create.isError ||
              priceBookMutations.snapshot.isError) && (
              <Alert variant="danger" role="alert" aria-live="assertive">
                {estimateRecoveryMessage(
                  mutations.create.error ?? priceBookMutations.snapshot.error,
                )}
              </Alert>
            )}
            <form
              className="grid gap-3 sm:grid-cols-2"
              onSubmit={(event) => void submit(event)}
            >
              <Select
                aria-label="Branch"
                value={form.branch}
                onChange={(event) => {
                  setProposalLines([]);
                  setServiceSearch("");
                  setServiceCategory("");
                  setForm({
                    ...form,
                    branch: event.target.value,
                    serviceItem: "",
                    optionGroup: "",
                    option: "",
                  });
                }}
                required
              >
                <option value="">Select Branch</option>
                {activeCompany?.branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name} ({branch.code})
                  </option>
                ))}
              </Select>
              <Field label="Find Customer" helperText="Searches the admitted Customer roster.">
                <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                  <Input
                    aria-label="Find Estimate Customer"
                    value={customerSearchInput}
                    onChange={(event) => setCustomerSearchInput(event.target.value)}
                    placeholder="Name, number, phone, email, or address"
                    disabled={!canReadCustomers}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!canReadCustomers}
                    onClick={() => {
                      setCustomerSearch(customerSearchInput.trim());
                      setCustomerPage(1);
                    }}
                  >
                    Search Customers
                  </Button>
                </div>
              </Field>
              <Field
                label="Customer"
                required
                helperText={customers.isError ? "Customer search is unavailable; no selection was changed." : customers.data ? `Showing ${customers.data.items.length} of ${customers.data.total_count} admitted Customers.` : undefined}
              >
                <Select
                  aria-label="Estimate Customer"
                  value={form.customer}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      customer: event.target.value,
                      serviceLocation: "",
                    })
                  }
                  required
                  disabled={!canReadCustomers || customers.isLoading}
                >
                  <option value="">Select Customer</option>
                  {selectedCustomer.data && !customers.data?.items.some((item) => item.id === selectedCustomer.data.id) && (
                    <option value={selectedCustomer.data.id}>{selectedCustomer.data.display_name || selectedCustomer.data.business_name || "Selected Customer"}</option>
                  )}
                  {customers.data?.items.map((customer) => (
                    <option key={customer.id} value={customer.id}>
                      {customer.display_name || customer.business_name || "Unnamed Customer"}
                    </option>
                  ))}
                </Select>
                <div className="mt-2 flex gap-2">
                  <Button type="button" variant="ghost" disabled={!customers.data || customerPage <= 1} onClick={() => setCustomerPage((page) => Math.max(1, page - 1))}>Previous Customers</Button>
                  <Button type="button" variant="ghost" disabled={!customers.data || customerPage >= customers.data.total_pages} onClick={() => setCustomerPage((page) => page + 1)}>Next Customers</Button>
                </div>
              </Field>
              <Field
                label="Service Location"
                helperText={form.customer && selectedCustomer.data?.properties.length === 0 ? "This Customer has no Service Locations. A location is required before Job conversion." : "Optional for a Draft Estimate; required before Job conversion."}
              >
                <Select
                  aria-label="Estimate Service Location"
                  value={form.serviceLocation}
                  onChange={(event) => setForm({ ...form, serviceLocation: event.target.value })}
                  disabled={!form.customer || selectedCustomer.isLoading}
                >
                  <option value="">No Service Location selected</option>
                  {selectedCustomer.data?.properties.map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.address_line_1}, {location.city}
                    </option>
                  ))}
                </Select>
              </Field>
              <Input
                aria-label="Search active Price Book services"
                placeholder="Search by service name, code, or category"
                value={serviceSearch}
                onChange={(event) => {
                  setServiceSearch(event.target.value);
                  setForm({ ...form, serviceItem: "", option: "" });
                }}
                disabled={!canReadPriceBook || form.branch.length !== 36}
              />
              <Select
                aria-label="Filter active Price Book category"
                value={serviceCategory}
                onChange={(event) => {
                  setServiceCategory(event.target.value);
                  setForm({
                    ...form,
                    serviceItem: "",
                    optionGroup: "",
                    option: "",
                  });
                }}
                disabled={!canReadPriceBook || form.branch.length !== 36}
              >
                <option value="">All service categories</option>
                {priceBook.data?.categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </Select>
              <Select
                aria-label="Customer option set"
                value={form.optionGroup}
                onChange={(event) => {
                  if (event.target.value) {
                    setServiceSearch("");
                    setServiceCategory("");
                  }
                  setForm({
                    ...form,
                    optionGroup: event.target.value,
                    option: "",
                    serviceItem: "",
                  });
                }}
              >
                <option value="">Choose an individual service</option>
                {priceBook.data?.option_groups
                  .filter((group) => group.status === "active")
                  .map((group) => (
                    <option key={group.id} value={group.id}>
                      {group.name}
                    </option>
                  ))}
              </Select>
              {form.optionGroup ? (
                <Select
                  aria-label="Price Book option"
                  value={form.option}
                  onChange={(event) => {
                    const option = priceBook.data?.options.find(
                      (candidate) => candidate.id === event.target.value,
                    );
                    setForm({
                      ...form,
                      option: event.target.value,
                      serviceItem: option?.service_item_id ?? "",
                    });
                  }}
                  required
                >
                  <option value="">Select customer option</option>
                  {priceBook.data?.options
                    .filter(
                      (option) => option.option_group_id === form.optionGroup,
                    )
                    .map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label} ·{" "}
                        {
                          priceBook.data?.service_items.find(
                            (item) => item.id === option.service_item_id,
                          )?.name
                        }
                      </option>
                    ))}
                </Select>
              ) : (
                <Select
                  aria-label="Price Book service"
                  value={form.serviceItem}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      serviceItem: event.target.value,
                      option: "",
                    })
                  }
                  required={proposalLines.length === 0}
                  disabled={!canReadPriceBook || priceBook.isPending}
                >
                  <option value="">
                    {priceBook.isPending
                      ? "Loading Price Book…"
                      : "Select active service"}
                  </option>
                  {activeServices.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.code} · {item.name}
                      </option>
                    ))}
                </Select>
              )}
              {!priceBook.isPending &&
                form.branch.length === 36 &&
                activeServices.length === 0 && (
                  <Alert variant="warning">
                    No active Price Book services match this search and category. Draft and held services must be reviewed and explicitly activated before they can be sold.
                  </Alert>
                )}
              <Input
                aria-label="Quantity"
                type="number"
                min="0.01"
                step="0.01"
                value={form.quantity}
                onChange={(event) =>
                  setForm({ ...form, quantity: event.target.value })
                }
                required
              />
              <Button
                type="button"
                variant="outline"
                disabled={!form.serviceItem}
                onClick={() => {
                  const service = priceBook.data?.service_items.find(
                    (item) => item.id === form.serviceItem,
                  );
                  const selectedOption = priceBook.data?.options.find(
                    (candidate) => candidate.id === form.option,
                  );
                  if (!service) return;
                  setProposalLines([
                    ...proposalLines,
                    {
                      serviceItem: service.id,
                      serviceName: service.name,
                      customerDescription: service.customer_description,
                      option: selectedOption?.id ?? "",
                      optionGroup: selectedOption?.option_group_id,
                      optionLabel: selectedOption?.label,
                      quantity: form.quantity,
                    },
                  ]);
                  setForm({
                    ...form,
                    serviceItem: "",
                    optionGroup: "",
                    option: "",
                    quantity: "1",
                  });
                }}
              >
                Add another service
              </Button>
              {proposalLines.length > 0 && (
                <div className="rounded-lg border border-stroke p-3 text-sm sm:col-span-2">
                  <strong>
                    {proposalLines.length} proposal line
                    {proposalLines.length === 1 ? "" : "s"} staged
                  </strong>
                  <ul className="mt-2 space-y-1">
                    {proposalLines.map((line, index) => (
                      <li
                        key={`${line.serviceItem}-${index}`}
                        className="flex justify-between gap-3"
                      >
                        <span>
                          {line.optionLabel ? `${line.optionLabel} · ` : ""}
                          {line.serviceName}{" "}
                          × {line.quantity}
                        </span>
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() =>
                            setProposalLines(
                              proposalLines.filter(
                                (_, candidate) => candidate !== index,
                              ),
                            )
                          }
                        >
                          Remove
                        </Button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <Input
                aria-label="Proposal title"
                placeholder="Defaults to first service name"
                value={form.title}
                onChange={(event) =>
                  setForm({ ...form, title: event.target.value })
                }
              />
              <Input
                aria-label="Estimate expiration"
                type="datetime-local"
                value={form.expiresAt}
                onChange={(event) =>
                  setForm({ ...form, expiresAt: event.target.value })
                }
              />
              <Input
                aria-label="Customer message"
                placeholder="Problem and proposed solution"
                value={form.customerMessage}
                onChange={(event) =>
                  setForm({ ...form, customerMessage: event.target.value })
                }
              />
              <Input
                aria-label="Terms"
                placeholder="Customer-facing terms"
                value={form.terms}
                onChange={(event) =>
                  setForm({ ...form, terms: event.target.value })
                }
              />
              <Select
                aria-label="Discount type"
                value={form.discountType}
                onChange={(event) =>
                  setForm({ ...form, discountType: event.target.value })
                }
              >
                <option value="">No discount</option>
                <option value="fixed">Fixed amount</option>
                <option value="percentage">Percentage</option>
              </Select>
              <Input
                aria-label="Discount value"
                type="number"
                min="0"
                step="0.01"
                disabled={!form.discountType}
                value={form.discountValue}
                onChange={(event) =>
                  setForm({ ...form, discountValue: event.target.value })
                }
              />
              <Button
                fullWidth
                type="submit"
                disabled={
                  !canReadPriceBook ||
                  !canReadCustomers ||
                  !form.customer ||
                  !form.branch ||
                  (!form.serviceItem && proposalLines.length === 0)
                }
                loading={
                  mutations.create.isPending ||
                  priceBookMutations.snapshot.isPending
                }
              >
                Create immutable Estimate
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
