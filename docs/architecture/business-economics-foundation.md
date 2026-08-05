# Business Economics Foundation

Status: authoritative after ECON.1R reconciliation

## Reconciliation decision

The authoritative foundation combines Implementation A (`c1cfcd6`) and
Implementation B (`1ac9f53`) without introducing a second economics namespace or
migration root.

Implementation A contributed normalized immutable evidence identities and
content digests, explicit measurement periods, logical fact versions,
independently versioned allocation policies, idempotent allocation runs, and
persisted input provenance. Implementation B remains the domain and API spine
because it provides integer minor-unit money, explicit measured/estimated/unknown
semantics, unknown propagation, named allocation strategies, the complete
revenue and cost breakdown, tenant-scoped read APIs, and migration continuity.

The resulting authority chain is:

`Business Event / Source Record → Evidence Reference → Business Fact → Allocation Policy + Run → Profit Measurement`

JSON evidence on facts and measurements is a read-optimized snapshot. Normalized
evidence references and fact-evidence links are the identity and integrity
authority. Reusing a source identity and version with a different SHA-256 digest
is rejected.

## Scope

Business Economics Phase 1 establishes an append-only, evidence-backed source of
profitability facts. It does not infer missing values, provide editing or manual
overrides, or perform AI reasoning.

## Domain and calculation boundary

`BusinessFact` records revenue or one cost category in integer minor units. A
known fact must retain evidence; an unknown fact has no amount. The immutable
measurement engine groups facts by category and computes:

- gross profit = revenue - labor - materials - equipment - truck;
- net profit = gross profit - allocated overhead.

If any required input is unknown, the dependent result is unknown. Estimated
inputs remain explicitly estimated and lower the resulting confidence. Currency
mixing and cross-subject calculations are rejected.

Facts also retain a stable fact key, measurement method, period, source occurrence
time, and logical version. Measurements reject facts from mixed periods and store
the exact fact and allocation identifiers used by the engine.

## Allocation

The allocation registry exposes versioned strategies for labor hours, revenue,
truck-days, job duration, branch, and company weights. Strategies allocate exact
minor units, including deterministic remainder distribution. New strategies can
be registered without changing the measurement engine.
Persisted policies are versioned separately from idempotent runs. A run digest
covers the source fact version, value, and ordered target weights, and every run
records its residual.

## Evidence and versioning

Evidence retains kind, source system, record type, source version, identifier,
SHA-256 digest, observation time, and an optional direct Business Event foreign
key. Allocations retain their source fact, weights, policy/run identity, strategy,
strategy version, and deterministic input digest. Persisted measurements snapshot
every component, confidence, normalized provenance identifiers, engine version,
measurement version, period, and timestamp. Records are append-only at the
application boundary; ledger services stage changes but never commit independently.

## API

Authenticated callers with `COMPANY_ECONOMICS_READ` can list company-scoped
measurements or fetch the latest measurement for a subject. Phase 1 exposes no
write, override, or deletion endpoint.

## Phase 2 authoritative ingestion

All source adapters are deterministic translators. They never write economics
tables and never infer missing values. `EconomicsIngestionService` rejects any
adapter output that is not explicitly measured and routes accepted commands to
`EconomicsLedgerService`, the sole internal materialization boundary.

- Issued invoices produce accrual-basis job revenue.
- Successful payments produce separate cash-basis invoice facts and therefore do
  not double-count accrual profitability.
- Labor time entries, material usage, equipment utilization, and truck activity
  implement a strict measured-cost source contract. Economics does not duplicate
  or own their future operational source tables.
- Jobs and appointments are supported sources but currently produce no monetary
  facts: Jobs have no measured amount, and Appointment duration is expected rather
  than measured.
- Business Events produce facts only when their payload explicitly declares a
  complete measured economics value.

Each known fact requires SHA-256 source evidence and Business Event linkage.
Canonical command digests make re-ingestion idempotent. Reversals, supersessions,
and effective-date corrections append new facts linked to the corrected fact;
historical facts and measurements are never updated or deleted.

Fact ingestion queues job, branch, and company recalculation scopes. The scheduled
recalculation service locks and processes only pending scopes. Job scopes create
idempotent, versioned measurement snapshots; branch and company read models roll
up the latest job snapshots without duplicating the accounting ledger. Read-only
projections expose job, branch, and company profitability, subject history,
evidence completeness, and stale measurements.

## Phase 3 financial integrity and allocation execution

Accounting periods govern ledger and allocation writes. Periods move through
`open -> closing -> closed`; a closed period accepts late evidence only after an
explicit `reopened` transition. Every transition retains its effective range,
responsible owner, reason, timestamp, and version. Closing is refused while
affected recalculations or recorded reconciliation failures remain.

Allocation policies remain immutable and versioned. `AllocationExecutionService`
executes registered labor, revenue, truck, equipment, overhead, branch, and
company strategies against measured ledger facts. Each idempotent run persists
its policy version, source fact, period, exact lines, source evidence, input
digest, residual, confidence, duration, and run version. Allocation never changes
the source ledger.

The integrity flow is:

