import { useState, type FormEvent } from "react";
import { useAuth, useHasPermission } from "../auth";
import { useInventory, useInventoryMutations } from "../hooks/useInventory";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Select, Spinner } from "../ui";

export function InventoryRoute() {
  const { activeCompany } = useAuth();
  const canRead = useHasPermission("COMPANY_INVENTORY_READ");
  const canMove = useHasPermission("COMPANY_INVENTORY_MOVE");
  const canReserve = useHasPermission("COMPANY_INVENTORY_RESERVE");
  const [branch, setBranch] = useState("");
  const inventory = useInventory(branch || undefined, canRead);
  const mutations = useInventoryMutations();
  const [transfer, setTransfer] = useState({ item_id: "", source_location_id: "", destination_location_id: "", quantity: "" });
  if (!activeCompany) return <Alert variant="danger">Select an accessible Company before opening Inventory.</Alert>;
  if (!canRead) return <Alert variant="danger">You are not authorized to view Inventory.</Alert>;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!branch) return;
    await mutations.transfer.mutateAsync({ ...transfer, branch_id: branch, occurred_at: new Date().toISOString(), idempotency_key: crypto.randomUUID() });
    setTransfer({ item_id: "", source_location_id: "", destination_location_id: "", quantity: "" });
  };
  const itemName = (id: string) => inventory.data?.items.find((item) => item.id === id)?.name ?? id;
  const locationName = (id: string) => inventory.data?.locations.find((location) => location.id === id)?.name ?? id;
  return <div className="mx-auto max-w-6xl space-y-6 pb-10">
    <header><p className="text-sm font-semibold text-action-primary">Operations</p><h1 className="mt-1 text-2xl font-bold sm:text-3xl">Inventory control</h1><p className="mt-2 text-content-muted">Review location balances, move stock atomically, and release controlled reservations.</p></header>
    <Card><CardHeader><CardTitle>Branch scope</CardTitle><CardDescription>Balances and reservations are restricted to authorized Branches.</CardDescription></CardHeader><CardContent><Select aria-label="Inventory Branch" value={branch} onChange={(event) => setBranch(event.target.value)}><option value="">All authorized Branches</option>{activeCompany.branches.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}</Select></CardContent></Card>
    {inventory.isPending ? <Spinner label="Loading Inventory" /> : inventory.isError ? <Alert variant="danger">Inventory could not be loaded.</Alert> : <>
      {canMove && branch && <Card><CardHeader><CardTitle>Transfer stock</CardTitle><CardDescription>One command posts linked source and destination evidence under a single identity.</CardDescription></CardHeader><CardContent><form className="grid gap-3 md:grid-cols-5" onSubmit={(event) => void submit(event)}><Select aria-label="Transfer item" value={transfer.item_id} onChange={(event) => setTransfer({ ...transfer, item_id: event.target.value })} required><option value="">Item</option>{inventory.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select><Select aria-label="Source location" value={transfer.source_location_id} onChange={(event) => setTransfer({ ...transfer, source_location_id: event.target.value })} required><option value="">Source</option>{inventory.data?.locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</Select><Select aria-label="Destination location" value={transfer.destination_location_id} onChange={(event) => setTransfer({ ...transfer, destination_location_id: event.target.value })} required><option value="">Destination</option>{inventory.data?.locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</Select><Input aria-label="Transfer quantity" type="number" min="0.000001" step="0.000001" value={transfer.quantity} onChange={(event) => setTransfer({ ...transfer, quantity: event.target.value })} required /><Button type="submit" loading={mutations.transfer.isPending}>Transfer</Button></form></CardContent></Card>}
      <Card><CardHeader><CardTitle>Location balances</CardTitle></CardHeader><CardContent><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">Item</th><th className="p-2">Location</th><th className="p-2">On hand</th><th className="p-2">Reserved</th><th className="p-2">Available</th></tr></thead><tbody>{inventory.data?.quantities.map((quantity) => <tr key={`${quantity.item_id}:${quantity.location_id}`} className="border-t border-stroke"><td className="p-2">{itemName(quantity.item_id)}</td><td className="p-2">{locationName(quantity.location_id)}</td><td className="p-2">{quantity.on_hand}</td><td className="p-2">{quantity.reserved}</td><td className="p-2 font-semibold">{quantity.available}</td></tr>)}</tbody></table></div></CardContent></Card>
      <Card><CardHeader><CardTitle>Reservations</CardTitle><CardDescription>Requested and allocated claims remain distinct from physical on-hand.</CardDescription></CardHeader><CardContent><ul className="space-y-3">{inventory.data?.reservations.map((reservation) => <li key={reservation.id} className="flex flex-col gap-3 rounded-lg border border-stroke p-4 sm:flex-row sm:items-center sm:justify-between"><div><strong>{itemName(reservation.item_id)}</strong> at {locationName(reservation.location_id)}<div className="mt-1 flex gap-2"><Badge>{reservation.status}</Badge><span>{reservation.allocated_quantity} / {reservation.quantity} {reservation.stocking_unit}</span></div></div>{canReserve && ["requested", "partially_allocated", "allocated"].includes(reservation.status) && <Button onClick={() => void mutations.release.mutateAsync({ id: reservation.id, version: reservation.version })} loading={mutations.release.isPending}>Release</Button>}</li>)}</ul></CardContent></Card>
    </>}
  </div>;
}
