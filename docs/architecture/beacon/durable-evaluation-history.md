# Beacon durable evaluation history

Beacon evaluation history is append-only evidence about what an admitted
evaluator observed. It is not business-domain truth and grants no authority to
change a Job, schedule, Customer, Employee, Payroll, Accounting, price,
purchase, or payment record.

## Persistence contract

Each completed run records Company and optional Branch scope, a deterministic
scope identity, the exact covered definition IDs, evaluation and evidence
cutoff times, evaluator version, provenance digest, and run digest. Each result
records the root condition and signal identities, definition version, evidence
digest, expiry, prior evaluation, and one disposition:

- `NEW`: no active predecessor exists;
- `STILL_ACTIVE`: the same admitted evidence remains active;
- `CHANGED`: the root condition remains but its evidence changed;
- `RESOLVED`: a successful complete evaluation proves the condition absent;
- `EXPIRED`: a successful complete evaluation proves it absent after its
  recorded expiry;
- `SUPERSEDED`: the same root condition is now evaluated by a different
  definition identity or version.

An omitted definition is not treated as resolved. A failed or partial adapter
run must not be persisted as complete coverage. Exact run replay returns the
existing evidence; contradictory reuse fails closed. Database triggers reject
direct update and delete of runs and results.

The bounded read endpoint `/api/v1/beacon/evaluation-history/deltas` derives
new, changed, resolved, and expired briefing facts only from persisted rows.
It accepts timezone-aware windows no longer than 31 days and applies the
requesting principal's Company and active-Branch scope.

## Cross-domain admission

`/api/v1/beacon/cross-domain-adapters` distinguishes active adapters from
adapter-, source-, and policy-gated contracts. A catalog entry never means an
evaluator is active. It also publishes deterministic responsibility and the
condition that would clear attention. Beacon only observes the accepted source
contract; the source domain remains the sole mutation authority.

Current snapshot adapters cover Scheduling overdue appointments, paused Jobs,
and past-due Invoice evidence. Migration, Workforce, Timekeeping, Payroll,
Accounting, Economics/Luminary, Price Book, Estimates, Inventory/Purchasing,
and Capacity remain explicitly gated until their accepted projections are
adapted without reproducing domain logic.

## Operations

Evaluation producers must use a stable 64-character scope identity and retain
the same evaluator version for exact replay. They must not mark a run complete
unless every definition in `covered_definitions` was evaluated successfully.
Provider or source outages should therefore remain visible as adapter/source
readiness, not falsely resolve active attention.

Historical metrics are descriptive only. They may report creation counts,
unresolved age, acknowledgement time, or proven resolution time, but must not
rank Employees or claim Beacon caused an outcome.
