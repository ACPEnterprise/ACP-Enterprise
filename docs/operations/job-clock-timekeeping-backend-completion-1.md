# Job clock and Timekeeping backend completion

## Authority

- Protected starting authority: `36cae7427d65130cbba38b77e66b881ddc8c828f`.
- Branch: `work/job-clock-timekeeping-backend-completion-1`.
- This successor builds on integrated `WORKFORCE.JOBSITE.HOURS.1`, Timecard,
  pay-period, and audited correction authority.

## Phone API contract

- `POST /api/v1/timekeeping/me/job-clock` records `start` or `stop` using a
  mandatory caller-persisted `Idempotency-Key`.
- `GET /api/v1/timekeeping/me/job-clock` returns the authenticated Employee's
  active Job, optional Appointment, authoritative start, server observation,
  and elapsed seconds.
- `POST /api/v1/timekeeping/job-intervals/{revision_id}/corrections` creates an
  append-only correction successor under existing correction permission.

The mutation body never accepts Employee, Company, Branch, timestamp, or duration.
Those identities and times are resolved or observed by the backend. Phone retries must
reuse the same key until the original result is recovered.

## Evidence and safety

- Employee-scoped PostgreSQL advisory locks serialize Job clock state transitions.
- Exact replay reconstructs the original event and completed interval; contradictory
  replay fails with a conflict.
- Job/Branch and optional Job/Appointment relationships are verified before mutation.
- Current interval projection ignores superseded revisions without altering originals.
- Second-level duration preserves server-observed truth; whole minutes remain a derived
  display/compatibility value.
- Employee Timecard and administrative pay-period views expose current Job intervals
  separately from paid entries. Job evidence does not create paid time or Payroll input.
- Tests use only generated synthetic identities and an isolated qualification database.

## Migration and qualification

- Alembic: `c3e5g7i9k1m3 -> d4f6h8j0l2n4`.
- Fresh PostgreSQL zero-to-head: passed with one head.
- `alembic check`: no drift.
- Affected backend suite: 290 passed.
- Focused Job clock/domain suite: 18 passed.
- Frontend API/Workday tests: 15 passed.
- Affected Ruff, MyPy, Python compilation, ESLint, TypeScript, and production build:
  passed.

No live deployment, Production mutation, Payroll execution, Accounting posting, or
money movement is authorized by this packet.
