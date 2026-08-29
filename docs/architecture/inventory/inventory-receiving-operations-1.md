# Inventory Receiving Operations 1

## Authority boundary

Purchasing remains authoritative for ordered, accepted, rejected, discrepancy,
and return facts. Inventory remains authoritative for physical quantity. An
issued Purchase Order is not stock, a receipt is not a Vendor Bill, and neither
fact is an Accounting posting.

An accepted receipt with an explicit active receiving location composes the two
domains atomically. Each accepted receipt line posts one append-only native
`purchase_receipt` StockMovement. The deterministic movement key and receipt
line provenance prevent replay from incrementing stock twice. A legacy or
evidence-only receipt without a location remains explicitly `pending`; it is
never treated as applied Inventory.

Physical completion of a Purchase Return posts one `purchase_return` movement
against the original receipt location and references the original inbound
movement as its reversal authority. The receipt and Purchasing return histories
remain immutable.

## Cost and reconciliation evidence

Receipt lines snapshot PO unit cost and currency as
`po_cost_evidence_unposted`. This is Purchasing evidence only: no FIFO, LIFO,
weighted-average, AP liability, or General Ledger policy is inferred.

The read-only receiving reconciliation projection reports ordered, accepted,
returned, Inventory-moved, and outstanding quantities per PO line. Until an
authoritative Vendor Bill match exists, bill state is `missing_bill`; missing
bill evidence is never converted to zero or `matched`.

## Fail-closed controls

- Inventory application requires a Company/Branch-bound active location and an
  explicitly mapped Inventory item.
- Accepted quantity cannot exceed PO authority; overage remains discrepancy
  evidence rather than stock.
- PO row locking, command receipts, and movement idempotency serialize receipt
  and return effects.
- Inventory conflicts roll back the entire Purchasing command.
- No receipt or return creates Vendor Bills, AP liability, Journals, Payments,
  Price Book changes, or Economics facts.

## Operator workflow

The existing Purchasing receiving workflow requires an active Inventory
location from the PO Branch, exposes Inventory application state and movement
evidence, disables duplicate submission while pending, and surfaces a safe
fail-closed error. Existing Purchasing receipt/return permissions remain the
authorization authority.
