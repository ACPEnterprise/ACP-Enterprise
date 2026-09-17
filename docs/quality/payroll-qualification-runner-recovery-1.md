# Payroll qualification runner recovery 1

## Authority and proven failure

- Protected authority: `b527d75eecb2d271a29bcb0bacb9e1b16b33784b`.
- Operations authority: `4bd5fc98814b7542c5bfebaece3292fb36f75f71`.
- Replay baseline: `14f665e8683aa0b151d1bb46c1431962cadf2e3d`.

The sanctioned Redis qualification Compose file built `backend/Dockerfile`,
which intentionally removes pip from the hardened runtime image. Its container
command then attempted `pip install -r requirements-dev.txt`. The exact
reproduction exited 127 with `sh: 1: pip: not found`; Docker reported
`OOMKilled=false`, no State error, no memory/CPU limit, and an elapsed time of 11
seconds. This is a test-runner image/command mismatch, not a Payroll failure.

The separately reported disposable Python process that ended without a pytest
summary left no retained container, exit status, signal, or kernel/OOM evidence.
Its historical termination mechanism therefore cannot be truthfully inferred.
The recovered runner completed the same population normally with retained logs,
exit status, and Docker state.

## Bounded infrastructure correction

`backend/Dockerfile.test` uses the repository's exact pinned Python base image
and installs `requirements-dev.txt` during image construction. The production
Dockerfiles remain unchanged and continue to remove pip. The Redis qualification
Compose service now builds the test-only image and invokes `python -m pytest`
without runtime package installation.

The observed runner versions were Python 3.12.13, pytest 8.4.2,
pytest-asyncio 0.26.0, SQLAlchemy 2.0.54, asyncpg 0.31.0, psycopg 3.3.5, and
redis-py 6.4.0. The repository has bounded requirements rather than a resolved
Python lockfile; installation therefore uses the authoritative
`requirements-dev.txt` contract.

## Isolation and migration

Project `om2c-payroll-recovery` created its own internal Compose network,
PostgreSQL 16 Alpine service, Redis 7 Alpine service, and qualification image.
PostgreSQL and Redis data used tmpfs. No host ports were published and no
Preview, Production, or live-data connection existed.

Fresh zero-to-head passed and both `alembic current` and `alembic heads` reported
the sole head `q2s4u6w8y0a2`.

## Incremental runner proof

- One known PostgreSQL Payroll case: 1 passed in 1.68 seconds, exit 0.
- Representative release/run subset: 6 passed in 2.62 seconds, exit 0.
- Compose default PostgreSQL/Redis qualification: 21 passed in 12.54 seconds,
  exit 0.
- Every retained runner container reported `OOMKilled=false`.

## Exact 55-test database population

The population is the 16 Payroll test modules importing SQLAlchemy async
database machinery, excluding the independent cutover replay differential:

```text
tests/payroll/test_accounting_posting_authority.py
tests/payroll/test_accounting_posting_finalization.py
tests/payroll/test_adjustment_authority.py
tests/payroll/test_adjustment_calculation.py
tests/payroll/test_adjustment_finalization.py
tests/payroll/test_compensation_proration_policy.py
tests/payroll/test_gross_pay_finalization.py
tests/payroll/test_payment_execution_authority.py
tests/payroll/test_payment_release_authority.py
tests/payroll/test_payroll_run_finalization.py
tests/payroll/test_paystatement_authority.py
tests/payroll/test_paystatement_experience.py
tests/payroll/test_period_input_assembly_acceptance.py
tests/payroll/test_policy_authority.py
tests/payroll/test_remittance_foundation.py
tests/payroll/test_tax_deduction_finalization.py
```

Result: **55 passed, 0 failed, 0 skipped, 0 errors** in 13.39 seconds; process
exit 0, elapsed 17 seconds, `OOMKilled=false`.

## Ten-test replay differential

The exact database-backed selection is
`test_cutover_replay_safety.py` excluding its one non-database OpenAPI schema
test. It comprises the seven parametrized cutover operations, concurrent exact
duplicate, concurrent contradiction, and HTTP create/replay/contradiction.

| Selection | Baseline `14f665e8` | Operations `4bd5fc98` | Classification |
| --- | --- | --- | --- |
| create review replay/contradiction | PASS | PASS | `BASELINE_IDENTICAL` |
| save fact replay/contradiction | PASS | PASS | `BASELINE_IDENTICAL` |
| certify fact replay/contradiction | PASS | PASS | `BASELINE_IDENTICAL` |
| create bridge period replay/contradiction | PASS | PASS | `BASELINE_IDENTICAL` |
| write bridge fact replay/contradiction | PASS | PASS | `BASELINE_IDENTICAL` |
| certify bridge period replay/contradiction | PASS | PASS | `BASELINE_IDENTICAL` |
| approve review replay/contradiction | PASS | PASS | `BASELINE_IDENTICAL` |
| concurrent exact duplicate | PASS | PASS | `BASELINE_IDENTICAL` |
| concurrent contradictory command | PASS | PASS | `BASELINE_IDENTICAL` |
| HTTP create/replay/contradiction | PASS | PASS | `BASELINE_IDENTICAL` |

Baseline: 10 passed, 1 deselected in 7.59 seconds. Operations: 10 passed,
1 deselected in 7.01 seconds. New candidate-owned replay regressions: **0**.

No PR #413 Payroll product defect was proven. No Payroll product code, live data,
Payroll execution, Beta/Preview, or Production state was changed.
