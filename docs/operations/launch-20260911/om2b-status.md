# OM2-B operating checkpoint

- Mission ref: `origin/work/launch-20260911-mission`
- Mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Mission file: `docs/operations/launch-20260911/mission.md`
- Activated: 2026-09-10 21:36 America/New_York
- Authorized continuation expiry: 2026-09-13 21:36 America/New_York
- Implementation base at reconciliation: `42a4f68087d76247269bd4c8388f556dd62a8b5c`
- Lane branch: `work/qbo-accounting-evidence-ui-1`

## Current task

QBO/Accounting evidence UI contract reconciliation, followed by Payroll-period,
office Timecard, and operating-register acceptance.

## Current evidence

- OM1 ECO candidate `ecfada3984beb8298b68c2df0d7a200c07a084a5`
  defines `qbo-om2b-source-evidence/v1` and is reconciled into this lane.
- OM1 proved no sanctioned real-company OAuth/runtime/evidence configuration was
  available. Live QBO evidence remains `LIVE_QBO_AUTHORIZATION_BLOCKED`.
- The ECO packet supplies source identity, dates, basis-specific report controls,
  completeness, counts, pagination, conflicts/limitations, and immutable digests.
  A company-scoped HTTP read model for individual accounts, Invoices, Payments,
  bills/AP, balances, and report rows has not yet been published.
- Protected authority contains Job-clock backend completion (`f4fa8fe`) and the
  integrated Payroll-period/Timecard office/register foundations (`567556e`,
  `fc23148`). OM2-B is qualifying and repairing the existing UI, not rebuilding it.
- Payroll aggregate cards now remain `Unavailable` when no approved run exists;
  blocked registers do not render zero liabilities without admitted calculations.
- Payroll-to-office-Timecard navigation now opens the requested Employee record.
- Frontend qualification: 112 files / 394 tests pass; ESLint, TypeScript, and the
  production Vite build pass.
- A fresh isolated PostgreSQL 16 database upgraded from base to the single current
  Alembic head `d4f6h8j0l2n4`. The complete Payroll + Timekeeping suites pass 135
  tests, and the complete QBO source suite passes 142 tests. The focused combined
  QBO packet/Timecard/Payroll persistence battery passes 13 tests.

## Remaining checks / next action

1. Reconcile the QBO UI to the final OM1 ECO HTTP contract when published; do not
   deploy the provisional row client as if it were agreed or live.
2. Complete Payroll/Timecard UI tests for missing calculations, office drill-down,
   partial/empty/error recovery, and source-date preservation.
3. Run QBO packet, Payroll, Timekeeping, authorization, frontend, migration, and
   static qualification against current authority.
4. Push the updated candidate and hand Enterprise exact dependencies and deployed
   acceptance steps. Enterprise alone deploys Preview.

## Boundaries

No QBO/HCP mutation, source freeze, Accounting posting, money movement, Payroll
or tax transmission, Customer communication, Preview deployment, or Production.
No real balances, wages, elections, or tax inputs are inferred.
