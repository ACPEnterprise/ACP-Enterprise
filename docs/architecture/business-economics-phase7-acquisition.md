# Business Economics Phase 7 Operational Fact Acquisition

Status: implemented provider-neutral foundation

## Boundary

Phase 7 introduces immutable source snapshots and read-only adapters for Jobs,
Dispatch, Price Book, and Customers. Source domains own their transactions,
versions, corrections, permissions, and Business Events. Economics receives a
snapshot plus authoritative source identity and SHA-256 evidence; it neither
queries nor writes an operational table through these contracts.

```text
source-owned query/projection
  -> provider-neutral immutable snapshot
  -> domain acquisition adapter
  -> canonically ordered AcquisitionBatch
  -> future authorized Economics translation/ingestion
  -> deterministic profitability computation
```

Phase 7 stops at acquisition. It does not materialize Business Facts or invoke
the ledger or Phase 6 computation service.

## Contracts and adapters

The common contract carries Company, authorized Branch scope, period, source
record identity/version, evidence digest, observation time, optional Business
Event identity, canonically ordered attributes, and explicit missing fields.

- `JobsAcquisitionAdapter` captures Job/customer/location identity, lifecycle,
  type, and concurrency version.
- `DispatchAcquisitionAdapter` captures appointment/activity, Job and Technician
  linkage, planned/actual execution context, and version.
- `PriceBookAcquisitionAdapter` captures exact item version, accepted estimate and
  option lineage, and expected revenue/labor/material amounts. Expected values are
  context for an estimated basis; they are not actual revenue or measured cost.
- `CustomersAcquisitionAdapter` captures customer classification, lifecycle,
  marketing source, and service-location context. It acquires no private contact
  details and creates no customer economics.

Missing optional or required downstream fields produce an `incomplete` record
with sorted field names. Adapters never supply placeholders or infer links.

## Determinism and isolation

Attributes, missing fields, and facts are canonically ordered. Each acquired fact
uses UUIDv5 over its source domain, source ID, source version, and evidence digest.
The batch digest covers the ordered manifest and produces a stable batch UUID.
Identical snapshots in any input order therefore replay identically.

Company mismatch or a Branch outside the request's authorized set fails closed.
Adapters expose no mutation method. Persistence, scheduling, AI, Luminary, Beacon,
frontend behavior, and provider transport are absent.

## Remaining source decisions

The operational owners must provide approved query projections that implement
these snapshot shapes. Dispatch still needs authoritative Technician assignment
and actual execution timestamps. Price Book needs accepted estimate/option
lineage on this branch. Customer-to-Branch and service-location effective history
must be explicit. A later milestone must approve the deterministic translation
from acquired context into ledger commands; acquisition alone is not financial
evidence of revenue, paid labor, or consumed materials.
