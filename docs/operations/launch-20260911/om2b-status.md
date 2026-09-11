# OM2-B operating checkpoint

- Mission ref: `origin/work/launch-20260911-mission`
- Mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Mission file: `docs/operations/launch-20260911/mission.md`
- Activated: 2026-09-10 21:36 America/New_York
- Authorized continuation expiry: 2026-09-13 21:36 America/New_York
- Initial implementation base: `42a4f68087d76247269bd4c8388f556dd62a8b5c`
- Current reconciled protected authority: `f3d886d88f432953ea187d989583e068c46ff228`
- Lane branch: `work/qbo-accounting-evidence-ui-1`

## Current task

QBO/Accounting evidence UI contract reconciliation, followed by Payroll-period,
office Timecard, and operating-register acceptance.

## Current evidence

- OM1 ECO candidate `ecfada3984beb8298b68c2df0d7a200c07a084a5`
  defines `qbo-om2b-source-evidence/v1` and is reconciled into this lane.
- OM1 proved no sanctioned real-company OAuth/runtime/evidence configuration was
  available. Live QBO evidence remains `LIVE_QBO_AUTHORIZATION_BLOCKED`.
- Protected commit `d8999fc` now supplies the company-scoped
  `qbo-accounting-source-evidence/v1` HTTP read model for accounts/balances,
  Invoice/AR, vendors, bills/AP, Payments/applications, reports, completeness,
  pagination/catalog state, and conflicts. The UI has been reconciled to its
  exact provider-authorization and evidence-mode vocabulary.
- Protected authority contains Job-clock backend completion (`f4fa8fe`) and the
  integrated Payroll-period/Timecard office/register foundations (`567556e`,
  `fc23148`). OM2-B is qualifying and repairing the existing UI, not rebuilding it.
- Payroll aggregate cards now remain `Unavailable` when no approved run exists;
  blocked registers do not render zero liabilities without admitted calculations.
- Payroll-to-office-Timecard navigation now opens the requested Employee record.
- Frontend qualification: 114 files / 409 tests pass; ESLint, TypeScript, and the
  production Vite build pass.
- A fresh isolated PostgreSQL 16 database upgraded from base to the single current
  Alembic head `d4f6h8j0l2n4`. The complete Payroll + Timekeeping suites pass 135
  tests, and the complete QBO source suite passes 142 tests. The focused combined
  QBO packet/Timecard/Payroll persistence battery passes 13 tests.
- After protected ECO integration, the combined QBO + Payroll + Timekeeping
  backend suites pass 282 tests against the isolated PostgreSQL database.
- Read-only Preview inspection still reports backend release
  `00e0d5f0faad31f6ff0b85cdde903857a78b70fc`, not protected authority
  `f3d886d88f432953ea187d989583e068c46ff228`. The QBO evidence endpoint now
  correctly rejects unauthenticated access with `401`; this proves the
  authentication boundary, not source-data acceptance. Deployed
  current-authority acceptance remains blocked on Enterprise's coherent
  deployment, sanctioned login, and real-company QBO authorization.

## Remaining checks / next action

1. Enterprise integrates the later fail-closed QBO consumer hardening from this
   lane; protected already contains the earlier QBO/Payroll/Timecard UI packet.
2. Enterprise performs one coherent current-authority Preview deployment.
3. With sanctioned authentication and real-company QBO authorization, execute
   cash/accrual source-date, completeness, conflict, and unavailable-state checks.
4. Keep historical snapshots labeled stale/unverified and do not infer missing
   balances, Payroll inputs, posting authority, or live-source acceptance.

## Boundaries

No QBO/HCP mutation, source freeze, Accounting posting, money movement, Payroll
or tax transmission, Customer communication, Preview deployment, or Production.
No real balances, wages, elections, or tax inputs are inferred.
