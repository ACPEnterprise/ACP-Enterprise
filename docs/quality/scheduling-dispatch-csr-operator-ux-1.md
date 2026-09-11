# Scheduling / Dispatch / CSR operator UX qualification

Qualified 2026-09-10 from protected authority
`36cae7427d65130cbba38b77e66b881ddc8c828f`.

## Product boundary

- Reuses the authoritative Appointment, Scheduling, Dispatch, Job, Customer,
  Branch, and permission contracts.
- Month is an operating calendar: every loaded appointment remains selectable
  and exposes time, Job/Appointment identity, Customer readiness, technician,
  and lifecycle. A date opens the corresponding Day schedule.
- Unassigned includes both Jobs without a known Appointment time and
  Appointments without authoritative assignment/time evidence.
- Appointment detail navigates to Appointment, Job, and Customer authority.
- Rescheduling requires a separate human confirmation and continues through the
  existing versioned Scheduling mutation. Dispatch assignment continues through
  its existing eligibility and confirmation contract.
- Dispatch Intelligence proposals remain review-only and non-mutating.
- Date input tolerates its transient empty state without crashing. The UI names
  the device timezone and preserves appointment instants; truncated range
  results are explicitly partial.

## Qualification

- Frontend full suite: 109 files, 384 tests passed.
- Scheduling/Dispatch focused frontend suite: 6 files, 28 tests passed.
- Frontend ESLint: passed.
- TypeScript and Vite production build: passed.
- Fresh PostgreSQL zero-to-head migration: passed at the single head
  `c3e5g7i9k1m3`.
- Backend Scheduling/Dispatch suites: 88 passed, with four pre-existing
  SQLAlchemy transaction-deassociation warnings and no failures.
- `git diff --check`: passed.
- Credential/private-key pattern scan: passed.

One earlier broad test attempt was invalid because a disposable qualification
database was removed by an overlapping local test command. Its
`InvalidCatalogNameError` results are excluded; the isolated rerun above is the
authoritative qualification result.

No migration is introduced by this change. Preview deployment and Production
are outside this branch.