`source evidence -> EconomicsIngestionService -> EconomicsLedgerService -> period-controlled allocation -> affected-scope materialization -> durable projection`

Recalculation publishes immutable job, branch, and company profitability
projection versions from authoritative measurement IDs. It never updates an
earlier projection. Source, ledger, allocation, measurement, and evidence
reconciliation results are immutable and input-digested. Failed checks remain
visible when a later run succeeds.

Operational observations persist pending recalculations, allocation and
materialization duration, reconciliation failures, stale measurements, and
incomplete periods. These records are operational evidence; they do not alter
financial values.

## Phase 4 accounting integration and financial close

Phase 4 operationalizes the integrity boundary without transferring ownership of
operational data to Economics. Versioned source bindings identify the owning
domain, table when one exists, adapter contract, availability state, and evidence
requirements. Invoices, payments, and Business Events are bound sources. Jobs and
Appointments are read-only economics context. Labor, materials, equipment, fleet,
and overhead retain measured-input contracts and remain `contract_ready` until an
authoritative owning table exists; Economics does not invent one.

Durable scheduled work items coordinate recalculation, allocation,
materialization, publication, reconciliation, and monitoring. Idempotency keys,
`FOR UPDATE SKIP LOCKED` claims, bounded attempts, exponential retry scheduling,
abandoned-claim recovery, failure evidence digests, and duration/failure metrics
make restart behavior explicit. Each service remains independently idempotent, so
replaying a work item cannot create a second financial result.

Close readiness is evidence-driven rather than clock-driven. It evaluates source
record coverage, balanced allocations, complete measurements, pending/stale
scopes, economics reconciliation, unresolved corrections, GL reconciliation, and
the responsible owner. Once Phase 4 source bindings exist, a period cannot move
from `closing` to `closed` without a current ready result and an immutable audit
package. Closed-period facts remain blocked until a controlled, reasoned,
owner-attributed reopening.

Accounting integration is provider-neutral. Versioned chart mappings classify
revenue, costs, payments, and allocation postings without embedding provider
behavior. Journal exports carry balanced debit/credit lines, branch dimensions,
payment/source references, evidence digests, projection lineage, a SHA-256
checksum, acknowledgement or rejection evidence, replay identity, and correction
lineage. General-ledger reconciliation reports represented source value, exported
value, journal balance, rejected lines, duplicates, corrections, variance,
ownership mismatch, and unexplained residual; unavailable evidence remains
`unknown`.

Period audit packages immutably snapshot transition history, fact and correction
lineage, evidence digests, allocations, measurements and confidence explanations,
projections, reconciliation, readiness, exports, and GL reconciliation. Downstream
publication exposes only reconciled projection identity, confidence,
completeness, freshness, evidence lineage, and integrity status. It exposes no
Beacon, Luminary, LIA, or AI behavior.

## Phase 5 architecture contract

The approved Phase 5 operational-source and profitability-intelligence boundary
is defined in
[`business-economics-phase5-contract.md`](business-economics-phase5-contract.md).
Its immutable Economics contracts define analysis, measured/allocation boundaries,
quality, evidence, comparison, findings, and recommendations without persistence
or execution. Operational-source implementation, migrations, Luminary, AI, Beacon
rules, dashboards, provider transports, and scheduling remain unauthorized until
the contract's dependencies and owner decisions are resolved and approved.

## Phase 6 deterministic profitability computation

The provider-neutral computation foundation is defined in
[`business-economics-phase6-computation.md`](business-economics-phase6-computation.md).
It deterministically converts immutable fact and allocation port inputs into the
approved Phase 5 analysis and explanation contracts. Canonical ordering, SHA-256
lineage, stable UUIDv5 identity, scope isolation, freshness enforcement, explicit
missing values, and gross/net reconciliation form the fail-closed boundary. Phase
6 adds no persistence, migration, runtime orchestration, Luminary, Beacon, AI,
scheduler, API, or frontend implementation.

## Phase 7 operational fact acquisition

The provider-neutral acquisition boundary is defined in
[`business-economics-phase7-acquisition.md`](business-economics-phase7-acquisition.md).
Immutable Jobs, Dispatch, Price Book, and Customer snapshots are translated by
read-only adapters into canonically ordered, evidence-digested acquisition
batches. Missing fields remain explicit and Company/Branch isolation fails
closed. Operational domains retain transaction ownership. Phase 7 adds no
persistence, migration, scheduler, runtime invocation, AI, Luminary, Beacon,
frontend, or Production behavior and does not yet translate acquired context into
ledger facts.

## Phase 8 deterministic allocation engine

The pure allocation foundation is defined in
[`business-economics-phase8-allocation.md`](business-economics-phase8-allocation.md).
It allocates immutable cost pools through effective, versioned policies across
direct, Technician, truck-day, Branch, and Company boundaries. Canonical ordering,
stable SHA-256/UUIDv5 lineage, exact minor-unit balancing, deterministic remainder
distribution, source and driver evidence, and zero residual are mandatory. It
does not replace Phase 3 durable allocation runs and adds no persistence,
migration, scheduler, runtime integration, AI, Luminary, Beacon, or frontend.
