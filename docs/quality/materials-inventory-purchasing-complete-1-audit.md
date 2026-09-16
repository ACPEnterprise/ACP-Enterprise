# Materials, Inventory and Purchasing complete 1 — capability audit

Protected authority inspected: `481ada5dddc7586163bf650556abecc66269a655`.

## Current authoritative chain

| Capability | State | Authority / limitation |
| --- | --- | --- |
| Item master | PARTIAL → OPERATOR_READY in this candidate | Canonical Company SKU, name, stocking unit, fractional policy and lifecycle exist. This candidate exposes replay-safe creation. Description, vendor-product identity, preferred vendor and explicit valuation state remain absent. |
| Price Book expected parts | AUTHORITATIVE_PARTIAL | Versioned material components are embedded in immutable commercial snapshots with code, label and quantity. Component code is not yet bound to Inventory item authority. |
| Estimate lineage | AUTHORITATIVE | Every Estimate line is bound to an immutable Price Book snapshot and digest. Expected components remain snapshot evidence. |
| Job material requirements | ABSENT | Estimate conversion preserves snapshot lineage but does not create/query a Job requirement projection. Expected, optional, substitutable and shortage state therefore remain unavailable. |
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
| Mobile / Dispatch | CONTRACT_REQUIRED | No assignment-scoped Job materials projection exists. Dispatch must remain read-only for materials. |

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
