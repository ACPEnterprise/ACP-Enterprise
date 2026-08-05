# Business Economics Phase 6 Deterministic Computation

Status: implemented application-layer foundation

## Boundary

`ProfitabilityComputationService` consumes immutable measured/estimated fact and
allocation inputs through `ProfitabilityFactPort` and
`ProfitabilityAllocationPort`. The ports are provider-neutral and read-only.
Operational domains retain transaction ownership; this layer has no persistence,
migration, scheduler, provider, Luminary, Beacon, API, or frontend behavior.

## Flow

```text
ProfitabilityComputationRequest
  -> fact and allocation ports
  -> scope, basis, identity, freshness, and contradiction validation
  -> deterministic category components
  -> gross and net reconciliation
  -> quality and lineage digest
  -> stable ProfitabilityAnalysis identity
  -> deterministic findings and bounded explanation
```

The request fixes Company, Branch, scope, subject, effective period, accounting
basis, currency, projection lineage, freshness policy, owner, and analysis
version. Inputs outside that boundary fail closed.

## Determinism and integrity

- Facts are ordered by stable fact identity; allocations by allocation identity;
  evidence by source identity/version/digest.
- Duplicate identical inputs collapse. Conflicting versions or evidence digests
  are rejected.
- The canonical ordered input manifest produces a SHA-256 lineage digest. UUIDv5
  over that digest produces the analysis identity.
- Actual analysis rejects estimated facts. Estimated analysis remains explicitly
  estimated. Components containing allocation lines remain allocated.
- Missing categories produce missing components and zero aggregate confidence;
  they never become zero-valued costs.
- Gross profit is revenue less labor, materials, equipment, and truck. Net profit
  is gross profit less overhead. Missing dependencies keep the result missing.
- Future evidence, evidence older than the request policy, mixed currency, and
  cross-scope or cross-Company inputs are rejected.
- Findings and explanations cite the same lineage digest and cannot alter the
  computed amounts or confidence.

## Supported views

The same computation contract supports Job, Technician, Branch, and Company
scopes and actual or estimated bases. Time windows are carried by the effective
period rather than becoming a second financial authority.

## Persistence decision

Phase 6 requires no persistence. Existing Phase 4 measurements and projections
provide lineage identities through adapters implemented in a later authorized
milestone. Persisting analyses or explanations would require an explicit future
retention, versioning, authorization, and migration decision.
