# PAYROLL.COMPENSATION.PRORATION.POLICY.1 integration packet

## Boundary

This candidate adds an explicit Company-scoped compensation-proration policy authority and deterministic hourly allocation. It does not select an owner policy, calculate tax, execute Payroll, post Accounting, move money, or affect Production.

The candidate is stacked on the completed Payroll period assembly/proration-gate authority. Integrate after those dependencies, then reconcile migration `e5g7i9k1m3o5` to the protected single head if Enterprise migration authority has advanced.

## Contract

- `UNSELECTED`: explicit undecided state; cannot be approved and blocks allocation.
- `BLOCK_PAYROLL`: approved instruction to keep affected Payroll blocked.
- `BY_WORK_DATE`: each accepted hourly time revision maps to exactly one effective approved compensation authority.
- Salaried/non-hourly evidence fails closed as `POLICY_REQUIRED / SOURCE_REQUIRED`.
- Existing compensation authority digests remain unchanged. Successor lineage is projected as metadata so valid supersession is distinguishable from an illegal overlap.
- Allocation output binds policy identity/digest, time revision identity, compensation identity/digest, work date, minutes, and deterministic result digest.

## Migration

`e5g7i9k1m3o5_create_payroll_proration_policy.py` creates `payroll_compensation_proration_policy_versions`. Validate zero-to-head, `alembic current`, and exactly one head after protected reconciliation.

## Qualification command

Use an isolated PostgreSQL database and the repository-supported dependencies:

```bash
ENVIRONMENT=test DATABASE_URL=<isolated-postgresql-url> PYTHONPATH=<isolated-deps>:. python -m pytest tests/payroll tests/timekeeping -q
python -m ruff check app/payroll tests/payroll alembic/versions/e5g7i9k1m3o5_create_payroll_proration_policy.py
python -m mypy app/payroll/proration.py tests/payroll/test_compensation_proration_policy.py
python -m compileall -q app/payroll tests/payroll
alembic upgrade head
alembic current
alembic heads
git diff --check
```

Synthetic fixtures only were used. No real payable punches or Payroll execution occurred.
