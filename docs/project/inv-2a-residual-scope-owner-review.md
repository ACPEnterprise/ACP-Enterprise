<!-- markdownlint-disable MD013 -->

# INV.2A residual-scope owner review

**Review milestone:** `INV.2A.REVIEW`  
**Authoritative Enterprise evidence:** `a76be4f1de0dae6fdcce00f77509381127de43e8`  
**Integrated Inventory foundations:** `2389af0415161fd685c3c73b8751df2ad440f701`, `303548a7ecba9bc8b5a788237cc3a81a233c0d48`, `d892cf96249083908317bc814f6b460940a91def`, `9c2b114cb658be0454bbb36bdf0e5929ecc7e0e5`  
**Alembic head at review:** `u6k8f0h2j497` (one head)

## Decision requested

Approve the **recommended residual scope** below and explicitly defer opening-balance
completeness policy. Approval authorizes only the missing Inventory interface and
acceptance-evidence closure; it does not authorize Purchasing, roadmap INV.3 Job
consumption, valuation policy, or a schema change.

If approved and accepted after implementation, INV.2A is complete and `PUR.1`
becomes dependency-ready. Approval does not start `PUR.1`.

## Original intent and governing contracts

The [Version 1 implementation roadmap](version-1-implementation-roadmap.md) defines
INV.2A as the remaining location/on-hand, reservation, and transfer workflows not
delivered by INV.2, with Inventory services, APIs, UI, events, and concurrency
evidence. Its dependencies are INV.2 and OPS.1. The
[MMQ.7 queue](five-day-continuous-production-plan.md) narrows the work further to
residual location/on-hand, reservation, release, and transfer workflows not already
delivered by INV.2 or INV.3-LEGACY. It excludes duplicate legacy scope, roadmap
INV.3 Job consumption, Purchasing, Invoicing, and costing/economics.

The approved architecture is recorded by the
[master milestone queue](master-milestone-queue.md) at immutable commit
`dd4a620aa93e209fee813f556bebefe9946cb12a`. Its documents are not merged into
the current Enterprise tree, so the paths below are commit-qualified evidence,
not relative links. It establishes these controlling rules:

- `dd4a620:docs/architecture/inventory/domain-architecture-brief.md`:
  Inventory alone owns physical item identity, location custody, stock movements,
  reservations, and quantity projections; Jobs supplies stable demand references.
- `dd4a620:docs/architecture/inventory/item-and-location-identity.md`:
  item and location identities are Company-compatible, units are decimal, and an
  item's stocking unit becomes immutable after movement.
- `dd4a620:docs/architecture/financial/inventory-purchasing-accounting-boundary.md`:
  Purchasing may request an Inventory-owned movement through an application
  contract but never writes Inventory tables; operational cost is not accounting.
- `dd4a620:docs/architecture/inventory/job-material-consumption.md`:
  Jobs owns requirement and actual-use facts while Inventory independently owns
  reservation and stock movement. Roadmap INV.3 Job consumption is not INV.2A.

INV.2 (`303548a`) and OPS.1 (`c893965`) are integrated. INV.3-LEGACY (`d892cf9`)
and the current stock-control interface (`9c2b114`) are also integrated. The roadmap
dependencies are therefore satisfied; the remaining blocker is this owner-reviewed
scope decision recorded by the durable scheduler manifest.

## Capability matrix

