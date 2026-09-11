# OM2-C launch acceptance status

Updated: 2026-09-10 America/New_York

## Authority and mission pin

- Mission ref: `origin/work/launch-20260911-mission`
- Mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Mission file SHA-256: `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`
- Starting protected base: `42a4f68087d76247269bd4c8388f556dd62a8b5c`
- Current protected base: `d7222d0fb8b9419a7df4c8331dc6d2c7d162724d`
- Isolated branch: `work/om2c-launch-20260911-e2e-acceptance-1`
- Mission activation evidence: mission commit at 2026-09-10 21:36:32 -0400.
- Mission authorization expiry: 2026-09-13 21:36:32 -0400, unless earlier
  completion, revocation, or safety stop applies.

## Current checkpoint

State: **WORKING — CURRENT PROTECTED DEPLOYMENT AND AUTHENTICATED ACCEPTANCE REQUIRED**.

The protected authority now includes the Job-clock backend, operator Month/calendar
workflow, Customer roster/navigation, CSR service-request booking, QBO source-evidence
projection/presentation, Payroll/Timecard operating UI, and the fail-closed SOURCE.4
successor-classification runner. OM2-C
extended the existing Enterprise operational acceptance scenario to select the landed
Job-clock tests; no second harness or shared runtime implementation was created.

Current-authority qualification on fresh PostgreSQL databases:

- Alembic: one head, `d4f6h8j0l2n4`, upgrade from zero passed.
- Extended Employee → Job clock → Timecard → Payroll scenario: 21 passed.
- Customer, Job, Scheduling, Dispatch, identity, employee access, Timekeeping,
  Payroll reporting, QBO projection/evidence and factory intersections: 441 passed.
- Frontend: 109 files / 389 tests passed.
- ESLint, TypeScript production build and runtime dependency audit: passed; runtime
  audit reports zero vulnerabilities.
- Focused Ruff, MyPy, Python compilation and `git diff --check`: passed.
- After the protected advance through `e9377e7`, the newly integrated QBO projection,
  SOURCE.4 classification, break-even readiness, Customer booking, Scheduling/Month,
  and Dispatch presentation checks passed: 31 backend tests and 8 frontend files / 45
  tests. Frontend ESLint, TypeScript and production build also passed.
- After OM2-B UI integration at `9b7dd10`, its affected QBO evidence,
  Financial Reports, Payroll, Workforce and Timecard-navigation suite passed: 6 frontend
  files / 13 tests. Frontend ESLint, TypeScript and production build also passed.
- After identity-retry integration at `f3d886d`, 10 path-correct idempotency standard
  tests, focused Ruff, MyPy and Python compilation passed. The database-backed
  onboarding cases could not execute because the repository-required `postgres` host
  is unavailable while local Docker is stopped; that environment failure is excluded
  from product results. The owning lane's integrated packet reports its isolated
  database qualification, but OM2-C does not substitute that for an independent run.
- After the protected advance through `d7222d0`, focused QBO-response and Migration
  classification checks passed 7 backend tests; Timekeeping/QBO/Payroll/Workforce UI
  checks passed 5 files / 16 tests; frontend ESLint, TypeScript and production build,
  plus focused Ruff, passed. The PostgreSQL-dependent Job-clock/Timecard/Payroll rerun
  remains pending because local Docker is stopped.
- Focused MyPy found 15 `attr-defined` failures in the protected Migration-owned
  `backend/app/operational_migration/hcp_legacy_projection_preview_command.py`: its
  `bindings` parameter is annotated as `tuple[object, ...]` while the implementation
  reads binding attributes. This is routed to **OM1 Migration** and is not repaired in
  OM2-C.

These are **synthetic fixture and isolated-database results**, not deployed or real-
source acceptance.

## Deployed checkpoint

Preview URL: `https://preview.allcountyhomeservices.com`.

- `/backend-health` is healthy and reports Preview PostgreSQL and Redis connected.
- The backend reports release `00e0d5f0faad31f6ff0b85cdde903857a78b70fc`, not
  current protected authority `d7222d0fb8b9419a7df4c8331dc6d2c7d162724d`.
- Preview index SHA-256 is now
  `91b425a67105bafaa4d8817e13d786160d3f1c812bbcc0ba6e646a67d56ce425`.
- Current protected frontend build index SHA-256 is now
  `91b425a67105bafaa4d8817e13d786160d3f1c812bbcc0ba6e646a67d56ce425`.
- The deployed index exactly matches the qualified `9b7dd10` production build. This
  proves current static artifact deployment, not rendering, session authorization, or
  operator acceptance.
- `GET /api/v1/timekeeping/me/job-clock` initially returned `404`, then advanced to
  the same bounded `401` authentication response as other protected APIs. This proves
  the route landed between checkpoints, but not Employee identity, authorization or
  Job-clock behavior.
- Existing protected Customer, Scheduling, office Timecard, Payroll register and
  Migration readiness endpoints consistently return the bounded unauthenticated
  `401` response. This proves authentication enforcement only; it does not prove the
  rendered operator workflow or its source data.
- The registered Timecard/Payroll routes checked were
  `/api/v1/timekeeping/me/timecard`, `/api/v1/timekeeping/admin/timecard-review`,
  `/api/v1/timekeeping/pay-periods`, `/api/v1/payroll/operations/summary`,
  `/api/v1/payroll/operations/registers`, `/api/v1/payroll/reporting`, and
  `/api/v1/payroll/me/payroll-status`. Guessed plural paths outside the router returned
  `404` and are not classified as product or deployment failures.
