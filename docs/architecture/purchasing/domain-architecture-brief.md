# Purchasing Domain Architecture Brief

- **Status:** Proposed boundary contract; implementation deferred
- **Release:** Procurement lifecycle after narrow Version 1.0 material capture

Related contracts: [Receiving and Cost Evidence](receiving-and-cost-evidence.md)
and [Inventory, Purchasing, and Accounting Boundary](../financial/inventory-purchasing-accounting-boundary.md).

## Purpose and ownership

Purchasing owns procurement intent and evidence: vendor operational identity,
purchase requisition references when later approved, purchase orders, amendments,
receipts, vendor-return authorization references, and procurement lifecycle.
Inventory owns physical stock effects. Accounting and QuickBooks own accounts
payable, bills, payment, ledger classification, and financial statements.

Purchasing does not own Inventory item identity, stock, Job use, customer pricing,
Invoice/Payment workflows, AP liability, chart of accounts, or journal entries. No
domain writes another domain's tables.

## Aggregates

`Vendor` is Company-owned operational procurement identity with UUID, stable code,
legal/display name, lifecycle, approved contact references, purchasing terms as
non-accounting metadata, external mappings, version, attribution, and timestamps.
It is not a QuickBooks vendor ledger identity; an append-only mapping may relate it.

`PurchaseOrder` owns Company/Branch, PO number, vendor reference/snapshot, ship-to
reference, currency, ordered lines, quantities/units, agreed unit costs, expected
dates, approval evidence, revisions, lifecycle, and concurrency. Lines may reference
Inventory items but snapshot ordered description/unit and never change item identity.

`Receipt` owns immutable receiving evidence against one PO/version: receipt number,
location reference, receiver/time, ordered-line references, received/rejected
quantities and units, packing/evidence references, discrepancies, cost evidence,
corrections, and idempotency identity. Receipt is not an Inventory movement or AP
bill. Corrections are append-only.

## Lifecycle and workflow

Purchase Order lifecycle is `draft`, `submitted`, `approved`, `issued`,
`partially_received`, `received`, `cancelled`, or `closed`. Issued commercial terms
are immutable; changes create an approved revision. Cancellation cannot erase prior
receipt evidence. Repeated issuance and receipt commands are idempotent.

1. Authorized staff select a Vendor and controlled item/description requirements.
2. Purchasing creates and approves a PO under Company/Branch policy.
3. Issuance freezes a version and records delivery evidence without claiming vendor
   acceptance unless such evidence exists.
4. Receiving records actual quantities, rejection, and discrepancy against the
   authoritative issued version.
5. Purchasing asks Inventory to post receipt movements through its public service.
   Inventory validates item/location/unit scope and returns movement identities.
6. Purchasing exposes receiving/cost evidence for controlled AP/QuickBooks handoff.
   Accounting independently establishes any liability; Purchasing never does.

Over-receipt, substitutions, price variance, blind receiving, three-way matching,
and approval thresholds require explicit policy. Until approved, contradictions
fail closed or remain attributed exceptions.

## Reorder and Job demand boundary

Inventory may publish a reorder signal; Jobs may expose unmet requirements. Neither
creates a Purchase Order. Purchasing may consume them as attributed demand inputs,
deduplicate them, and require authorized creation/approval. A PO does not reserve
stock for a Job unless Inventory separately accepts a reservation.

## Security and proposed permissions

All queries and commands enforce Company and authorized Branch scope in repositories.
Vendor bank details, tax identifiers, terms, and costs require restricted handling.
Proposed permissions are:

| Permission | Purpose |
| --- | --- |
| `COMPANY_PURCHASING_READ` | View authorized vendors, orders, and receipts |
| `COMPANY_VENDOR_MANAGE` | Create and maintain operational Vendor identity |
| `COMPANY_PURCHASE_ORDER_MANAGE` | Draft and revise purchase orders |
| `COMPANY_PURCHASE_ORDER_APPROVE` | Approve, issue, cancel, or close orders |
| `COMPANY_PURCHASE_RECEIVE` | Record receipts and discrepancies |
| `COMPANY_PURCHASE_COST_READ` | View restricted procurement cost evidence |

They grant no Inventory adjustment, AP, payment, or accounting authority and are
proposals only.

## Proposed Business Events

Proposed events are `purchasing.vendor_created`,
`purchasing.purchase_order_created`, `purchasing.purchase_order_approved`,
`purchasing.purchase_order_issued`, `purchasing.receipt_recorded`,
`purchasing.receipt_corrected`, and `purchasing.purchase_order_closed`. Safe payloads
contain Company/Branch, aggregate/version IDs, controlled status, counts, currency
when needed, times, and actor IDs. Bank/tax data, unrestricted line descriptions,
credentials, raw documents, and detailed costs are excluded from general events.

## Migration compatibility, risks, and sequence

Imported vendor/PO/receipt facts retain provider identity, source IDs, provenance,
confidence, and completeness. Source status labels do not manufacture ACP approval,
issuance, receipt, or AP evidence. QuickBooks vendor or bill IDs remain mappings,
not Purchasing primary identities. Migrations are additive and preserve Company
isolation and decimal precision.

Risks include duplicate receipts, unit conversion errors, unauthorized cost access,
PO/receipt races, false AP liability, and conflating vendor mappings. Controls are
idempotency identities, row/version locks, issued-version references, append-only
corrections, restricted projections, and explicit accounting handoff state.

Recommended sequence follows Inventory identity: Vendor identity, PO drafts and
approval, immutable issuance, receiving/discrepancy evidence, Inventory receipt
integration, then accounting handoff. Automated replenishment, electronic ordering,
vendor portals, three-way match, returns, and direct QuickBooks transport require
separate milestones.

## Acceptance criteria

The boundary is acceptable when a receipt can truthfully exist without silently
changing stock or AP; Inventory posting and accounting handoff are independently
visible and idempotent; vendors do not become accounting identities by implication;
and every cross-domain effect uses an owned service/event rather than table writes.
