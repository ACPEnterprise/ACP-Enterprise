# Materials, Inventory and Purchasing complete 1 — capability audit

Protected authority inspected: `481ada5dddc7586163bf650556abecc66269a655`.

## Current authoritative chain

| Capability | State | Authority / limitation |
| --- | --- | --- |
| Item master | PARTIAL → OPERATOR_READY in this candidate | Canonical Company SKU, name, stocking unit, fractional policy and lifecycle exist. This candidate exposes replay-safe creation. Description, vendor-product identity, preferred vendor and explicit valuation state remain absent. |
| Price Book expected parts | AUTHORITATIVE_PARTIAL | Versioned material components are embedded in immutable commercial snapshots with code, label and quantity. Component code is not yet bound to Inventory item authority. |
| Estimate lineage | AUTHORITATIVE | Every Estimate line is bound to an immutable Price Book snapshot and digest. Expected components remain snapshot evidence. |
| Job material requirements | PARTIAL → READ_ONLY_READY in this candidate | Estimate conversion now projects version-pinned required material components into Job context. Exact SKU binding, branch stock, allocated reservation, net issue/reversal consumption and shortages are visible. Optional/substitutable policy and automatic reservation remain absent. |
| Locations and truck stock | AUTHORITATIVE | Company/Branch-scoped warehouse, vehicle, staging, in-transit and quarantine locations; external vehicle identity is optional and explicit. |
| Stock truth | AUTHORITATIVE | Immutable movements drive on-hand; reservations drive reserved/available; negative physical stock fails closed. |
| Transfer | AUTHORITATIVE | Atomic source/destination movement covers warehouse ↔ truck. Actor/time and idempotency are retained. |
| Reservation/allocation | AUTHORITATIVE | Demand-bound reservation, partial allocation, release and expiration are separate from issue/consumption. |
| Material issue/reversal | AUTHORITATIVE_BACKEND | Reservation-bound issue and reversal retain item, location, actor, time and optional external source reference. Owner/field product composition remains incomplete. |
| Purchasing | AUTHORITATIVE | Requisition, approval policy, vendor, PO, change control, issue, disposition and document custody exist. |
| Receiving | AUTHORITATIVE | Partial receipt, discrepancy evidence, cost and selected Inventory location compose atomically. |
| Purchase return | AUTHORITATIVE | Governed vendor-return lifecycle exists; it is distinct from unused Job material return. |
| Replenishment | AUTHORITATIVE_REVIEW_ONLY | Evidence-bound recommendations and manual decisions exist. No autonomous purchasing. |
| Cycle count/adjustment | AUTHORITATIVE | Count variance and explicit adjustment are audited; no silent balance edit. |
| Costing | POLICY_REQUIRED | Movements can retain unit cost, currency and valuation method, but no All County valuation policy may be invented. |
| Job cost / Economics | PARTIAL | Economics accepts actual material evidence, but Job consumption lacks an owner-complete workflow joining expected requirement, issue and actual cost. |
| Beacon / Luminary | PARTIAL | Generic operational/economics evidence exists; the named low-stock, missing-required-part and material-variance projections are not complete. |
| Mobile / Dispatch | PARTIAL | A Company/Branch-scoped read-only Job materials contract now exists for authorized Inventory readers. Assignment-scoped Field Tech authorization remains required before Mobile consumption. Dispatch remains read-only for materials. |

## Candidate result

`PUT /api/v1/inventory/items/{code}` creates one canonical Company SKU through
the existing Inventory repository. Repeating the normalized SKU and exact facts
returns the same item. Reusing the SKU with different facts returns a safe
conflict. The ordinary Inventory page exposes SKU, name, stocking unit and
fractional-quantity policy to Inventory managers. It explicitly leaves vendor,
cost and valuation evidence unasserted.

No migration is required. No stock movement, vendor relationship, cost,
Accounting entry, purchase, Customer communication, Preview or Production state
is created by this candidate.

## Job materials projection

`GET /api/v1/inventory/jobs/{job_id}/materials` follows the accepted Estimate
conversion to its immutable Price Book snapshot references. It extracts only
`material` components, multiplies component quantity by the snapshotted service
quantity, and retains every source snapshot ID and digest. It binds an expected
part only when its normalized component code exactly matches the canonical
Inventory SKU; missing codes and missing items remain `SOURCE_REQUIRED`.

The projection reports branch on-hand and available quantities, allocations
reserved specifically for the Job, and net consumption from linked issue and
reversal evidence. The Job page exposes those facts without treating expected
as consumed or a requested reservation as allocated stock. It performs no
mutation and creates no substitute, reservation, purchase, or accounting fact.
