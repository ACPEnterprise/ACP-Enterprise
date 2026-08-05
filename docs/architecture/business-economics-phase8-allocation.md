# Business Economics Phase 8 Deterministic Allocation and Profitability Engine

Status: implemented deterministic application foundation

## Boundary and flow

`DeterministicAllocationEngine` accepts one immutable cost pool, one effective
versioned policy, and evidence-backed weighted targets. It emits a balanced,
canonically ordered `DeterministicAllocation` with stable policy/run lineage and
line-level evidence. It has no persistence, scheduler, provider, AI, Luminary,
Beacon, API, frontend, or Production behavior.

```text
measured or estimated cost pool
  + effective allocation policy
  + measured driver targets
  -> scope and policy validation
  -> canonical target ordering
  -> integer-minor-unit proportional allocation
  -> deterministic remainder distribution
  -> balanced lines, lineage, and evidence digest
```

## Supported boundaries

- Direct cost: exactly one target receives the full cost.
- Technician: targets use an approved measured Technician driver.
- Truck-day: targets use an approved measured truck-day driver.
- Branch: a shared pool is allocated to Branch-authorized targets.
- Company: a Company pool may allocate across its Branch dimensions but never
  across Companies.

The engine does not decide which driver or policy is appropriate. That authority
belongs to the approved, effective-dated policy supplied to it.

Immutable policies identify direct, proportional, labor-hour, revenue-share,
truck-day, Technician, Branch, Company, fixed, or custom provider-neutral
strategies. Custom identifies a policy contract; it does not execute provider
code. Every policy preserves its identity/version, run version, effective period,
driver, freshness limit, and explanation.

## Invariants

- Cost pools accept only labor, materials, equipment, truck, and overhead.
- Missing or already allocated pools cannot be reallocated as source authority.
- Policy and run versions are positive and preserved in the output reference.
- Targets are unique, non-negative, evidence-backed, and Company-isolated.
- Direct allocation requires exactly one target.
- Policies must cover the full cost-pool effective period.
- Positive and negative correction pools balance exactly in integer minor units.
- Remainders are distributed in canonical target order.
- Canonical input SHA-256 produces stable allocation, run, and line UUIDv5 values.
- Conflicting evidence identities fail closed.
- Circular targets, duplicate allocation identities, stale evidence, and
  unsupported currencies fail closed.
- Output residual is always zero and line totals equal the source pool.

## Reconciled profitability engine

`ReconciledProfitabilityEngine` accepts acquired economic facts and allocated
costs carrying acquisition/allocation digests, completeness, evidence, and
explanation identities. It delegates component computation to the Phase 6
service, then publishes contribution margin, gross and net margin basis points,
allocated cost, and fully burdened cost. The Phase 5 analysis remains the
financial component authority.

The reconciliation equations remain revenue less direct labor, materials,
equipment, and truck for gross profit, followed by Technician burden, Branch,
Company, and administrative overhead allocations for net profit. Inputs that do
not reconcile are rejected by the Phase 5/6 invariants.

Comparison results support like-scope Job, Technician, Branch, or Company results,
including actual-versus-estimated bases. Stable ordered lineage produces UUIDv5
result and comparison identities, identical metrics, explanations, and digests on
replay. Cross-scope comparison fails closed.

## Persistence decision

Phase 8 requires no new persistence. Existing Phase 3 allocation-run persistence
remains authoritative for durable execution. Connecting this pure engine to that
boundary requires a separately approved integration milestone and no schema
change is implied here.
