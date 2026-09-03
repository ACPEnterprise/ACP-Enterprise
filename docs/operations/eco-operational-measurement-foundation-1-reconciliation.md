# ECO.OPERATIONAL.MEASUREMENT.FOUNDATION.1 schema reconciliation

- Protected authority: `origin/customer-management-v1` at
  `7d12ffeec1ff6de2f0a7dcfee8ba8e899bf71e6c`.
- Published OM1 authority: `6fb21c1dcd53e4cf3736e79c7a040b6d0746d382`.
- Published migration lineage: `z7q9m1o3r508 -> a1c3e5g7i9k1`.
- Reconciled migration lineage: `n0p8r16g3t9u -> a1c3e5g7i9k1`.

The protected migration head `n0p8r16g3t9u` already descends from
`z7q9m1o3r508`. Re-parenting the unpublished OM1 migration onto the current
protected head preserves every intervening protected migration while producing
one Alembic head. The table, constraints, immutable trigger, contract version,
source states, packet digests, correction semantics, and runtime measurement
architecture are unchanged.

This reconciliation adds no owner policy values. Productive-time definitions,
break-even methodology, overhead allocation, contribution interpretation,
markups, labor policy, staffing policy, pricing policy, scenario parameters,
and alert thresholds remain external approved-policy inputs. Luminary receives
read-only evidence and limitations only; no autonomous action, employment
decision, Price Book activation, or repricing is introduced.

HCP compatibility remains provider-neutral through the admitted operational
evidence contract. Missing arrival, travel, pause/resume, category, timezone,
technician crosswalk, or other HCP fields retain their existing `PARTIAL`,
`SOURCE_REQUIRED`, `CONFLICTING`, or `EXTERNAL_GATE` disposition and cannot be
promoted into measured values without Migration-supplied digest-bound evidence.

Qualification used a fresh isolated PostgreSQL 16 cluster. Zero-to-head reached
`a1c3e5g7i9k1`; `alembic current` equaled head and `alembic check` reported no
upgrade operations. The affected cross-domain suite passed 1,266 tests and the
additional audit/authorization/isolation suite passed 40 tests. Repository-wide
MyPy passed 709 source files; affected Ruff, Python compilation, and diff checks
also passed. Repository-wide Ruff continues to report pre-existing findings in
unrelated protected files; none are introduced or modified by this branch.
