# OM2-A Job clock and labor-actuals handoff

## Authority and scope

- Protected base: `42a4f68087d76247269bd4c8388f556dd62a8b5c`.
- Mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`.
- Mission file SHA-256: `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`.
- Candidate branch: `work/job-labor-actuals-queue-1`.

This candidate composes with the integrated Jobsite Hours and operational Job-clock
authority. It does not create payable time, run Payroll, post Accounting, or mutate a
live environment.

## Phone and office contract

- `POST /api/v1/timekeeping/me/job-clock` remains the start/stop mutation. The Phone
  persists and reuses its `Idempotency-Key` until it has reconciled the outcome.
- `GET /api/v1/timekeeping/me/job-clock` now returns the latest action, event,
  timestamp, and completed interval identity when inactive. This makes a successful
  stop distinguishable after a disconnect or app restart.
- Exact replay recovers committed immutable evidence even when the mutable
  Job/Appointment relationship changed after the original response was lost. New
  clock events still require current Job/Appointment scope.
- Current Timecard views expose Job intervals separately from paid-time entries.
  Corrections expose the correcting user and reason while retaining the original
  revision and complete lineage.
- `GET /api/v1/timekeeping/admin/pay-periods/{pay_period_id}/job-labor-actuals`
  supplies the bounded office queue. It admits only current valid, authoritative Job
  intervals as accepted labor actuals and separately reports overlap with accepted
  paid-time evidence. Missing overlap remains visible and never creates payable time.

## Time and Payroll evidence safety

- Payroll-period operations derive current approved Timecard revision identities and
  classify the sealed snapshot and gross calculation independently as `CURRENT`,
  `MISSING`, or `STALE_TIME_EVIDENCE`.
- Gross calculation persistence, review initiation, and review acceptance recompute
  the current approved Timecard revision set. A corrected or replaced revision makes
  the old calculation fail closed and requires a newly sealed snapshot and successor
  calculation.
- Job worked intervals remain actual Job-attribution evidence and never silently
  become paid time. Scheduled duration remains non-authoritative for worked duration.

## Reproducible qualification

All database tests used an isolated, freshly migrated PostgreSQL database and
synthetic identities only.

- Fresh PostgreSQL zero-to-head: passed; head `d4f6h8j0l2n4`.
- Focused Job-clock/office tests: 8 passed.
- Affected Timekeeping, Payroll, labor evidence, and productive-hour tests: 71 passed.
- Affected Ruff and MyPy: passed.
- Shared frontend Timekeeping API tests: 6 passed.
- Frontend ESLint, TypeScript, and production build: passed.

Enterprise owns protected integration and Preview deployment. After deployment,
acceptance must verify authenticated start, active refresh, stop, inactive reconnect,
office Timecard visibility, append-only correction display, stale calculation status,
and unchanged historical evidence using sanctioned synthetic fixtures. Production and
real payable Employee records remain out of scope.