| INV.2A requirement | Classification | Repository evidence | Reconciliation result |
| --- | --- | --- | --- |
| Company-owned Inventory item identity and immutable stocking unit | ALREADY DELIVERED | `backend/app/inventory/models.py` (`InventoryItem`); `contracts.py`; `repository.py`; `test_inventory_foundation.py`; migration `s4i6d8f0h275`; commit `2389af0` | Reuse without redesign. |
| Branch-scoped warehouse, vehicle, staging, in-transit, and quarantine locations | ALREADY DELIVERED | `StockLocation` model and constraints; create/get/list repository methods; `POST /api/v1/inventory/locations`; migration `s4i6d8f0h275`; commits `2389af0`, `9c2b114` | Persistence and API exist. |
| Location creation in the launch UI | NOT DELIVERED | `frontend/src/routes/InventoryRoute.tsx` shows Branch scope, balances, transfer, and release but has no location form | Small UI residual; backend duplication is unnecessary. |
| Append-only movement journal and quantity projection | ALREADY DELIVERED | `StockMovement`, `InventoryQuantity`; `post_movement` and reconciliation methods; immutable database trigger; `test_inventory_foundation.py`; migration `s4i6d8f0h275`; commit `2389af0` | Authoritative stock core exists. |
| Branch-scoped on-hand/reserved/available query and UI | ALREADY DELIVERED | repository list/get quantity; `GET /api/v1/inventory/overview`; `InventoryRoute.tsx`; `test_inventory_application.py`; commit `9c2b114` | No new projection is warranted. |
| Atomic transfer as one identity with source/destination effects | ALREADY DELIVERED | movement type `transfer`; `post_movement`; `POST /api/v1/inventory/transfers`; `inventory.transfer_posted`; `test_transfer_is_one_evidence_record_and_two_quantity_changes` and application transfer test; commits `2389af0`, `9c2b114` | No pair of unrelated movements should be added. |
| Transfer authorization and tenant/Branch isolation | ALREADY DELIVERED | `InventoryService._branch`; authorization dependencies in `router.py`; Company/Branch predicates and composite constraints; foundation/application isolation tests; commit `9c2b114` | Reuse current fail-closed boundary. |
| Reservation creation and availability separation | ALREADY DELIVERED | `InventoryReservation`; create/get/list repository methods; `POST /api/v1/inventory/reservations`; migration `s4i6d8f0h275` evolved by `u6k8f0h2j497`; commits `2389af0`, `d892cf9`, `9c2b114` | Backend workflow exists. |
| Reservation allocation, partial allocation, locking, and stale-version control | ALREADY DELIVERED | `ReservationAllocation`; `allocate_reservation`; allocation API; `test_reservation_allocation_material_issue.py`, including concurrent allocation; migration `u6k8f0h2j497`; commit `d892cf9` | This is INV.3-LEGACY behavior and must not be reimplemented. |
| Reservation release and idempotent lifecycle evidence | ALREADY DELIVERED | transition/release repository methods; lifecycle events table; release API; `inventory.reservation_released`; foundation and INV.3 tests; commits `d892cf9`, `9c2b114` | Preserve current versioned transition. |
| Reservation creation/allocation in the launch UI | NOT DELIVERED | backend endpoints exist, but `InventoryRoute.tsx` only lists and releases reservations | Small UI residual; material issue UI remains excluded. |
| Business Events for residual application workflows | ALREADY DELIVERED | `inventory.location_created`, `inventory.transfer_posted`, `inventory.reservation_created`, `inventory.reservation_released` in `events/types.py`; staged transactionally by `InventoryService`; commit `9c2b114` | Allocation has durable Inventory lifecycle evidence; adding duplicate events is not required by the architecture event list. |
| Explicit Inventory permissions and launch-role access | ALREADY DELIVERED | `InventoryPermission` READ/MANAGE/MOVE/RESERVE; permission catalog; launch role matrix; route dependencies; commit `9c2b114` | COUNT/ADJUST are architecture extension permissions and are not required to duplicate accepted INV.2 behavior here. |
| Adjustments, cycle counts, correction audit | ALREADY DELIVERED | adjustment and cycle-count models/repository; append-only correction evidence; `test_inventory_adjustments.py`, `test_cycle_counts.py`; migration `t5j7e9g1i386`; commit `303548a` | Accepted INV.2 scope; exclude from residual implementation. |
| Material issue/reversal and issued quantity | SUPERSEDED | `MaterialIssue`, issue/reversal repository methods and tests; migration `u6k8f0h2j497`; commit `d892cf9` | Delivered by INV.3-LEGACY; never duplicate in INV.2A. |
| Full authorized API acceptance coverage | PARTIALLY DELIVERED | repository tests are extensive and `test_inventory_application.py` covers overview/transfer/isolation, but no focused router test exercises permission denial plus location/reservation/allocation/release endpoints | Add tests, not new runtime semantics. |
| Frontend acceptance coverage | NOT DELIVERED | no Inventory API, hook, or route test exists; global frontend regression proves compilation only | Add focused UI/API tests for the residual workflow. |
| Opening-balance completeness state | PARTIALLY DELIVERED / OWNER POLICY | opening movement and quantity evidence exist; no completeness declaration exists. Architecture says incomplete coverage must not be represented as zero, but also explicitly says complete opening balances are not a Version 1 prerequisite unless separate launch evidence requires them | Owner must either defer explicitly or authorize a separate persistence-bearing residual. |
| Purchasing receipt, replenishment, Vendor/PO, AP, valuation policy | NO LONGER APPLICABLE to INV.2A | Purchasing and financial boundary documents; roadmap PUR.1/PUR.2/PUR.3; no Purchasing module writes Inventory | Keep in their owning milestones. |

## What integrated Inventory already satisfies

The current implementation already supplies the authoritative aggregates, decimal
and Company/Branch constraints, append-only movement ledger, balance projections,
atomic transfer, reservation creation/allocation/release, material issue/reversal,
adjustments, cycle counts, locking, idempotency, lifecycle evidence, application
APIs, scoped permissions, Business Events, and a launch Inventory workspace.

