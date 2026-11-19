# Data Master overnight integration ledger — 2026-11-18

## Gate

- Data Master starting SHA: `1804e3d7418810bc30bb204761e009d768c9f8e4`
- Starting and resulting Alembic head: `zq9s1u3w5y7c`
- Source policy: HCP read-only; QBO read-only; no payroll execution; no money movement.
- Release policy: candidate review and integration only; no Beta deployment.

## Candidate decisions

| Lane | Candidate | Decision | Reason | Resulting Data Master SHA | Schema head | Tests | Remaining dependencies |
|---|---|---|---|---|---|---|---|
| OM2A — source acquisition / QBO Accounting | `work/migration-factory-v1` at `0ec9ccd001c9ecd8bb5f8bf132a5e05727386b2f` | RETURNED | The diff merges textually, but its migration chain forks at `zq9s1u3w5y7a` and ends at `mf3c5e7g9i1k`; admission beside current `zq9s1u3w5y7c` would create two heads. The historical-read document is not the required candidate handoff packet. | `1804e3d7418810bc30bb204761e009d768c9f8e4` | `zq9s1u3w5y7c` | 50 focused Migration Factory/HCP tests passed. Static candidate lineage has one candidate-local head, `mf3c5e7g9i1k`, but is not integration-safe. | Rebase onto current Data Master; produce one integration lineage; provide the full handoff contract and an isolated PostgreSQL zero-to-head/drift receipt; retain explicit HCP/QBO read-only evidence. |
| OM2B — Demo Company | `work/enterprise-operational-acceptance-factory-1` at `e8c3b6d937319c51bdaf12afa1afa3f340466185` | RETURNED | One content conflict exists in `backend/scripts/operational_acceptance_factory.py`. Its generated packet records an obsolete authority and schema head and was not regenerated against current Data Master. No candidate handoff packet was supplied. | `1804e3d7418810bc30bb204761e009d768c9f8e4` | `zq9s1u3w5y7c` | Prior worker evidence is stale relative to the current catalog; no post-admission tests ran. | Rebase onto current Data Master, preserve current scenarios, re-add only the intended bounded cases, regenerate the packet, and supply the full handoff contract. |
| OM2D — historical identity bridge | `work/om2d-historical-source-parity` at `5bf8932737fc5c580353841c488c3d1aa110df7b` | RETURNED | The clean candidate is textually and schema conflict-free, but its bridge is a disconnected in-memory planner: no application path calls `build_historical_identity_bridge`, and no durable admitted source crosswalk is created. The router only prefers an already-existing SOURCE.4 identity. Richard Ratliff is synthetic test data rather than a real evidence-backed acceptance receipt; there is no 20-customer cohort, required per-domain disposition report, or complete handoff packet. The candidate also changes Product-owned frontend files without Product acceptance and is not published on origin. | `1804e3d7418810bc30bb204761e009d768c9f8e4` | `zq9s1u3w5y7c` | 11 focused parity, bridge-planner, and retained-history projection tests passed. Static lineage remains one head with no schema change. | Wire the deterministic plan into a governed, idempotent, durable crosswalk admission path; prove real Richard Ratliff and at least 20 retained customers; report Customer/Location/child counts and human decisions; obtain Product acceptance for frontend changes or return a Data-only candidate; provide the full handoff contract and publish the branch. |
| OM2E — payroll blind replay | `work/om2e-real-payroll-blind-replay` at `33fd2c8a40d426a482a88b9f8d9a2988f9d0f12d` | RETURNED | The candidate is clean and textually conflict-free, but its new migration revises `zq9s1u3w5y7a`, producing two candidate-local heads: `ar1p3s5u7w9y` and `zq9s1u3w5y7c`. The real input packet is explicitly incomplete, no result was frozen, and no QBO answer-key comparison occurred. The branch is not published and no complete handoff packet was supplied. | `1804e3d7418810bc30bb204761e009d768c9f8e4` | `zq9s1u3w5y7c` | 22 focused blind-replay contract tests passed. Static lineage failed with `HEAD_COUNT_NOT_ONE`; persistence tests were not admission-relevant after the schema gate failed. | Rebase/linearize the migration on current Data Master; retain the zero-money-movement boundary; finish or truthfully gate the six-employee sealed input/result/answer-key sequence; provide PostgreSQL migration/drift evidence and the full handoff contract; publish the candidate. |

## Exact bounded correction requests

### OM2A

Return one clean candidate based on current Data Master. The candidate must retain exactly one Alembic head and include the required handoff fields: branch, SHA, domains and sources, starting/resulting head, tests, source-write status, reconciliation and provenance effects, rollback, and blockers. Include isolated PostgreSQL zero-to-head plus `alembic current`, `heads`, and `check` evidence. Do not broaden provider scope.

### OM2B

Reconcile the acceptance-factory script against the current scenario catalog without replacing current scenarios. Regenerate every derived packet on the current authority and schema head. Return the full handoff contract and focused harness tests.

### OM2D

Return a governed, idempotent, durable crosswalk admission path rather than only an in-memory plan. Prove the application path actually persists or admits exact Customer and Location relationships and makes retained children visible without recreating canonical records. Include a real Richard Ratliff receipt, at least 20 representative retained customers, per-domain source/bridged/quarantined/ambiguous/unexplained counts, duplicate prevention, the canonical timeline contract, exact remaining human decisions, and no-HCP-write evidence. Separate Product-owned frontend changes unless Product Master has accepted them.

### OM2E

Return a clean, published candidate based on current Data Master with one Alembic head. The pre-calculation inputs and results must be sealed, the QBO comparison must occur only after freeze, and the receipt must prove no payroll execution or money movement. Include isolated PostgreSQL zero-to-head/current/check evidence and the complete Data Master handoff fields.

## Admission result

No worker candidate was admitted in this sweep. Data Master remains on the current Product baseline with one Alembic head. No source system was contacted or mutated, and Beta was not deployed.

## Data Master regression receipt

- Static lineage: one root, one head (`zq9s1u3w5y7c`), 212 revisions, no structural risks.
- Isolated PostgreSQL zero-to-head: passed.
- Runtime `alembic current`: `zq9s1u3w5y7c`.
- Runtime `alembic check`: no new upgrade operations detected.
- Focused retained HCP financial-history and QBO native-application tests: 10 passed.
- Disposable qualification database removed after the run.
