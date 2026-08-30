import { useState, type FormEvent } from "react";
import axios from "axios";
import { useAuth, useHasPermission } from "../auth";
import { InventoryCountAdjustmentWorkbench } from "../components/InventoryCountAdjustmentWorkbench";
import { useInventory, useInventoryMutations } from "../hooks/useInventory";
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

const inventoryRecoveryMessage = (error: unknown) => {
  if (axios.isAxiosError(error)) {
    const recovery = (error.response?.data as {
      detail?: { recovery?: string };
    })?.detail?.recovery;
    if (recovery === "RECONCILIATION_REQUIRED")
      return "Inventory authority is uncertain and requires reconciliation. Do not retry blindly.";
    if (recovery === "TEMPORARILY_UNAVAILABLE")
      return "Inventory is temporarily unavailable. Your inputs were retained for a safe retry.";
    if (recovery === "USER_CORRECTION_REQUIRED")
      return "Inventory evidence requires correction. Review the retained inputs and try again.";
    if (recovery === "TERMINAL_FAILURE")
      return "The Inventory resource is no longer available. Refresh authoritative state before continuing.";
  }
  return "Inventory change could not be completed. Refresh authoritative state and try again.";
};

export function InventoryRoute() {
  const { activeCompany } = useAuth();
  const canRead = useHasPermission("COMPANY_INVENTORY_READ");
  const canManage = useHasPermission("COMPANY_INVENTORY_MANAGE");
  const canMove = useHasPermission("COMPANY_INVENTORY_MOVE");
  const canReserve = useHasPermission("COMPANY_INVENTORY_RESERVE");
  const canAdjust = useHasPermission("COMPANY_INVENTORY_ADJUST");
  const canCount = useHasPermission("COMPANY_INVENTORY_COUNT");
  const [branch, setBranch] = useState("");
  const inventory = useInventory(branch || undefined, canRead);
  const mutations = useInventoryMutations();
  const [location, setLocation] = useState({
    code: "",
    name: "",
    location_type: "warehouse",
  });
  const [transfer, setTransfer] = useState({
    item_id: "",
    source_location_id: "",
    destination_location_id: "",
    quantity: "",
  });
  const [reservation, setReservation] = useState({
    item_id: "",
    location_id: "",
    quantity: "",
    demand_type: "job",
    demand_id: "",
  });
  if (!activeCompany)
    return (
      <Alert variant="danger">
        Select an accessible Company before opening Inventory.
      </Alert>
    );
  if (!canRead)
    return (
      <Alert variant="danger">You are not authorized to view Inventory.</Alert>
    );
  const submitTransfer = async (event: FormEvent) => {
    event.preventDefault();
    if (!branch) return;
    try {
      await mutations.transfer.mutateAsync({
        ...transfer,
        branch_id: branch,
        occurred_at: new Date().toISOString(),
        idempotency_key: crypto.randomUUID(),
      });
      setTransfer({
        item_id: "",
        source_location_id: "",
        destination_location_id: "",
        quantity: "",
      });
    } catch {
      // The governed mutation error is rendered without reflecting backend text.
    }
  };
  const submitLocation = async (event: FormEvent) => {
    event.preventDefault();
    if (!branch) return;
    try {
      await mutations.createLocation.mutateAsync({
        ...location,
        branch_id: branch,
      });
      setLocation({ code: "", name: "", location_type: "warehouse" });
    } catch {
      // Retain the location evidence for correction or retry.
    }
  };
  const submitReservation = async (event: FormEvent) => {
    event.preventDefault();
    if (!branch) return;
    try {
      await mutations.createReservation.mutateAsync({
        ...reservation,
        branch_id: branch,
        idempotency_key: crypto.randomUUID(),
      });
      setReservation({
        item_id: "",
        location_id: "",
        quantity: "",
        demand_type: "job",
        demand_id: "",
      });
    } catch {
      // Retain the reservation evidence for correction or retry.
    }
  };
  const failedMutation = [
    mutations.createLocation,
    mutations.transfer,
    mutations.createReservation,
    mutations.allocate,
    mutations.release,
  ].find((mutation) => mutation.isError);
  const runReservationMutation = async (operation: () => Promise<unknown>) => {
    try {
      await operation();
    } catch {
      // The governed mutation error is announced below.
    }
  };
  const itemName = (id: string) =>
    inventory.data?.items.find((item) => item.id === id)?.name ?? id;
  const locationName = (id: string) =>
    inventory.data?.locations.find((location) => location.id === id)?.name ??
    id;
  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-10">
      <header>
        <p className="text-sm font-semibold text-action-primary">Operations</p>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">
          Inventory control
        </h1>
        <p className="mt-2 text-content-muted">
          Review location balances, move stock atomically, and release
          controlled reservations.
        </p>
      </header>
      <Card>
        <CardHeader>
          <CardTitle>Branch scope</CardTitle>
          <CardDescription>
            Balances and reservations are restricted to authorized Branches.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Select
            aria-label="Inventory Branch"
            value={branch}
            onChange={(event) => setBranch(event.target.value)}
          >
            <option value="">All authorized Branches</option>
            {activeCompany.branches.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {candidate.name}
              </option>
            ))}
          </Select>
        </CardContent>
      </Card>
      {inventory.isPending ? (
        <Spinner label="Loading Inventory" />
      ) : inventory.isError ? (
        <Alert variant="danger">Inventory could not be loaded.</Alert>
      ) : (
        <>
          {failedMutation && (
            <Alert variant="danger" role="alert" aria-live="assertive">
              {inventoryRecoveryMessage(failedMutation.error)}
            </Alert>
          )}
          {canManage && branch && (
            <Card>
              <CardHeader>
                <CardTitle>Create stock location</CardTitle>
                <CardDescription>
                  Add an operational location inside the selected authorized
                  Branch.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form
                  className="grid gap-3 md:grid-cols-4"
                  onSubmit={(event) => void submitLocation(event)}
                >
                  <Input
                    aria-label="Location code"
                    value={location.code}
                    onChange={(event) =>
                      setLocation({ ...location, code: event.target.value })
                    }
                    required
                  />
                  <Input
                    aria-label="Location name"
                    value={location.name}
                    onChange={(event) =>
                      setLocation({ ...location, name: event.target.value })
                    }
                    required
                  />
                  <Select
                    aria-label="Location type"
                    value={location.location_type}
                    onChange={(event) =>
                      setLocation({
                        ...location,
                        location_type: event.target.value,
                      })
                    }
                  >
                    <option value="warehouse">Warehouse</option>
                    <option value="vehicle">Vehicle</option>
                    <option value="staging">Staging</option>
                    <option value="in_transit">In transit</option>
                    <option value="quarantine">Quarantine</option>
                  </Select>
                  <Button
                    type="submit"
                    loading={mutations.createLocation.isPending}
                  >
                    Create location
                  </Button>
                </form>
              </CardContent>
            </Card>
          )}
          {canMove && branch && (
            <Card>
              <CardHeader>
                <CardTitle>Transfer stock</CardTitle>
                <CardDescription>
                  One command posts linked source and destination evidence under
                  a single identity.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form
                  className="grid gap-3 md:grid-cols-5"
                  onSubmit={(event) => void submitTransfer(event)}
                >
                  <Select
                    aria-label="Transfer item"
                    value={transfer.item_id}
                    onChange={(event) =>
                      setTransfer({ ...transfer, item_id: event.target.value })
                    }
                    required
                  >
                    <option value="">Item</option>
                    {inventory.data?.items.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                  <Select
                    aria-label="Source location"
                    value={transfer.source_location_id}
                    onChange={(event) =>
                      setTransfer({
                        ...transfer,
                        source_location_id: event.target.value,
                      })
                    }
                    required
                  >
                    <option value="">Source</option>
                    {inventory.data?.locations.map((location) => (
                      <option key={location.id} value={location.id}>
                        {location.name}
                      </option>
                    ))}
                  </Select>
                  <Select
                    aria-label="Destination location"
                    value={transfer.destination_location_id}
                    onChange={(event) =>
                      setTransfer({
                        ...transfer,
                        destination_location_id: event.target.value,
                      })
                    }
                    required
                  >
                    <option value="">Destination</option>
                    {inventory.data?.locations.map((location) => (
                      <option key={location.id} value={location.id}>
                        {location.name}
                      </option>
                    ))}
                  </Select>
                  <Input
                    aria-label="Transfer quantity"
                    type="number"
                    min="0.000001"
                    step="0.000001"
                    value={transfer.quantity}
                    onChange={(event) =>
                      setTransfer({ ...transfer, quantity: event.target.value })
                    }
                    required
                  />
                  <Button type="submit" loading={mutations.transfer.isPending}>
                    Transfer
                  </Button>
                </form>
              </CardContent>
            </Card>
          )}
          {canReserve && branch && (
            <Card>
              <CardHeader>
                <CardTitle>Create reservation</CardTitle>
                <CardDescription>
                  Reserve an item for an authoritative demand reference without
                  changing physical on-hand.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form
                  className="grid gap-3 md:grid-cols-6"
                  onSubmit={(event) => void submitReservation(event)}
                >
                  <Select
                    aria-label="Reservation item"
                    value={reservation.item_id}
                    onChange={(event) =>
                      setReservation({
                        ...reservation,
                        item_id: event.target.value,
                      })
                    }
                    required
                  >
                    <option value="">Item</option>
                    {inventory.data?.items.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                  <Select
                    aria-label="Reservation location"
                    value={reservation.location_id}
                    onChange={(event) =>
                      setReservation({
                        ...reservation,
                        location_id: event.target.value,
                      })
                    }
                    required
                  >
                    <option value="">Location</option>
                    {inventory.data?.locations.map((candidate) => (
                      <option key={candidate.id} value={candidate.id}>
                        {candidate.name}
                      </option>
                    ))}
                  </Select>
                  <Input
                    aria-label="Reservation quantity"
                    type="number"
                    min="0.000001"
                    step="0.000001"
                    value={reservation.quantity}
                    onChange={(event) =>
                      setReservation({
                        ...reservation,
                        quantity: event.target.value,
                      })
                    }
                    required
                  />
                  <Input
                    aria-label="Demand type"
                    value={reservation.demand_type}
                    onChange={(event) =>
                      setReservation({
                        ...reservation,
                        demand_type: event.target.value,
                      })
                    }
                    required
                  />
                  <Input
                    aria-label="Demand ID"
                    value={reservation.demand_id}
                    onChange={(event) =>
                      setReservation({
                        ...reservation,
                        demand_id: event.target.value,
                      })
                    }
                    required
                  />
                  <Button
                    type="submit"
                    loading={mutations.createReservation.isPending}
                  >
                    Create reservation
                  </Button>
                </form>
              </CardContent>
            </Card>
          )}
          <Card>
            <CardHeader>
              <CardTitle>Location balances</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr>
                      <th className="p-2">Item</th>
                      <th className="p-2">Location</th>
                      <th className="p-2">On hand</th>
                      <th className="p-2">Reserved</th>
                      <th className="p-2">Available</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inventory.data?.quantities.map((quantity) => (
                      <tr
                        key={`${quantity.item_id}:${quantity.location_id}`}
                        className="border-t border-stroke"
                      >
                        <td className="p-2">{itemName(quantity.item_id)}</td>
                        <td className="p-2">
                          {locationName(quantity.location_id)}
                        </td>
                        <td className="p-2">{quantity.on_hand}</td>
                        <td className="p-2">{quantity.reserved}</td>
                        <td className="p-2 font-semibold">
                          {quantity.available}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Reservations</CardTitle>
              <CardDescription>
                Requested and allocated claims remain distinct from physical
                on-hand.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3">
                {inventory.data?.reservations.map((reservation) => (
                  <li
                    key={reservation.id}
                    className="flex flex-col gap-3 rounded-lg border border-stroke p-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div>
                      <strong>{itemName(reservation.item_id)}</strong> at{" "}
                      {locationName(reservation.location_id)}
                      <div className="mt-1 flex gap-2">
                        <Badge>{reservation.status}</Badge>
                        <span>
                          {reservation.allocated_quantity} /{" "}
                          {reservation.quantity} {reservation.stocking_unit}
                        </span>
                      </div>
                    </div>
                    {canReserve &&
                      [
                        "requested",
                        "partially_allocated",
                        "allocated",
                      ].includes(reservation.status) && (
                        <div className="flex gap-2">
                          {["requested", "partially_allocated"].includes(
                            reservation.status,
                          ) && (
                            <Button
                              onClick={() =>
                                void runReservationMutation(() =>
                                  mutations.allocate.mutateAsync({
                                    id: reservation.id,
                                    data: {
                                      quantity: null,
                                      allow_partial: true,
                                      expected_version: reservation.version,
                                      idempotency_key: crypto.randomUUID(),
                                    },
                                  }),
                                )
                              }
                              loading={mutations.allocate.isPending}
                            >
                              Allocate available
                            </Button>
                          )}
                          <Button
                            onClick={() =>
                              void runReservationMutation(() =>
                                mutations.release.mutateAsync({
                                  id: reservation.id,
                                  version: reservation.version,
                                }),
                              )
                            }
                            loading={mutations.release.isPending}
                          >
                            Release
                          </Button>
                        </div>
                      )}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          {branch && (
            <InventoryCountAdjustmentWorkbench
              branchId={branch}
              items={inventory.data?.items ?? []}
              locations={inventory.data?.locations ?? []}
              canAdjust={canAdjust}
              canCount={canCount}
            />
          )}
        </>
      )}
    </div>
  );
}
