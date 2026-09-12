# PAYROLL.TIME.SOURCE.ACCEPTANCE.1

## Authority and dependency

This acceptance candidate began at protected authority
`4514b5df6be66e50ee172085c622ae613e172086` and composes the exact, unmodified
heads of PRs #221 and #222. It should be integrated after #222; it does not
reimplement or amend either dependency.

## Accepted evidence chain

The PostgreSQL-backed acceptance suite proves:

1. replay-safe Job clock evidence derives one authoritative worked interval;
2. explicit Job participation binds that interval to the exact approved Workday
   revision through `paid_time_revision_id`;
3. Payroll seals that same Workday revision identity and digest once;
4. corrected predecessors disappear from current Payroll contribution while
   immutable correction lineage remains visible;
5. corrected/submitted evidence contributes zero until approval;
6. out-of-period Workday evidence contributes zero;
7. open clocks, unapproved Job participation, and overlapping approved evidence
   fail closed or contribute zero as applicable; and
8. Company scope mismatches are rejected.

Schedules are not an input. Job worked intervals do not independently create
paid time. No withholding, Payroll execution, Accounting posting, or payment is
performed.

## Qualification

Use a fresh PostgreSQL database:

```bash
cd backend
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic upgrade head
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" pytest \
  tests/timekeeping/test_payroll_time_source_acceptance.py \
  tests/timekeeping tests/payroll
ruff check app/timekeeping app/payroll tests/timekeeping tests/payroll
mypy app/timekeeping app/payroll
python -m compileall -q app
```

Also verify one Alembic head and run `git diff --check`.

All fixtures use synthetic Company, Employee, Job, and time identities. No real
payable Employee evidence is created.
