# OM2-A Workforce/Time continuation handoff

## Authority

- Mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`.
- Mission file SHA-256: `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`.
- Protected starting authority: `b22297c65165280a761860198dc05441df4a4312`.
- Reconciled protected authority: `2d8709c895e60faf7cc0251d6c8ac82311013613`.
- PR #195 Job clock and PR #200 Job labor actuals are confirmed protected ancestors.
- Successor branch: `work/job-labor-actuals-continuation-1`.

## Completed continuation

The protected backend already owns Job clock, current active state, immutable worked
interval revisions, office Timecards, the Job labor-actuals queue, stale Payroll-time
input checks, and correction lineage. This successor does not recreate those domains.

Two remaining interoperability defects were repaired:

1. ACP Employee now admits the backend's latest action/event/completed-interval fields
   instead of stripping them at its runtime schema. A lost clock-off response is only
   classified committed after refresh returns a distinct authoritative stop event and
   completed interval identity. A merely inactive response remains unconfirmed and
   retains the original retry identity.
2. Operational labor evidence now accepts an authoritative Employee/Job relationship
   and worked interval whose Appointment is absent. This matches the native Job-clock
   contract. Appointment-scoped evidence remains supported; paid time is still
   prohibited from carrying Job or Appointment identity.
3. New Job-clock mutations now require a current Dispatch assignment for the
   authenticated Employee as either primary technician or active crew. The assignment
   must be `assigned`, `acknowledged`, or `reconciliation_required` and match Company,
   Branch, Job, and the supplied Appointment when present. Released assignments fail
   closed. Exact replay still recovers already-committed immutable evidence after an
   assignment changes.

No scheduled duration becomes worked duration. No Job interval becomes payable time.
No Production, Payroll execution, Accounting posting, or real Employee punch occurred.

## Qualification

- Fresh isolated PostgreSQL zero-to-head: passed; one head `d4f6h8j0l2n4`.
- Alembic drift check: passed.
- Affected Timekeeping, Payroll, Dispatch assignment, operational measurement,
  Economics, and Job tests: 195 passed.
- Focused operational labor/Economics compatibility: 17 passed.
- ACP Employee: 15 suites / 131 tests passed.
- Mobile ESLint and TypeScript: passed.
- iOS and Android Expo/Hermes exports: passed, 2.7 MB each.
- Affected Ruff, MyPy, Python compilation, and `git diff --check`: passed.

## Enterprise and acceptance handoff

Enterprise owns protected integration and Preview deployment. After deployment, use a
sanctioned non-payable synthetic Employee/Job fixture to verify:

1. clock on, foreground/reconnect, and active event stability;
2. clock off with an intentionally lost client response;
3. refresh returns the distinct stop event and completed interval identity;
4. the same interval appears in My Time, office Timecard, and Job labor actuals;
5. paid Workday evidence remains unchanged unless independently recorded;
6. an authorized correction preserves the original and exposes successor, actor,
   reason, and updated current projections.

Physical-device and authenticated Preview acceptance remain separate evidence gates;
route presence or an unauthenticated `401` is not sufficient.
