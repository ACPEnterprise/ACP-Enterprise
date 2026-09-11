# OM2-C launch acceptance status

Updated: 2026-09-10 America/New_York

## Authority and mission pin

- Mission ref: `origin/work/launch-20260911-mission`
- Mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Mission file SHA-256: `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`
- Current protected base: `42a4f68087d76247269bd4c8388f556dd62a8b5c`
- Isolated branch: `work/om2c-launch-20260911-e2e-acceptance-1`
- Mission activation evidence: mission commit at 2026-09-10 21:36:32 -0400.
- Mission authorization expiry: 2026-09-13 21:36:32 -0400, unless earlier
  completion, revocation, or safety stop applies.

## Current checkpoint

State: **WORKING — RELEASE ATTESTATION AND AUTHENTICATED ACCEPTANCE REQUIRED**.

The protected authority now includes the Job-clock backend, operator Month/calendar
workflow, and Customer roster navigation. OM2-C extended the existing Enterprise
operational acceptance scenario to select the landed Job-clock tests; no second
harness or shared runtime implementation was created.

Current-authority qualification on fresh PostgreSQL databases:

- Alembic: one head, `d4f6h8j0l2n4`, upgrade from zero passed.
- Extended Employee → Job clock → Timecard → Payroll scenario: 21 passed.
- Customer, Job, Scheduling, Dispatch, identity, employee access, Timekeeping,
  Payroll reporting, QBO projection/evidence and factory intersections: 441 passed.
- Frontend: 109 files / 389 tests passed.
- ESLint, TypeScript production build and runtime dependency audit: passed; runtime
  audit reports zero vulnerabilities.
- Focused Ruff, MyPy, Python compilation and `git diff --check`: passed.

These are **synthetic fixture and isolated-database results**, not deployed or real-
source acceptance.

## Deployed checkpoint

Preview URL: `https://preview.allcountyhomeservices.com`.

- `/backend-health` is healthy and reports Preview PostgreSQL and Redis connected.
- The backend reports release `00e0d5f0faad31f6ff0b85cdde903857a78b70fc`, not
  current protected authority `42a4f68087d76247269bd4c8388f556dd62a8b5c`.
- Preview index SHA-256 is now
  `5ffe996047bbddc8ff3b18a4c517b0529ad378741334738e47d70c30abd49895`.
- Current protected frontend build index SHA-256 is
  `5ffe996047bbddc8ff3b18a4c517b0529ad378741334738e47d70c30abd49895`.
- The deployed entrypoint and current Customer, Scheduling/Month, Workday and Payroll
  route bundles are byte-for-byte identical to the qualified local production build.
  This proves those static artifacts were deployed; it is not rendered or authenticated
  operator acceptance.
- `GET /api/v1/timekeeping/me/job-clock` initially returned `404`, then advanced to
  the same bounded `401` authentication response as other protected APIs. This proves
  the route landed between checkpoints, but not Employee identity, authorization or
  Job-clock behavior.
- Existing protected Customer, Scheduling, office Timecard, Payroll register and
  Migration readiness endpoints consistently return the bounded unauthenticated
  `401` response. This proves authentication enforcement only; it does not prove the
  rendered operator workflow or its source data.

Exact failed transition:

`protected 42a4f680 release → Preview current coherent deployment → authenticated
operator journey`

The frontend and route-presence checkpoints advanced, but the backend release identity
still contradicts protected authority. Route release attestation, migration, backup and
rollback verification to **OM1 Enterprise**. OM2-C must rerun with sanctioned sessions
after that checkpoint.

## Source-data evidence boundary

- Customer/HCP population: no admitted current population/as-of packet was available
  to this lane at this checkpoint. Fixture roster pagination is qualified; actual
  completeness is unverified.
- QBO: OM1 ECO's published candidate explicitly classifies live connection/readability
  as `BLOCKED_EXTERNAL`; no production client, token, exact-company binding, verified
  realm marker or sealed production run was available. Existing reports are historical
  evidence, not live acquisition. OM2-B has a compatible evidence candidate not yet in
  protected authority. Route acquisition to **OM1 ECO**, presentation to **OM2-B**, and
  rerun to OM2-C after protected integration/deployment. OM2-B candidate
  `e0210ef414b574f9e573cde4de7939d230be5e80` also preserves unavailable Payroll totals
  and office Timecard navigation but remains outside protected authority.
- Employee access: OM1 Phone's read-only Preview checkpoint reports the existing Lianne
  User/Membership/Employee/MAIN Branch graph intact, invitation valid and unconsumed,
  and delivery definitively failed without provider acceptance. This is actual Preview
  administrative evidence, but it is not OM2-C login/activation acceptance. Retry is
  owned by **OM1 Enterprise/OM1 Phone**; human receipt, activation and login remain
  separate subsequent checkpoints.
- Job clocks and Payroll: current fixtures prove Job clock evidence remains explicitly
  non-payable until accepted Workday Time and Payroll inputs exist. No real or payable
  test punch was made. Actual employee-to-office consistency remains pending a
  sanctioned segregated fixture and current Preview deployment.

Additional handoffs observed but not substituted for deployed acceptance:

- Laptop1-B candidate `c13f6c97893e26110fdf6bf7c15d24996443778b`
  adds complete Customer population traversal and booking-context checks; it is three
  commits ahead of protected authority.
- OM1 Phone candidate `ee6fb2ee1870f7632f813edeaa4a8b5767dbe03d`
  confirms the invitation remains valid/unconsumed and records Postmark server live
  readiness, but human receipt, activation and login remain pending.

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