Recreating tables, movement types, reservations, allocations, material issues,
quantity projections, permissions, or event names would be duplicate work and would
risk incompatible stock truth. Direct Job, Purchasing, Price Book, Invoice, Finance,
Migration, or Economics writes are prohibited.

## Recommended residual scope

Complete only the interface and acceptance-evidence gaps already implied by the
roadmap deliverable:

1. Extend the existing Inventory route to let an authorized user create a stock
   location and create/allocate a reservation through the existing typed APIs.
2. Add focused frontend API/hook/route tests for Branch scope, balances, transfer,
   reservation creation/allocation/release, loading/error state, and permission-
   hidden actions.
3. Add focused backend router/application tests for READ/MANAGE/MOVE/RESERVE
   permission enforcement, unauthorized Branch concealment, endpoint idempotency,
   transactionally staged events, and current conflict responses.
4. Preserve every current repository, model, table, movement, reservation, material
   issue, event, and authorization semantic unless a test exposes a defect inside
   this exact boundary.

This is the smallest coherent residual that makes the existing backend workflows
operable and proves the promised API/UI/authorization contract. It requires no new
runtime domain capability, no persistence work, no migration, and no Purchasing
integration.

### Explicitly excluded duplication

- new Inventory item/location/movement/quantity/reservation/allocation/material-
  issue tables or replacement services;
- a second stock ledger, transfer pair, availability formula, reservation lifecycle,
  material issue workflow, adjustment workflow, or cycle-count workflow;
- roadmap INV.3 Job requirement/consumption, technician experience, returns/waste,
  Purchasing receipts/replenishment, Vendor/PO, Invoice, cost/valuation policy,
  accounting, Economics, barcode, serial/lot, bins, or automated ordering;
- changes to EST.4, DISP.2, PHONE, scheduler/control-plane, Migration, or Economics
  ownership.

## Genuine owner choice: opening-balance completeness

**Recommended:** explicitly defer opening-balance completeness state from INV.2A.
The architecture makes complete opening balances optional for Version 1 and requires
separate launch evidence before making them critical. PUR.1 establishes Vendor/PO
authority and does not require complete stock balances. Existing zero rows remain
absence of recorded movement evidence, not a certified complete count.

**Alternative:** require explicit completeness before accepting INV.2A. This would
add a product policy for completeness granularity and authority, a persistence model
and migration, APIs/UI, events, permissions, and reconciliation tests. It would keep
PUR.1 blocked and must not be inferred from the current documents. If selected, the
owner must decide whether completeness is Company, Branch, location, item/location,
or count-session scoped and who may certify/revoke it.

## Execution readiness after owner acceptance

- **Starting Enterprise SHA:** fetch immediately before execution; at review it is
  `a76be4f1de0dae6fdcce00f77509381127de43e8`.
- **Alembic:** no migration is required for the recommended residual. The current
  single head is `u6k8f0h2j497`; if any schema need is discovered, stop and return
  for owner review rather than creating a migration under this scope.
- **Permanent capacity:** `OM2`, matching the durable scheduler manifest and roadmap
  Office Machine 2 assignment; use an available isolated OM2 lane.
- **Collision risk:** low when restricted to the named Inventory frontend/API test
  seams. Re-fetch and compare active worktrees before execution. Inventory service,
  router, permission, event, and navigation files are shared seams and should change
  only if tests expose a bounded defect.
- **Machine-enforceable boundary candidate:**
  `frontend/src/routes/InventoryRoute.tsx`, `frontend/src/api/inventory.ts`,
  `frontend/src/hooks/useInventory.ts`, `frontend/src/types/inventory.ts`, new
  Inventory-focused frontend tests, `backend/tests/inventory/**`, and only narrowly
  necessary existing Inventory API/service/schema files. Forbid migrations,
  Purchasing, Jobs, Price Book, Invoicing, Financial, Economics, Migration,
  scheduler/control-plane, and unrelated frontend routes.
- **Validation contract:** focused Inventory repository/service/router tests;
  Inventory/Jobs/Operations/permission regression; frontend Inventory tests and
  full frontend regression; Ruff; MyPy; ESLint; TypeScript/Vite build; fresh Alembic
  upgrade and drift/one-head confirmation; `git diff --check`; focused secret scan.
- **Immediate execution:** yes, after the owner approves the recommended residual
  and the scheduler records a Start against a freshly fetched SHA and available OM2
  capacity.
- **PUR.1:** accepted completion of this residual immediately clears the INV.2A
  dependency. PUR.1 then becomes dependency-ready but still requires its own packet,
  Start, fresh SHA, collision check, and serialized integration.

## Owner response requested

Choose one:

1. **Approve recommended residual and defer opening-balance completeness.**
2. **Require opening-balance completeness in INV.2A** and provide the completeness
   granularity and certifying authority decisions listed above.

No other product choice is required by the current repository evidence.