- The newly protected QBO evidence route
  `GET /api/v1/accounting/source-evidence/qbo?basis=cash` advanced from `404` to the
  common bounded `401` in Preview, proving route deployment and authentication only.
  A read-only `GET` against the POST-only Operations service-request route returns
  `405`, which proves route presence but neither authenticated booking nor mutation.

Exact failed transition:

`protected d7222d0 release → coherent backend release attestation → authenticated
operator journey`

The frontend and route-presence checkpoints advanced, but the backend release identity
still contradicts protected authority. Route release attestation, migration, backup and
rollback verification to **OM1 Enterprise**. OM2-C must rerun with sanctioned sessions
after that checkpoint.

## Source-data evidence boundary

- Customer/HCP population: no admitted current population/as-of packet was available
  to this lane at this checkpoint. Fixture roster pagination is qualified; actual
  completeness is unverified.
- SOURCE.4: protected authority contains a read-only Preview successor-classification
  runner that can produce a qualified Enterprise admission packet. Its own contract
  explicitly never admits data. No executed packet or admission result is available to
  OM2-C, so actual-source acceptance remains gated rather than inferred from code.
- OM1 Migration's integrated read-only Preview packet reports 4,970 known identity
  projections plus 1,540 native Locations examined: 5,121 exact successors, 1,389
  ambiguous holds, and zero conflicts. Canonical admission is explicitly false; report
  digest `ddf33badaa56e18948718946d52ca30203935c971396e34d86db9b49811f3be7`.
  This is actual Preview classification evidence reported by the owning lane, not an
  OM2-C fixture result or post-admission operational pass.
- The September 11 GET-only HCP refresh also proves the August 27 SOURCE.4 seal is not
  current: it reports source changes including 50 added Customers and 48 added Jobs.
  OM2-C therefore cannot present SOURCE.4 as the current Customer → Appointment graph.
- QBO: OM1 ECO's published candidate explicitly classifies live connection/readability
  as `BLOCKED_EXTERNAL`; no production client, token, exact-company binding, verified
  realm marker or sealed production run was available. Existing reports are historical
  evidence, not live acquisition. OM2-B has a compatible evidence candidate not yet in
  protected authority. Route acquisition to **OM1 ECO**, presentation to **OM2-B**, and
  rerun to OM2-C after protected integration/deployment. Latest observed OM2-B
  candidate `37597155167a04fed2a38af5b1387e745bf0fc00` preserves unavailable Payroll
  totals, office Timecard navigation, and consumes OM1 ECO's packet, but both
  candidates remain outside protected authority. OM1 ECO still reports that a
  company-scoped HTTP read model for source accounts, Invoices, Payments, bills/AP,
  balances, and report rows is unpublished.
- Employee access: OM1 Phone's read-only Preview checkpoint reports the existing Lianne
  User/Membership/Employee/MAIN Branch graph intact, invitation valid and unconsumed,
  and delivery definitively failed without provider acceptance. This is actual Preview
  administrative evidence, but it is not OM2-C login/activation acceptance. The
  audited retry for the original definitively rejected outbox identity is now protected
  at `f3d886d`, but execution/deployment is not established. Retry remains owned by
  **OM1 Enterprise/OM1 Phone**; provider acceptance,
  human receipt, activation and login remain separate subsequent checkpoints.
- Job clocks and Payroll: current fixtures prove Job clock evidence remains explicitly
  non-payable until accepted Workday Time and Payroll inputs exist. No real or payable
  test punch was made. Actual employee-to-office consistency remains pending a
  sanctioned segregated fixture and current Preview deployment.

Additional handoffs observed but not substituted for deployed acceptance:

- Latest observed Laptop1-B candidate
  `5f3e66b0248a22744bc4262c606f669e726952e0` adds deterministic page-one-to-page-two
  Customer roster and Job-selector traversal. Its own packet still requires protected
  integration, a coherent Preview deployment, and Migration's source admission packet.
- The protected OM1 Phone packet confirms the invitation remains valid and unconsumed
  and records Postmark server live readiness, but provider retry acceptance,
  human receipt, activation, login, and the post-activation mobile permission assignment
  remain pending.

## Operator rerun matrix

After a coherent current Preview deployment and sanctioned synthetic credentials:

1. CSR: sign in; verify role, Company and MAIN Branch; search the admitted Customer
   roster; record population count, pagination behavior and source as-of.
2. Customer: open a source-backed Customer, Location and related Job without losing
   context; verify direct reload and foreign-tenant/Branch concealment.
3. Job/calendar: open the authoritative Appointment, switch Day/Week/Work Week/Month,
   navigate previous/Today/next across month and timezone boundaries, open every item
   on crowded days through `+N more`, refresh, and prove identity/state stability.
4. Dispatch: verify the same appointments, assignments, unmapped technicians,
   canceled/historical state and no inferred availability.
5. QBO evidence: verify real company identity, source basis/date, last refresh,
   completeness and conflicts, or preserve the exact live authorization gate.
6. Employee access: separately verify delivery acceptance, human receipt, one-time
   activation, login, MAIN Branch and server-resolved Employee identity.
7. Job clocks: use only Enterprise-sanctioned non-payable synthetic evidence; verify
   start, visible active clock, response-loss replay, stop and refresh persistence.
8. Office Timecards/Payroll: verify the same Job interval is visible but not silently
   payable, approved/corrected time has lineage, and missing compensation/elections/tax
   rules remain blockers rather than zero.

Record rendered evidence or screenshots with no secrets or unnecessary PII. HTTP 200,
source presence, component tests and simulator results cannot replace these checks.

## Next action

Monitor protected authority and Preview release identity. When Enterprise deploys the
coherent checkpoint, rerun the deployed matrix immediately. Meanwhile, reconcile any
new QBO, Customer population, identity-delivery or Payroll evidence packets without
duplicating their owners' implementations.
