# Inventory Domain Architecture Brief

- **Status:** Proposed Version 1.0 boundary contract
- **Release:** Narrow material evidence in Version 1.0; stock control later

Related contracts: [Item and Location Identity](item-and-location-identity.md),
[Job Material Consumption](job-material-consumption.md), and
[Inventory, Purchasing, and Accounting Boundary](../financial/inventory-purchasing-accounting-boundary.md).

## Purpose and business problem

Inventory is the authoritative bounded context for physical item identity and,
when stock control is implemented, physical quantity by location, movements,
reservations, replenishment policy, and valuation evidence. The boundary prevents
a Price Book component, Job material entry, purchase receipt, or accounting record
from silently becoming stock truth.

Version 1.0 must permit Jobs to record materials actually used even when warehouse
and truck balances are not complete. Missing Inventory coverage is explicit; it is
never represented as zero stock or inferred from Job consumption.

## Scope and ownership

Inventory owns these aggregates:

- `InventoryItem`: stable Company-owned physical identity, stocking unit,
  conversion policy, lifecycle, and optional barcode/serialization/lot policy;
- `InventoryLocation`: warehouse, vehicle, staging, quarantine, or other controlled
  stock location identity;
- `StockMovement`: append-only quantity movement and valuation evidence;
- `Reservation`: a controlled claim against available quantity for a Job or other
  approved demand reference;
- `ReorderPolicy` and `ReorderSignal`: replenishment thresholds and measured signal;
- `CycleCount`: count session, observations, approval, and resulting adjustments.

Inventory does not own Price Book services or prices, Job requirements or actual
use attribution, vendors, purchase orders, receipts, invoices, accounts payable,
ledger classifications, or QuickBooks records. It references their stable
identities through contracts. No other domain writes Inventory tables.

## Aggregate boundaries and invariants

`InventoryItem` controls identity and units, but never stores a mutable on-hand
total. Quantity truth is derived from posted movements or maintained as an
Inventory-owned projection with the movement journal as evidence. An item cannot
change its stocking unit after movements exist; a successor identity or explicit
conversion migration is required.

`StockMovement` is immutable after posting. Corrections use linked compensating
movements. Every movement has Company, item, quantity and unit, occurrence and
posting time, movement type, source/destination location as appropriate,
provenance, actor, idempotency identity, and optional unit-cost evidence. Quantity
uses decimal numeric values, never binary floating point.

`Reservation` changes availability, not physical on-hand quantity. It is scoped
to one Company, item, location or approved location set, demand reference, quantity,
expiration, and lifecycle. Allocation, release, fulfillment, and expiration are
idempotent. Reservations cannot cross Companies or produce negative availability
unless an explicitly approved policy permits backorder state.

## Workflows

1. An authorized user establishes an Inventory item and permitted stock locations.
2. A Purchasing receipt may request Inventory to post receipt movements through an
   application contract; Purchasing never inserts them.
3. An approved demand may create a reservation. Inventory locks the applicable
   balance/reservation scope and either records one claim or fails closed.
4. Transfers post one atomic source/destination movement pair with a shared transfer
   identity. In-transit handling, if enabled, is an Inventory location/state.
5. Job consumption remains a Jobs fact. A later integration may ask Inventory to
   issue stock against it, recording a source reference and idempotency key. Failure
   to issue stock never erases the Job's actual-use evidence.
6. Returns, waste, counts, and adjustments post separately classified movements;
   they never edit prior movements.

## Warehouse, vehicle, and quantity behavior

Warehouses and vehicles are location identities, not item owners. A vehicle
location references the fleet/vehicle identity owned elsewhere and preserves that
reference when a vehicle is inactive. Branch access and physical custody are
distinct: authorized Branch sets constrain access, while Inventory records the
actual location. Records are Company-scoped in every repository predicate and
constraint; access is never filtered after loading.

On-hand, reserved, available, in-transit, quarantined, and damaged quantities are
distinct projections. Reorder signals consume controlled quantities and policy;
they do not automatically create a purchase order. Negative on-hand, substitution,
cross-location allocation, and backorders require explicit later policy.

## Returns, waste, transfers, counts, and adjustments

- A return from a Job records disposition: restock, quarantine, scrap, or vendor
  return candidate. Only restock increases available stock.
- Waste records a reason code and evidence reference and reduces the controlled
  location quantity; it is not a Job correction.
- A transfer cannot be represented as unrelated decrement/increment commands.
- A cycle count freezes or versions its counting scope, records blind observations,
  calculates variance, and requires the configured approval before adjustment.
- An adjustment requires reason, actor, evidence, and compensating valuation fact.

## Security and proposed permissions

Platform authentication, immutable authorization context, Company isolation, and
authorized Branch sets apply to every command and query. Proposed permissions are:

| Permission | Purpose |
| --- | --- |
| `COMPANY_INVENTORY_READ` | View authorized item, location, and quantity evidence |
| `COMPANY_INVENTORY_MANAGE` | Manage item and location drafts and reorder policy |
| `COMPANY_INVENTORY_MOVE` | Post issues, returns, waste, and transfers |
| `COMPANY_INVENTORY_RESERVE` | Create, release, and fulfill reservations |
| `COMPANY_INVENTORY_COUNT` | Conduct counts and propose variance |
| `COMPANY_INVENTORY_ADJUST` | Approve controlled stock adjustments |

These are architecture proposals only. This milestone changes no live catalog or
role. Cost visibility may require a separate financial-data permission.

## Proposed Business Events

`inventory.item_created`, `inventory.location_created`,
`inventory.movement_posted`, `inventory.reservation_created`,
`inventory.reservation_released`, `inventory.transfer_posted`,
`inventory.reorder_signaled`, `inventory.cycle_count_completed`, and
`inventory.adjustment_posted` are proposed. Events are transactional with their
aggregate change and contain identifiers, controlled quantities/units, reason or
movement codes, and occurrence time—not unrestricted descriptions, vendor terms,
customer data, costs unless specifically authorized, or credentials.

## Migration compatibility and risks

Existing imported material text, Price Book component descriptions, and Job facts
must not be reclassified as Inventory items or stock movements without an explicit
mapping record and provenance. Additive migrations preserve source identities,
Company scope, decimal precision, and historical evidence. A material code collision
across Price Book, Jobs, and Inventory is not identity equivalence.

Primary risks are unit mismatch, duplicate receipt/issue posting, negative stock
races, cross-Branch leakage, mutable cost evidence, and assuming incomplete opening
balances are complete. Database constraints, scoped locking, idempotency identities,
append-only movements, and explicit completeness state are required controls.

## Acceptance criteria and implementation sequence

This architecture is satisfied when ownership is unambiguous; Version 1.0 Job use
can exist without stock; units and identities cross boundaries through versioned
contracts; Inventory alone changes stock; and no contract invents accounting facts.

Recommended implementation order:

1. Job-owned material requirements and append-only actual-use evidence.
2. Inventory item/location identity and mapping contracts, if operationally needed.
3. Opening-balance completeness and movement journal.
4. Receipts, issues, returns, transfers, and reservations.
5. Counts, adjustments, reorder signals, and replenishment projections.
6. Serialized/lot tracking and advanced valuation only after separate approval.

## Deferred extension points

Version 1.0 excludes complete warehouse/truck balances, barcoding, scanners,
serialized and lot-controlled stock, replenishment automation, purchase generation,
vendor returns, and accounting valuation. Stable item/location IDs, mapping tables,
movement provenance, optional serial/lot references, and provider-neutral event/API
contracts preserve these seams without implementing them.
