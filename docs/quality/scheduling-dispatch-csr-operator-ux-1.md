# Scheduling / Dispatch / CSR operator UX qualification

Initially qualified 2026-09-10 from protected authority
`36cae7427d65130cbba38b77e66b881ddc8c828f`; reconciled and requalified after
protected integrations through `42a4f68087d76247269bd4c8388f556dd62a8b5c`.

## Product boundary

- Reuses the authoritative Appointment, Scheduling, Dispatch, Job, Customer,
  Branch, and permission contracts.
- Month is an operating calendar: the first three appointments expose time,
  Job/Appointment identity, Customer readiness, technician, and lifecycle;
  crowded days expose an accessible `+N more` control that opens the complete
  Day projection. A date also opens the corresponding Day schedule.
- Unassigned includes both Jobs without a known Appointment time and
  Appointments without authoritative assignment/time evidence.
- Appointment detail navigates to Appointment, Job, and Customer authority.
- Rescheduling requires a separate human confirmation and continues through the
  existing versioned Scheduling mutation. Dispatch assignment continues through
  its existing eligibility and confirmation contract. A successful reschedule
  invalidates Schedule, Appointment detail, and Dispatch projections so the
  authoritative saved state is re-read.
- Dispatch Intelligence proposals remain review-only and non-mutating.
- Authorized CSR/office users can book Customer work through the existing
  atomic Operations service-request command. Customer search is bounded,
  Service Location and Branch are server-validated, the time window is shown
  in local time, and a separate confirmation is required before the Appointment
  and related draft Job are persisted. Technician assignment remains a
  separate, human-confirmed Dispatch command.
- Date input tolerates its transient empty state without crashing. The UI names
  the device timezone and preserves appointment instants; truncated range
  results are explicitly partial. Local half-open date ranges retain their
  calendar boundaries across spring/fall daylight-saving transitions without
  assuming that every local day is exactly 24 hours.

## Qualification

- Frontend full suite: 111 files, 395 tests passed.
- CSR booking, crowded Month drill-down, DST boundaries, and post-reschedule
  projection reconciliation focused suite: 5 files, 22 tests passed.
- Crowded Month drill-down and post-reschedule projection reconciliation:
  2 files, 16 tests passed.
- Frontend ESLint: passed.
- TypeScript and Vite production build: passed.
- Operations Ruff, Operations/Scheduling/Dispatch MyPy, and backend Python
  compilation: passed. A wider pre-existing Ruff check still reports only the
  import ordering in `app/scheduling/query.py`; this frontend capability does
  not rewrite that authoritative backend file.
- Fresh PostgreSQL zero-to-head migration: passed at the single head
  `c3e5g7i9k1m3`.
- Backend Operations/Scheduling/Dispatch suites: 92 passed against a fresh
  zero-to-head PostgreSQL database, with four pre-existing
  SQLAlchemy transaction-deassociation warnings and no failures.
- `git diff --check`: passed.
- Credential/private-key pattern scan: passed.

One earlier broad test attempt was invalid because a disposable qualification
database was removed by an overlapping local test command. Its
`InvalidCatalogNameError` results are excluded; the isolated rerun above is the
authoritative qualification result.

No migration is introduced by this change. Preview deployment and Production
are outside this branch.
