# WORKFORCE.TIME.PAYROLL.INPUT.INTEGRITY.1

## Boundary

This candidate adds a deterministic pre-seal Payroll-input projection over the
existing Workday Time authority. It does not calculate Payroll, withholding,
tax, compensation, or Accounting results.

`GET /api/v1/timekeeping/pay-periods/{pay_period_id}/employees/{employee_id}/payroll-input-projection`
requires Timekeeping approval authority and returns:

- current accepted Workday revision identities and evidence digests eligible for
  the period;
- excluded evidence with a stable, truthful reason;
- total eligible minutes; and
- a canonical projection digest for exact replay comparison.

The existing Payroll-input seal now applies the same current-revision selection
and independently rejects overlapping approved intervals. Open Job clocks are
reported as `open_job_clock_non_payable` and never add payable minutes.

## Source integrity

Payroll snapshots continue to bind the immutable Workday revision IDs and
digests. Job participation assertions bind that same `paid_time_revision_id`
when paid time is attributed to Job labor. A completed Job clock interval alone
does not create paid time and is not silently matched to a Workday revision;
explicit participation evidence remains required for that relationship.

Corrections remain append-only. The current successor revision is the only
candidate considered by the projection, while its correction lineage preserves
the superseded evidence. Scheduled Appointments are not an input to this
contract.

## Enterprise qualification

From a clean checkout at this commit, use a fresh PostgreSQL database and run:

```bash
cd backend
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic upgrade head
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" pytest \
  tests/timekeeping tests/payroll
ruff check app tests/timekeeping tests/payroll
mypy app/timekeeping app/payroll
python -m compileall -q app
```

Also run `git diff --check` and verify one Alembic head. No migration is added by
this candidate.

## Safety assertions

- No real Employee punch or payable record is created by qualification.
- No Payroll execution, posting, payment, Preview deployment, or Production
  mutation is authorized.
- PR #216 is not amended by this branch.
