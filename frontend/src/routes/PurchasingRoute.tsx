import { useState, type FormEvent } from "react";
import { useAuth, useHasPermission } from "../auth";
import { usePurchasing, usePurchasingMutations } from "../hooks/usePurchasing";
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

export function PurchasingRoute() {
  const { activeCompany } = useAuth();
  const canRead = useHasPermission("COMPANY_PURCHASING_READ");
  const canManage = useHasPermission("COMPANY_PURCHASING_MANAGE");
  const canApprove = useHasPermission("COMPANY_PURCHASING_APPROVE");
  const canIssue = useHasPermission("COMPANY_PURCHASING_ISSUE");
  const [search, setSearch] = useState("");
  const purchasing = usePurchasing(search || undefined, canRead);
  const mutations = usePurchasingMutations();
  const [vendor, setVendor] = useState({
    id: "",
    version: 0,
    code: "",
    display_name: "",
    legal_name: "",
    contact_reference: "",
  });
  const [order, setOrder] = useState({
    id: "",
    version: 0,
    branch_id: "",
    vendor_id: "",
    po_number: "",
    currency: "USD",
    expected_date: "",
  });
  const [line, setLine] = useState({
    id: "",
    version: 0,
    po_id: "",
    description: "",
    quantity: "1",
    unit: "each",
    unit_cost: "0",
  });
  if (!activeCompany)
    return (
      <Alert variant="danger">
        Select an accessible Company before opening Purchasing.
      </Alert>
    );
  if (!canRead)
    return (
      <Alert variant="danger">You are not authorized to view Purchasing.</Alert>
    );
  const submitVendor = async (event: FormEvent) => {
    event.preventDefault();
    if (vendor.id) {
      await mutations.updateVendor.mutateAsync({
        id: vendor.id,
        input: {
          expected_version: vendor.version,
          display_name: vendor.display_name,
          legal_name: vendor.legal_name || null,
          contact_reference: vendor.contact_reference || null,
          status: "active",
          idempotency_key: crypto.randomUUID(),
        },
      });
    } else {
      await mutations.createVendor.mutateAsync({
        code: vendor.code,
        display_name: vendor.display_name,
        legal_name: vendor.legal_name || null,
        contact_reference: vendor.contact_reference || null,
        idempotency_key: crypto.randomUUID(),
      });
    }
    setVendor({
      id: "",
      version: 0,
      code: "",
      display_name: "",
      legal_name: "",
      contact_reference: "",
    });
  };
  const submitOrder = async (event: FormEvent) => {
    event.preventDefault();
    if (order.id) {
      await mutations.updateOrder.mutateAsync({
        id: order.id,
        input: {
          expected_version: order.version,
          vendor_id: order.vendor_id,
          expected_date: order.expected_date || null,
          idempotency_key: crypto.randomUUID(),
        },
      });
    } else {
      await mutations.createOrder.mutateAsync({
        branch_id: order.branch_id,
        vendor_id: order.vendor_id,
        po_number: order.po_number,
        currency: order.currency,
        expected_date: order.expected_date || null,
        idempotency_key: crypto.randomUUID(),
      });
    }
    setOrder({
      id: "",
      version: 0,
      branch_id: "",
      vendor_id: "",
      po_number: "",
      currency: "USD",
      expected_date: "",
    });
  };
  const submitLine = async (event: FormEvent) => {
    event.preventDefault();
    const po = purchasing.data?.purchase_orders.find(
      (candidate) => candidate.id === line.po_id,
    );
    if (!po) return;
    const input = {
      expected_po_version: po.version,
      description: line.description,
      quantity: line.quantity,
      unit: line.unit,
      unit_cost: line.unit_cost,
      idempotency_key: crypto.randomUUID(),
    };
    if (line.id) {
      await mutations.updateLine.mutateAsync({
        id: po.id,
        lineId: line.id,
        input: { ...input, expected_line_version: line.version },
      });
    } else {
      await mutations.addLine.mutateAsync({ id: po.id, input });
    }
    setLine({
      id: "",
      version: 0,
      po_id: "",
      description: "",
      quantity: "1",
      unit: "each",
      unit_cost: "0",
    });
  };
  const transition = (
    po: NonNullable<typeof purchasing.data>["purchase_orders"][number],
    action: "submit" | "approve" | "issue" | "cancel" | "close",
  ) =>
    mutations.transition.mutateAsync({
      id: po.id,
      action,
      input: {
        expected_version: po.version,
        reason:
          action === "cancel" || action === "close"
            ? "Authorized manual lifecycle action"
            : null,
        idempotency_key: crypto.randomUUID(),
      },
    });
  const failed =
    mutations.createVendor.isError ||
    mutations.updateVendor.isError ||
    mutations.createOrder.isError ||
    mutations.updateOrder.isError ||
    mutations.addLine.isError ||
    mutations.updateLine.isError ||
    mutations.transition.isError;
  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-12">
      <header>
        <p className="text-sm font-semibold text-action-primary">
          Commercial Operations
        </p>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">Purchasing</h1>
        <p className="mt-2 text-content-muted">
          Operational Vendors and controlled purchase orders. Receiving, stock,
          AP, and Accounting remain separate.
        </p>
      </header>
      {failed && (
        <Alert variant="danger">
          Purchasing command failed. Refresh authoritative state before
          retrying.
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Operational Vendors</CardTitle>
          <CardDescription>
            Procurement identity only; no banking, tax, AP liability, or payment
            authority.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Input
            aria-label="Search Vendors"
            placeholder="Search code or name"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          {purchasing.isPending ? (
            <Spinner label="Loading Purchasing" />
          ) : purchasing.isError ? (
            <Alert variant="danger">Purchasing could not be loaded.</Alert>
          ) : (
            <ul className="mt-3 space-y-2">
              {purchasing.data?.vendors.map((item) => (
                <li key={item.id} className="rounded border border-stroke p-3">
                  <strong>{item.code}</strong> — {item.display_name}{" "}
                  <Badge>{item.status}</Badge>
                  {canManage && (
                    <Button
                      className="ml-2"
                      onClick={() =>
                        setVendor({
                          id: item.id,
                          version: item.version,
                          code: item.code,
                          display_name: item.display_name,
                          legal_name: item.legal_name ?? "",
                          contact_reference: item.contact_reference ?? "",
                        })
                      }
                    >
                      Edit
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      {canManage && (
        <Card>
          <CardHeader>
            <CardTitle>
              {vendor.id
                ? "Edit operational Vendor"
                : "Create operational Vendor"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-3 sm:grid-cols-2"
              onSubmit={(event) => void submitVendor(event)}
            >
              <Input
                aria-label="Vendor code"
                required
                disabled={Boolean(vendor.id)}
                value={vendor.code}
                onChange={(event) =>
                  setVendor({ ...vendor, code: event.target.value })
                }
              />
              <Input
                aria-label="Vendor display name"
                required
                value={vendor.display_name}
                onChange={(event) =>
                  setVendor({ ...vendor, display_name: event.target.value })
                }
              />
              <Input
                aria-label="Vendor legal name"
                value={vendor.legal_name}
                onChange={(event) =>
                  setVendor({ ...vendor, legal_name: event.target.value })
                }
              />
              <Input
                aria-label="Safe contact reference"
                value={vendor.contact_reference}
                onChange={(event) =>
                  setVendor({
                    ...vendor,
                    contact_reference: event.target.value,
                  })
                }
              />
              <Button
                type="submit"
                loading={
                  mutations.createVendor.isPending ||
                  mutations.updateVendor.isPending
                }
              >
                {vendor.id ? "Save Vendor" : "Create Vendor"}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
      {canManage && (
        <Card>
          <CardHeader>
            <CardTitle>
              {order.id
                ? "Edit draft Purchase Order"
                : "Create draft Purchase Order"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-3 md:grid-cols-5"
              onSubmit={(event) => void submitOrder(event)}
            >
              <Select
                aria-label="PO Branch"
                required
                disabled={Boolean(order.id)}
                value={order.branch_id}
                onChange={(event) =>
                  setOrder({ ...order, branch_id: event.target.value })
                }
              >
                <option value="">Branch</option>
                {activeCompany.branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name}
                  </option>
                ))}
              </Select>
              <Select
                aria-label="PO Vendor"
                required
                value={order.vendor_id}
                onChange={(event) =>
                  setOrder({ ...order, vendor_id: event.target.value })
                }
              >
                <option value="">Vendor</option>
                {purchasing.data?.vendors
                  .filter((item) => item.status === "active")
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.display_name}
                    </option>
                  ))}
              </Select>
              <Input
                aria-label="PO number"
                required
                disabled={Boolean(order.id)}
                value={order.po_number}
                onChange={(event) =>
                  setOrder({ ...order, po_number: event.target.value })
                }
              />
              <Input
                aria-label="Currency"
                required
                disabled={Boolean(order.id)}
                value={order.currency}
                onChange={(event) =>
                  setOrder({
                    ...order,
                    currency: event.target.value.toUpperCase(),
                  })
                }
              />
              <Input
                aria-label="Expected date"
                type="date"
                value={order.expected_date}
                onChange={(event) =>
                  setOrder({ ...order, expected_date: event.target.value })
                }
              />
              <Button
                type="submit"
                loading={
                  mutations.createOrder.isPending ||
                  mutations.updateOrder.isPending
                }
              >
                {order.id ? "Save draft PO" : "Create draft PO"}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
      {canManage && (
        <Card>
          <CardHeader>
            <CardTitle>
              {line.id ? "Edit draft PO line" : "Add draft PO line"}
            </CardTitle>
            <CardDescription>
              Catalog item is optional; a safe free description is required
              otherwise. Cost is operational evidence, not Accounting truth.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-3 md:grid-cols-5"
              onSubmit={(event) => void submitLine(event)}
            >
              <Select
                aria-label="Draft PO"
                required
                disabled={Boolean(line.id)}
                value={line.po_id}
                onChange={(event) =>
                  setLine({ ...line, po_id: event.target.value })
                }
              >
                <option value="">Purchase Order</option>
                {purchasing.data?.purchase_orders
                  .filter((po) => po.status === "draft")
                  .map((po) => (
                    <option key={po.id} value={po.id}>
                      {po.po_number}
                    </option>
                  ))}
              </Select>
              <Input
                aria-label="Line description"
                required
                value={line.description}
                onChange={(event) =>
                  setLine({ ...line, description: event.target.value })
                }
              />
              <Input
                aria-label="Line quantity"
                type="number"
                min="0.000001"
                step="0.000001"
                required
                value={line.quantity}
                onChange={(event) =>
                  setLine({ ...line, quantity: event.target.value })
                }
              />
              <Input
                aria-label="Line unit"
                required
                value={line.unit}
                onChange={(event) =>
                  setLine({ ...line, unit: event.target.value })
                }
              />
              <Input
                aria-label="Operational unit cost"
                type="number"
                min="0"
                step="0.0001"
                required
                value={line.unit_cost}
                onChange={(event) =>
                  setLine({ ...line, unit_cost: event.target.value })
                }
              />
              <Button
                type="submit"
                loading={
                  mutations.addLine.isPending || mutations.updateLine.isPending
                }
              >
                {line.id ? "Save line" : "Add line"}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Purchase Orders</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-3">
            {purchasing.data?.purchase_orders.map((po) => (
              <li key={po.id} className="rounded border border-stroke p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <strong>{po.po_number}</strong> <Badge>{po.status}</Badge>
                    <p className="text-sm text-content-muted">
                      {po.lines.length} lines · {po.currency}
                      {po.issuance_digest
                        ? ` · issued ${po.issuance_digest.slice(0, 12)}`
                        : ""}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {canManage && po.status === "draft" && (
                      <Button
                        onClick={() =>
                          setOrder({
                            id: po.id,
                            version: po.version,
                            branch_id: po.branch_id,
                            vendor_id: po.vendor_id,
                            po_number: po.po_number,
                            currency: po.currency,
                            expected_date: po.expected_date ?? "",
                          })
                        }
                      >
                        Edit PO
                      </Button>
                    )}
                    {canManage && po.status === "draft" && (
                      <Button onClick={() => void transition(po, "submit")}>
                        Submit
                      </Button>
                    )}
                    {canApprove && po.status === "submitted" && (
                      <Button onClick={() => void transition(po, "approve")}>
                        Approve
                      </Button>
                    )}
                    {canIssue && po.status === "approved" && (
                      <Button onClick={() => void transition(po, "issue")}>
                        Issue
                      </Button>
                    )}
                    {canIssue &&
                      ["draft", "submitted", "approved", "issued"].includes(
                        po.status,
                      ) && (
                        <Button onClick={() => void transition(po, "cancel")}>
                          Cancel
                        </Button>
                      )}
                    {canIssue && po.status === "issued" && (
                      <Button onClick={() => void transition(po, "close")}>
                        Close without receipt
                      </Button>
                    )}
                  </div>
                </div>
                {po.lines.length > 0 && (
                  <ul className="mt-3 space-y-1 text-sm">
                    {po.lines.map((item) => (
                      <li key={item.id}>
                        {item.line_number}. {item.description} — {item.quantity}{" "}
                        {item.unit} @ {item.unit_cost}
                        {canManage && po.status === "draft" && (
                          <Button
                            className="ml-2"
                            onClick={() =>
                              setLine({
                                id: item.id,
                                version: item.version,
                                po_id: po.id,
                                description: item.description,
                                quantity: item.quantity,
                                unit: item.unit,
                                unit_cost: item.unit_cost,
                              })
                            }
                          >
                            Edit line
                          </Button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
