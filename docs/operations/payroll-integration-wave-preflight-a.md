# PAYROLL.INTEGRATION.WAVE.PREFLIGHT.A

Generated 2026-09-12 from protected `customer-management-v1` at `d4eee6f6b0bc178d58654f26f3ef2b9429332ab3`. This packet is qualification evidence only: no protected merge, deployment, Payroll execution, or real punches.

## Candidate disposition

| Item | Exact disposition | Evidence / action |
| --- | --- | --- |
| PR #216, Job labor and authoritative Clock Off | **INTEGRATED** | GitHub merged it as protected commit `d52d117`; protected contains the Job-clock/labor contracts. Do not replay its branch head. |
| PR #221, Payroll-input integrity | **SUPERSEDED** | Closed unmerged. Protected #229 (`ee88242`) supplies the current payable-time projection; protected #231 (`40f4425`) aligns corrected-time acceptance. Do not integrate #221. |
| PR #222, correction integrity | **SUPERSEDED** | Closed unmerged; `git cherry` identifies its correction patch as already patch-equivalent in protected authority. Do not integrate #222. |
| PR #225, time-source acceptance | **READY_TO_INTEGRATE** | Open, mergeable, no mechanical conflict against current protected. First live candidate in the remaining stack. |
| PR #226, correction staleness acceptance | **READY_TO_INTEGRATE** after #225 | Test/packet successor. |
| PR #232, period input assembly acceptance | **READY_TO_INTEGRATE** after #226 | Adds deterministic period packet and compensation resolution acceptance. |
| PR #234, period proration gate | **READY_TO_INTEGRATE** after #232 | Explicitly blocks a mid-period compensation change absent policy. |
| PR #239, proration policy | **READY_TO_INTEGRATE** after #234 | Adds governed policy and migration `e5g7i9k1m3o5`. |
| PR #240, proration acceptance | **READY_TO_INTEGRATE** after #239 | Acceptance-only successor. |

All six remaining candidate tips produce a clean `git merge-tree` result against the recorded protected SHA. Their GitHub stacked bases are clean/mergeable. Recheck immediately before each integration because protected is advancing.

## Dependency and migration order

```text
protected #216/#229/#231
  Job clock -> current accepted Workday revision -> correction/supersession
    -> #225 payable source identity -> #226 stale predecessor exclusion
      -> #232 Payroll-period packet + effective compensation authority
        -> #234 explicit mid-period-change gate
          -> #239 governed proration policy + work-date allocation
            -> #240 boundary/overlap/replay acceptance
```

Enterprise integration order is **#225, #226, #232, #234, #239, #240**. Do not merge #221 or #222.

Protected currently has one Alembic head, `d4f6h8j0l2n4`. PRs #225–#234 add no migration. PR #239 adds `e5g7i9k1m3o5` with `down_revision = d4f6h8j0l2n4`; #240 adds none. Expected composed head is exactly `e5g7i9k1m3o5`.

## Release acceptance matrix

| Guarantee | Primary evidence |
| --- | --- |
| Clock Off uses authoritative stop evidence; loss retry is idempotent | `tests/timekeeping/test_job_clock_operations.py` |
| Only accepted/current evidence is payable; open clock is zero | `tests/timekeeping/test_payroll_time_source_acceptance.py` |
| Corrected predecessor contributes zero; successor invalidates stale projection | same source-acceptance suite plus #226 |
| Overlapping accepted time fails closed | Workday authority and source-acceptance suites |
| Job labor and Payroll share accepted revision identity | `test_job_labor_and_payroll_bind_the_same_accepted_revision_once` |
| Compensation resolves by effective work date and scope | period assembly and proration-policy suites |
| Unauthorized compensation overlap fails closed | policy-authority and proration-policy suites |
| Policy is explicit; unselected/block/work-date are deterministic | `test_compensation_proration_policy.py` |
| No silent proration | #234 period gate and #239 explicit-policy contract |

## Exact post-composition qualification

Run in an isolated PostgreSQL database; never point these commands at operational data:

```bash
cd backend
ENVIRONMENT=test DATABASE_URL=<isolated-postgresql-url> PYTHONPATH=<isolated-deps>:. python -m alembic upgrade head
ENVIRONMENT=test DATABASE_URL=<isolated-postgresql-url> PYTHONPATH=<isolated-deps>:. python -m alembic current
PYTHONPATH=<isolated-deps>:. python -m alembic heads
ENVIRONMENT=test DATABASE_URL=<isolated-postgresql-url> PYTHONPATH=<isolated-deps>:. python -m pytest tests/timekeeping tests/payroll tests/operational_measurement -q
PYTHONPATH=<isolated-deps>:. python -m ruff check app/timekeeping app/payroll app/operational_measurement tests/timekeeping tests/payroll tests/operational_measurement
PYTHONPATH=<isolated-deps>:. python -m mypy app/timekeeping app/payroll app/operational_measurement
python -m compileall -q app/timekeeping app/payroll app/operational_measurement tests/timekeeping tests/payroll tests/operational_measurement
cd ..
git diff --check
```

Additionally run a fresh empty PostgreSQL zero-to-head migration, verify `current == heads == e5g7i9k1m3o5`, and run the repository credential/private-key scan. Frontend/mobile builds are required only if reconciliation changes their protected files; #225–#240 introduce no new client runtime contract.

## Reconciliation and rollback

- Do not merge old branch tips wholesale. Integrate the six PRs in order so each stacked delta stays reviewable.
- #225 contains older scheduling/test context. Protected scheduling has advanced; preserve protected implementation if a textual conflict appears and retain only the Payroll/time acceptance delta.
- #232's historical PR file list includes #216 ancestry. Since #216 is protected, verify the integration diff does not reintroduce Mobile/Job-clock changes.
- #239 was already reconciled through protected `9096a77`; protected has since advanced by #241–#243. Current merge-tree is clean, but re-fetch before integration.
- Schema rollback is application-sensitive: downgrade of #239 drops only the new proration-policy table, but must not be used after policy evidence exists without an explicit evidence-retention plan. Prefer application rollback while retaining schema.
- None of these candidates activates Payroll. If acceptance fails, stop the wave at the last integrated PR; do not bypass the proration gate or select a default policy.

## Deployment acceptance checks

Before any later Preview promotion, confirm authenticated Company/Employee scope, open clocks excluded, one current accepted revision per contribution, predecessor exclusion after correction, shared Job-labor/Payroll evidence identity, compensation effective-date selection, explicit approved proration policy for mid-period changes, stable replay digests, single migration head, and zero real Payroll execution. Production, tax filing, Accounting posting, and money movement remain prohibited.
