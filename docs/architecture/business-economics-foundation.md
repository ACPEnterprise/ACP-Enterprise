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
