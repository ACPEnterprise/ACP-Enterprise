import { useState, type FormEvent } from "react";
import { useCycleCounts, useInventoryMutations } from "../hooks/useInventory";
import type { InventoryItem, InventoryLocation } from "../types/inventory";
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
} from "../ui";

interface Props {
  branchId: string;
  items: readonly InventoryItem[];
  locations: readonly InventoryLocation[];
  canAdjust: boolean;
  canCount: boolean;
}

export function InventoryCountAdjustmentWorkbench({
  branchId,
  items,
  locations,
  canAdjust,
  canCount,
}: Props) {
  const counts = useCycleCounts(branchId, Boolean(branchId));
  const mutations = useInventoryMutations();
  const [adjustment, setAdjustment] = useState({
    item_id: "",
    location_id: "",
    reason: "gain",
    quantity_delta: "",
    note: "",
  });
  const [newCount, setNewCount] = useState({ location_id: "", name: "" });
  const [entry, setEntry] = useState({
    session_id: "",
    item_id: "",
    counted_quantity: "",
  });
  const itemName = (id: string) =>
    items.find((item) => item.id === id)?.name ?? id;
  const locationName = (id: string) =>
    locations.find((location) => location.id === id)?.name ?? id;
  const error =
    counts.isError ||
    mutations.adjust.isError ||
    mutations.startCount.isError ||
    mutations.recordCount.isError ||
    mutations.completeCount.isError;

  const submitAdjustment = async (event: FormEvent) => {
    event.preventDefault();
    await mutations.adjust.mutateAsync({
      ...adjustment,
      branch_id: branchId,
      occurred_at: new Date().toISOString(),
      idempotency_key: crypto.randomUUID(),
    });
    setAdjustment({
      item_id: "",
      location_id: "",
      reason: "gain",
      quantity_delta: "",
      note: "",
    });
  };

  const submitCount = async (event: FormEvent) => {
    event.preventDefault();
    const created = await mutations.startCount.mutateAsync({
      ...newCount,
      branch_id: branchId,
      idempotency_key: crypto.randomUUID(),
    });
    setEntry((current) => ({ ...current, session_id: created.id }));
    setNewCount({ location_id: "", name: "" });
  };

  const submitEntry = async (event: FormEvent) => {
    event.preventDefault();
    await mutations.recordCount.mutateAsync({
      id: entry.session_id,
      data: {
        item_id: entry.item_id,
        counted_quantity: entry.counted_quantity,
        counted_at: new Date().toISOString(),
        idempotency_key: crypto.randomUUID(),
      },
    });
    setEntry((current) => ({
      ...current,
      item_id: "",
      counted_quantity: "",
    }));
  };

  return (
    <div className="space-y-6">
      {error && (
        <Alert variant="danger">
          Inventory count or adjustment could not be completed. Refresh
          authoritative state and try again.
        </Alert>
      )}
      {canAdjust && (
        <Card>
          <CardHeader>
            <CardTitle>Post inventory adjustment</CardTitle>
            <CardDescription>
              Post an evidenced correction through the native movement ledger.
              Financial valuation remains separate.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-3 md:grid-cols-6"
              onSubmit={(event) => void submitAdjustment(event)}
            >
              <Select
                aria-label="Adjustment item"
                value={adjustment.item_id}
                onChange={(event) =>
                  setAdjustment({ ...adjustment, item_id: event.target.value })
                }
                required
              >
                <option value="">Item</option>
                {items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </Select>
              <Select
                aria-label="Adjustment location"
                value={adjustment.location_id}
                onChange={(event) =>
                  setAdjustment({
                    ...adjustment,
                    location_id: event.target.value,
                  })
                }
                required
              >
                <option value="">Location</option>
                {locations.map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                  </option>
                ))}
              </Select>
              <Select
                aria-label="Adjustment reason"
                value={adjustment.reason}
                onChange={(event) =>
                  setAdjustment({ ...adjustment, reason: event.target.value })
                }
              >
                <option value="gain">Count gain</option>
                <option value="found">Found stock</option>
                <option value="loss">Count loss</option>
                <option value="damaged">Damage</option>
                <option value="expired">Expired stock</option>
              </Select>
              <Input
                aria-label="Adjustment quantity"
                type="number"
                step="0.000001"
                value={adjustment.quantity_delta}
                onChange={(event) =>
                  setAdjustment({
                    ...adjustment,
                    quantity_delta: event.target.value,
                  })
                }
                required
              />
              <Input
                aria-label="Adjustment note"
                value={adjustment.note}
                onChange={(event) =>
                  setAdjustment({ ...adjustment, note: event.target.value })
                }
                required
              />
              <Button type="submit" loading={mutations.adjust.isPending}>
                Post adjustment
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
      {canCount && (
        <Card>
          <CardHeader>
            <CardTitle>Physical count</CardTitle>
            <CardDescription>
              Preserve observed quantities before a separately authorized
              adjustment is posted.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form
              className="grid gap-3 md:grid-cols-3"
              onSubmit={(event) => void submitCount(event)}
            >
              <Select
                aria-label="Count location"
                value={newCount.location_id}
                onChange={(event) =>
                  setNewCount({ ...newCount, location_id: event.target.value })
                }
                required
              >
                <option value="">Location</option>
                {locations.map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                  </option>
                ))}
              </Select>
              <Input
                aria-label="Count name"
                value={newCount.name}
                onChange={(event) =>
                  setNewCount({ ...newCount, name: event.target.value })
                }
                required
              />
              <Button type="submit" loading={mutations.startCount.isPending}>
                Start count
              </Button>
            </form>
            <form
              className="grid gap-3 md:grid-cols-4"
              onSubmit={(event) => void submitEntry(event)}
            >
              <Select
                aria-label="Open count"
                value={entry.session_id}
                onChange={(event) =>
                  setEntry({ ...entry, session_id: event.target.value })
                }
                required
              >
                <option value="">Open count</option>
                {counts.data
                  ?.filter((count) => count.status === "open")
                  .map((count) => (
                    <option key={count.id} value={count.id}>
                      {count.name}
                    </option>
                  ))}
              </Select>
              <Select
                aria-label="Counted item"
                value={entry.item_id}
                onChange={(event) =>
                  setEntry({ ...entry, item_id: event.target.value })
                }
                required
              >
                <option value="">Item</option>
                {items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </Select>
              <Input
                aria-label="Observed quantity"
                type="number"
                min="0"
                step="0.000001"
                value={entry.counted_quantity}
                onChange={(event) =>
                  setEntry({ ...entry, counted_quantity: event.target.value })
                }
                required
              />
              <Button type="submit" loading={mutations.recordCount.isPending}>
                Record observation
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Physical count history</CardTitle>
          <CardDescription>
            Expected and observed evidence remains visible without granting
            mutation authority.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-3">
            {counts.data?.map((count) => (
              <li
                key={count.id}
                className="rounded-lg border border-stroke p-4"
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <strong>{count.name}</strong> at{" "}
                    {locationName(count.location_id)}
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge>{count.status}</Badge>
                    {canAdjust &&
                      count.status === "open" &&
                      count.entries.length > 0 && (
                        <Button
                          onClick={() =>
                            void mutations.completeCount.mutateAsync({
                              id: count.id,
                              version: count.version,
                            })
                          }
                          loading={mutations.completeCount.isPending}
                        >
                          Complete count
                        </Button>
                      )}
                  </div>
                </div>
                <ul className="mt-2 text-sm text-content-muted">
                  {count.entries.map((observation) => (
                    <li key={observation.id}>
                      {itemName(observation.item_id)}: expected{" "}
                      {observation.expected_quantity}, observed{" "}
                      {observation.counted_quantity}, variance{" "}
                      {observation.variance}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
