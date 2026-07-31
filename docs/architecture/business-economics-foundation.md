# Business Economics Foundation

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

## Allocation

The allocation registry exposes versioned strategies for labor hours, revenue,
truck-days, job duration, branch, and company weights. Strategies allocate exact
minor units, including deterministic remainder distribution. New strategies can
be registered without changing the measurement engine.

## Evidence and versioning

Facts retain source system, source version, source/business-event identifiers,
and explanations. Allocations retain their source fact, weights, strategy, and
strategy version. Persisted measurements snapshot every component, confidence,
deduplicated evidence, engine version, measurement version, and timestamp.
Records are append-only at the application boundary.

## API

Authenticated callers with `COMPANY_ECONOMICS_READ` can list company-scoped
measurements or fetch the latest measurement for a subject. Phase 1 exposes no
write, override, or deletion endpoint.
