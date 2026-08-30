# Economics capability reconciliation

`business-economics-foundation` is treated as capability evidence, not as an authority lineage. Current Enterprise Economics remains `app.business_economics` and consumes accepted facts; it does not own Payroll calculation, Accounting journals, Invoice truth, Payment settlement, Inventory, or Purchasing.

## Current authority

- Source conformance, source-authority adapters, inconsistency findings, policy authority, evidence acceptance, measurement input/package contracts, calculation admission, and policy-to-measurement bridging were already authoritative.
- Accounting, Payroll, Purchasing, Inventory, Jobs, Payments, Beacon, QBO source evidence, Timekeeping, and Business Events retain their native authority.

## Transplanted capability

- Immutable profitability evidence, quality, scope, component, finding, recommendation, and explanation contracts.
- Deterministic cost allocation with balanced residual handling and immutable policy/input lineage.
- Deterministic profitability computation and actual/estimated comparison.
- A current-authority admission bridge that prevents calculation unless the existing Economics measurement package is admitted and binds the result to its package/admission digests.

## Superseded or obsolete capability

- The legacy `app.economics` router, service, repository, persistence models, ledger, accounting-close, journal export, integrity publication, processing queue, and source acquisition are not transplanted. Their authority is superseded by current Accounting, Business Events, source adapters, evidence acceptance, and measurement admission.
- Legacy Economics migrations are not retained: they would create duplicate facts, ledgers, accounting-close state, and projections. No bridge schema is required for the persistence-free calculation transplant.
- Legacy source adapters are superseded by current QBO, Payroll/Timekeeping, Purchasing/Inventory, Jobs, Payments, Accounting, and Beacon contracts.

Unknown, partial, conflicting, stale, unaccepted, or policy-incomplete evidence remains non-calculable. Missing components are never interpreted as zero, and no AI-generated value becomes financial truth.

## Owner intelligence and LIA-readiness boundary

The owner workspace exposes Company, Branch, service/category, Customer, and Job
rollups over admitted immutable results. Contribution remains distinct from fully
allocated profitability and Accounting net income. Estimate value, invoicing,
settlement, and Accounting revenue retain distinct economic roles and are never
summed as interchangeable revenue.

`GET /api/v1/business-economics/owner-intelligence` is the bounded deterministic
owner-question contract. It accepts a fixed question identity and period; arbitrary
SQL or free-form query execution is prohibited. Answers include explicit quality,
freshness, limitations, a stable digest, and at most ten citable Economics result
references. The digest excludes execution time, so unchanged authority produces an
unchanged evidence identity.

This context packet is suitable for a future permission-aware LIA, but grants no
recommendation or mutation authority. Economics supplies measured results and
findings; Beacon owns attention lifecycle; LIA may later explain or recommend; an
authorized domain service alone may execute an action. Conflicting, stale, partial,
and unavailable evidence survives this boundary without being replaced by zero.

Unknown Company overhead policies, targets, benchmarks, and prioritization weights
remain explicitly unconfigured. Their missing values do not block contribution
measurement, but they do block claims of fully allocated profitability or target
variance.

## Immutable profitability history

`economics_profitability_results` is append-only database evidence. PostgreSQL
rejects direct update and delete operations. Corrections and recomputations
insert a new result and an immutable
`economics_profitability_result_supersessions` edge. The edge is Company-bound,
validates matching subject/scope/basis/period/currency and result digests, and
permits only one predecessor and one successor per edge of a lineage.

Current authority is resolved without a mutable status flag: a result is current
when no accepted supersession names it as predecessor. Historical detail remains
queryable with predecessor, successor, reason, package, and computation lineage.
Exact replay recovers the existing result/edge; contradictory or concurrent forks
fail closed. Downgrade refuses to discard accepted supersession evidence.
