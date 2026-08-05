# Job Material Requirements and Consumption

## Authority

Operations owns Jobs, and each Job is authoritative for what it expects to need and
what was actually used. Field Service is the technician-facing recording experience;
it records through Job-owned contracts and never duplicates Job ownership.
Inventory owns whether a physical item was available and whether stock moved.
Price Book owns descriptive expected components used to construct commercial
offerings. These are related facts, not one shared record.

## Job-owned aggregates

`JobMaterialRequirement` is a versioned planning fact with Company, Branch, Job,
identity, optional commercial-scope/Price Book component provenance, optional
Inventory item reference, snapshotted description, required decimal quantity/unit,
needed-by time, status, actor, and concurrency version. It does not reserve stock.

`JobMaterialConsumption` is append-only actual-use evidence with Company, Branch,
Job, identity, optional requirement and Inventory item references, snapshotted
description, decimal quantity/unit, use/disposition code, occurrence and recording
times, actor/technician attribution, source, and correction relationship. Authorized
unit-cost evidence is a snapshot with currency and provenance, not a customer price
or ledger amount.

Requirements may be planned, revised, fulfilled, cancelled, or unresolved. Actual
consumption is never edited or deleted; corrections reverse or replace an entry and
retain the complete chain. Job completion policy may warn about unresolved material
facts but must not claim stock truth.

## Version 1.0 workflow

1. A PRICEBOOK.1 snapshot or authorized staff entry may propose requirements. The
   current Price Book component supplies descriptive and expected-quantity
   provenance; Jobs records the operational unit independently. A future Price Book
   unit-of-measure or Inventory-item mapping may enrich this proposal but is not a
   current PRICEBOOK.1 contract.
2. Jobs validates its own Job/Branch scope and records the requirement snapshot.
3. Field staff record actual materials used, returned, or wasted, with units and
   occurrence time. An Inventory identity is optional.
4. Jobs commits its fact and proposed `job.material_consumed` event atomically.
5. If Inventory integration exists, Inventory independently and idempotently posts
   an issue/return movement using the Job consumption identity as provenance.
6. Inventory failure becomes visible reconciliation state; it does not roll back or
   erase truthful field evidence unless an explicitly orchestrated transaction was
   chosen before either domain committed.

This permits Version 1.0 material capture without complete opening balances,
warehouse definitions, truck stock, reservations, or purchasing.

## Returns, waste, substitution, and reconciliation

A return is a new Job disposition fact linked to prior consumption. Inventory alone
decides whether it is restocked, quarantined, or scrapped. Waste is actual Job use
attribution with a controlled reason; Inventory may separately post the decrement.
A substituted material records the actual item/description and its relationship to
the requirement; it never rewrites Price Book composition.

Jobs and Inventory maintain a reconciliation projection keyed by Job consumption
identity: `not_integrated`, `pending`, `posted`, `exception`, or `not_applicable`.
The projection is not ownership of the other domain's state. Duplicate messages and
retries resolve to the same movement identity. Quantity/unit contradiction fails
closed and requires attributed correction.

## Cost and downstream use

Job cost evidence may come from an Inventory issue-cost snapshot, a receipt-derived
cost, an authorized manual fact, or remain unavailable. Provenance, currency,
quantity, unit, valuation method label, and effective time accompany it. Missing
cost is unavailable, not zero. Customer charge remains governed by commercial scope
and Invoice rules; material consumption cannot automatically change it.

Business Economics consumes requirement variance, actual quantities, waste/returns,
and measured cost snapshots. It cannot correct Jobs, move Inventory, generate a
purchase order, or post accounting entries.

## Proposed permissions and events

Proposed permissions are `COMPANY_JOB_MATERIAL_READ`,
`COMPANY_JOB_MATERIAL_PLAN`, `COMPANY_JOB_MATERIAL_RECORD`, and
`COMPANY_JOB_MATERIAL_CORRECT`, constrained by Company, authorized Branch set, and
Job access. They are not live catalog additions.

Proposed Jobs events are `job.material_requirement_recorded`,
`job.material_consumed`, `job.material_returned`, `job.material_wasted`, and
`job.material_consumption_corrected`. Payloads carry identities, controlled decimal
quantity/unit, disposition, occurrence time, and optional Inventory reference; they
exclude customer descriptions, free-form notes, internal cost unless a restricted
contract requires it, and credentials.

## Collision controls

- Price Book component IDs are provenance, not Inventory or Job identities.
- Estimate/Job commercial quantities do not prove physical use.
- Invoice lines cannot be generated merely because material was consumed.
- Inventory issues cannot rewrite Job consumption.
- Accounting reconciliation cannot alter either operational record.
- Migrated material text remains source evidence until explicitly mapped.
