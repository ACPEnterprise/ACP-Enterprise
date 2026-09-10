# WORKFORCE.JOBSITE.HOURS.1 integration packet

## Authority and lineage

- Protected starting authority: `9ff11122c4591d8738c11164caff829ef72dc729`.
- Recovered candidate: `c0ab29b0bd19fe9e2221a0bb0d1ed076f79ba2f5`.
- Candidate history was retained and protected authority was merged into the isolated
  `work/workforce-jobsite-hours-1` branch.
- Alembic successor: `a1c3e5g7i9k1 -> b2d4f6h8j0m3`.

## Operational boundary

`timekeeping_job_clock_events` holds immutable start/stop source evidence with
Company, Branch, Employee, Job, optional Appointment, recorder, source, timestamp,
request digest, and a recorder-scoped idempotency key.

`timekeeping_job_interval_revisions` holds derived or authorized-correction revisions
with start, stop, duration, source events, correction lineage, validity, confidence,
and evidence digest. Original revisions remain unchanged when a corrected successor is
created.

The domain contract rejects duplicate active work, Employee overlaps, unmatched stops,
scope-changing stops, contradictory replays, naive timestamps, and partial-minute
evidence. It permits multiple Employees on one Job and repeated intervals per Employee.
It never derives Job identity or worked duration from Appointment schedules or paid-time
records. Existing Workday Time remains the only paid-time authority.

## Enterprise qualification

From a fresh PostgreSQL database, set the repository's required test security settings
(`ENVIRONMENT=test` is sufficient for local synthetic qualification), then run:

```text
cd backend
alembic heads
alembic upgrade head
alembic current
pytest -q tests/timekeeping tests/jobs tests/workforce tests/operational_measurement
ruff check app/timekeeping tests/timekeeping/test_job_participation.py \
  alembic/versions/b2d4f6h8j0m3_create_job_worked_time_authority.py
mypy app/timekeeping/job_participation.py app/timekeeping/models.py
python -m compileall -q app alembic
git diff --check origin/customer-management-v1...HEAD
```

Expected migration result is one head, `b2d4f6h8j0m3`. This packet authorizes no
Production deployment, Payroll execution, Accounting posting, or money movement.

Repository-wide MyPy currently also reports two protected-baseline findings in
`app/operational_migration/hcp_legacy_projection_classification.py`; neither file nor
finding is changed by this candidate.
