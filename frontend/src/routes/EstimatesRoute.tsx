import { useState, type FormEvent } from "react";
import axios from "axios";
import { Link, useSearchParams } from "react-router";
import { useHasPermission } from "../auth";
import {
  useEstimate,
  useEstimateMutations,
  useEstimates,
} from "../hooks/useEstimates";
import { usePriceBook, usePriceBookMutations } from "../hooks/usePriceBook";
import { useCustomerSearch } from "../hooks/useCustomers";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
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
  const [params, setParams] = useSearchParams();
  const canRead = useHasPermission("COMPANY_ESTIMATE_READ");
  const canManage = useHasPermission("COMPANY_ESTIMATE_MANAGE");
  const canReadPriceBook = useHasPermission("COMPANY_PRICE_BOOK_READ");
  const id = params.get("id") ?? "";
  const returnTo = customerReturnPath(params.get("returnTo"));
  const estimate = useEstimate(id, canRead && Boolean(id));
  const mutations = useEstimateMutations();
  const priceBookMutations = usePriceBookMutations();
  const [statusFilter, setStatusFilter] = useState("");
  const estimates = useEstimates(statusFilter || undefined, undefined, canRead);
  const [lookup, setLookup] = useState(id);
  const [form, setForm] = useState({
    branch: "",
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
  const [customerSearch, setCustomerSearch] = useState("");
  const [selectedCustomerLabel, setSelectedCustomerLabel] = useState("");
  const customers = useCustomerSearch({
    query: customerSearch.trim() || undefined,
    sort_by: "display_name",
    sort_direction: "asc",
    record_state: "current",
    page: 1,
    page_size: 25,
  }, canManage);
  const [proposalLines, setProposalLines] = useState<
    Array<{ serviceItem: string; option: string; quantity: string }>
  >([]);
  const priceBook = usePriceBook(
    form.branch || undefined,
    canManage && canReadPriceBook && form.branch.length === 36,
  );

  if (!canRead)
    return (
      <Alert variant="danger">You are not authorized to view Estimates.</Alert>
    );
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const requestedLines = form.serviceItem
        ? [
            ...proposalLines,
            {
              serviceItem: form.serviceItem,
              option: form.option,
              quantity: form.quantity,
            },
          ]
        : proposalLines;
      if (!requestedLines.length) return;
      const lines = [];
      for (const requested of requestedLines) {
        const service = priceBook.data?.service_items.find(
          (item) => item.id === requested.serviceItem,
        );
        if (!service) return;
        const option = priceBook.data?.options.find(
          (candidate) => candidate.id === requested.option,
        );
        const snapshot = await priceBookMutations.snapshot.mutateAsync({
          itemId: service.id,
          data: {
            branch_id: form.branch,
            quantity: requested.quantity,
            currency: "USD",
            effective_at: new Date().toISOString(),
            idempotency_key: `estimate-${crypto.randomUUID()}`,
            option_group_id: option?.option_group_id,
            option_id: option?.id,
          },
        });
        lines.push({
          snapshot_id: snapshot.id,
          title: service.name,
          description: service.customer_description,
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
              onChange={(event) => setStatusFilter(event.target.value)}
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
              <Input
                aria-label="Branch ID"
                value={form.branch}
                onChange={(event) => {
                  setProposalLines([]);
                  setForm({
                    ...form,
                    branch: event.target.value,
                    serviceItem: "",
                    optionGroup: "",
                    option: "",
                  });
                }}
                required
              />
              <label className="grid gap-1 text-sm sm:col-span-2"><span className="font-medium">Customer</span><Input aria-label="Search Customers" placeholder="Search by name, number, phone, or email" value={customerSearch} onChange={(event) => setCustomerSearch(event.target.value)} disabled={customers.isLoading} />{customers.isError && <span className="text-xs text-status-danger">Customer search is unavailable; no selection was changed.</span>}<Select aria-label="Customer" value={form.customer} onChange={(event) => { const selected = customers.data?.items.find((item) => item.id === event.target.value); setForm({ ...form, customer: event.target.value, serviceLocation: "" }); setSelectedCustomerLabel(selected?.display_name || selected?.business_name || `${selected?.first_name ?? ""} ${selected?.last_name ?? ""}`.trim()); }} required disabled={customers.isLoading || customers.isError}><option value="">{customers.isLoading ? "Loading Customers…" : "Select Customer"}</option>{form.customer && !customers.data?.items.some((item) => item.id === form.customer) && <option value={form.customer}>{selectedCustomerLabel || "Selected Customer"}</option>}{customers.data?.items.map((item) => <option key={item.id} value={item.id}>{item.display_name || item.business_name || `${item.first_name ?? ""} ${item.last_name ?? ""}`.trim() || "Unnamed Customer"} · {item.customer_number || "number unavailable"}</option>)}</Select>{customers.data && <span className="text-xs text-content-muted">Showing {customers.data.items.length} of {customers.data.total_count} admitted Customers. Select a result to bind the canonical Customer record.</span>}</label>
              <Input
                aria-label="Service Location ID"
                value={form.serviceLocation}
                onChange={(event) =>
                  setForm({ ...form, serviceLocation: event.target.value })
                }
                placeholder="Required before Job conversion"
              />
              <Select
                aria-label="Customer option set"
                value={form.optionGroup}
                onChange={(event) =>
                  setForm({
                    ...form,
                    optionGroup: event.target.value,
                    option: "",
                    serviceItem: "",
                  })
                }
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
                  {priceBook.data?.service_items
                    .filter(
                      (item) =>
                        item.status === "active" && item.current_version_id,
                    )
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.code} · {item.name}
                      </option>
                    ))}
                </Select>
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
                  setProposalLines([
                    ...proposalLines,
                    {
                      serviceItem: form.serviceItem,
                      option: form.option,
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
                          {
                            priceBook.data?.service_items.find(
                              (item) => item.id === line.serviceItem,
                            )?.name
                          }{" "}
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
