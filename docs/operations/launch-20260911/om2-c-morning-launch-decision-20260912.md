# OM2-C morning launch decision — 2026-09-12

## Authority

- Mission: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Mission file SHA-256:
  `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`
- Qualified protected authority: `b2cf7b60f1c927b4ba24fc6a49513b7d19c26a94`
- Observed Preview backend: `b5dff4b0203fe9a725a0ff844279876f410cba12`
- Preview/current frontend index SHA-256:
  `18d32734b4fe23a46cffebd30d4fcff2893475a0609db59ed38e1f992c835de6`

Preview health still names protected ancestor `b5dff4b`, but the production frontend
is byte-identical to current `b2cf7b6` (whose PR #219 delta is backend/docs only) and a
read-only method probe proves the new
existing-Job scheduling path is present (`405`, `Allow: POST`). The version string is
therefore stale release metadata, not proof of an old backend. Preview PostgreSQL and
Redis report connected. Authenticated behavior remains unaccepted.

## Decision

**CONDITIONALLY QUALIFIED; NOT OPERATOR ACCEPTED.**

Current code and synthetic cross-domain behavior are qualified. Launch acceptance is
not complete because no sanctioned authenticated CSR or Employee session is available,
SOURCE.4 admission is prohibited, Lianne activation/login is unproven, physical Mobile
acceptance is external, and live QBO authority is unavailable. No HTTP status, static
asset, fixture test, or owning-lane packet is treated as operator acceptance.

## Lifecycle matrix

| Chain | Implemented | Integrated | Deployed | Operator accepted |
| --- | --- | --- | --- | --- |
| CSR Customer → Location → Job → Appointment → calendar → Dispatch | Yes | Yes through `b2cf7b6` | Current frontend and Job-schedule route present; health version stale | No authenticated/source-backed run; mutation classification defect |
| Employee → Job clock → Jobsite Hours → Timecard → Payroll evidence | Yes | Yes | Server/web through `b5dff4b`; Mobile client protected | No authenticated employee or physical-device run |
| Customer → Estimate → Invoice → AR/payment evidence | Yes | Yes | Server/web and static UI present | No authenticated operator run; no money movement |
| QBO source → ACP read model/UI | Yes, including GET-only connection probe | Yes through `198da22` | Routes present and auth-protected | No live realm/company evidence; unavailable state only |

## Independent qualification

- Fresh ephemeral PostgreSQL 16 upgraded from zero to the single Alembic head
  `d4f6h8j0l2n4`.
- Existing operational acceptance factory: 53 scenarios, 49 passed, 4 declared gates,
  0 failed, 144.589 seconds. The gates were Redis, real communications, physical Mobile,
  and real source acquisition.
- Redis gate separately mitigated using supported Redis 7 plus PostgreSQL with Redis
  required for readiness: 21 passed.
- Post-SOURCE.4 projection/gate harness: 21 passed.
- Current QBO read-probe/projection/Economics: 36 passed.
- Current Customer preferred-contact and Company role administration: 23 passed.
- Existing-Job → Appointment scheduling: 5 backend and 3 frontend files / 9 tests;
  focused Ruff/MyPy, ESLint, TypeScript and production build passed.
- Protected PR #218 checkpoint: 87/88 focused backend tests passed and 4 frontend
  files / 31 tests passed; frontend ESLint, TypeScript and production build passed.
  The one backend failure is a real mutation-coverage defect, detailed below.
- Employee/identity/clock/Timecard/Payroll preparation: 59 tests passed with fresh
  PostgreSQL 16 and supported Redis 7. Earlier Redis-unavailable and reused-fixture
  exceptions were invocation state, not product failures.
- Protected PR #219 Economics/labor readiness delta: 17 tests passed; focused Ruff
  and MyPy passed. The backend-only deployment is unproven while health names
  `b5dff4b`.
- Frontend: Customer/role 5 files / 54 tests; Scheduling/Dispatch 5 / 29; Employee/
  Payroll 4 / 14; Revenue 4 / 20. ESLint and TypeScript production build passed.
- Earlier current-chain evidence retained: backend intersections 441 passed; frontend
  109 files / 389 tests; Mobile 4 suites / 46 tests with TypeScript and ESLint passed.

All values above are fixture or isolated-service qualification unless explicitly
described as a Preview observation.

## Actual source evidence

OM1 Migration reports a September 12 GET-only HCP refresh at `2026-09-12T16:49:00Z`
and current decision digest
`5070aa62a8a86bfbd1249588e86f1f08d29ae433803ba05fdf8ee04b234e9025`.
This is owner-lane actual Preview evidence, not an OM2-C authenticated UI run.

- 383/383 bounded open-work Job relationship requests succeeded.
- 479 Appointments: 47 new, 6 changed, 426 unchanged versus sealed SOURCE.4 scope.
- 187 fully mapped and 292 partially unmapped technician dispositions.
- All 40 referenced Customers absent from the list endpoint resolved by sanctioned
  detail GETs.
- 22 open Jobs remain without provider Location identity.
- Canonical SOURCE.4 admission remains false: 5,121 exact successors, 1,389 holds,
  zero conflicts. The executor was not invoked.

The synthetic projection harness proves unmapped technicians remain `PARTIAL`, missing
lineage/native identity fails closed, tenant substitution and contradictory replay are
blocking, and missing Estimate/Invoice evidence is not fabricated. It cannot replace
post-admission operator acceptance.

## Exact pending deployed rerun

After Enterprise supplies sanctioned sessions and any admitted current projection:

1. CSR: verify Company/MAIN scope, total-aware Customer search/pagination and preferred
   contact; open Customer → Location → Job without context loss.
2. Calendar: verify the same authoritative Appointment in Month, Day, Week and Work
   Week; navigate month boundaries, crowded-day `+N more`, refresh and direct reload.
3. Dispatch: reconcile the same Appointment set; explicitly inspect unmapped,
   unassigned, missing-duration and canceled states without inferred availability.
4. Employee: verify server-resolved identity and MAIN membership; with Enterprise's
   non-payable synthetic protocol, start clock, reconcile response loss, refresh active
   state, stop, and verify the immutable Job interval.
5. Office: verify the same interval in Jobsite Hours and Timecard; confirm it is not
   payable until accepted paid-time evidence exists; verify correction lineage and
   stale Payroll calculation invalidation.
6. Revenue: inspect Customer → accepted Estimate snapshot → Invoice → AR/payment
   evidence; do not collect, apply, settle, refund, post, or communicate.
7. QBO: inspect production connection evidence and cash/accrual read models. Accept
   `blocked`/`historical` when authority or completeness is absent; never relabel it
   live.

## Routed defects and pending candidates

1. **Laptop1-A Scheduling / Operations — protected replay-governance defect:**
   release `68cdc38976fcfb2d5a20e7ce52fc78306bde91ce`; exact route
   `POST /api/v1/operations/jobs/{job_id}/schedule`; exact transition is route
   integration → platform mutation inventory. `app.main` OpenAPI exposes operation ID
   `schedule_existing_job_api_v1_operations_jobs__job_id__schedule_post`, but
   `backend/app/platform/idempotency/mutation-coverage.v1.json` has no corresponding
   entry. Expected: exactly one current classification with tenant scope and replay
   evidence. Actual: `test_every_mutating_operation_has_exactly_one_current_classification`
   fails with that sole missing identity. This blocks replay-governance qualification
   for the new operation; OM2-C did not repair another lane's implementation.
2. **OM1 Migration — qualification defect:** focused MyPy produces 15
   `attr-defined` errors in
   `backend/app/operational_migration/hcp_legacy_projection_preview_command.py` because
   `bindings` is typed as `tuple[object, ...]` while binding attributes are accessed.
3. **OM1 Migration — source gate:** 1,389 holds, 22 open Jobs without Location IDs,
   292 partially unmapped Appointments, native-field drift, and absent backup/restore
   receipt prohibit admission.
4. **OM2-B — pending implementation candidate:**
   `724398348b566f655d2bc7127c20beeb6be52d6c` exposes existing operating Payroll
   calculation evidence and tightens QBO consumer validation; it is not protected or
   deployed and was not substituted into OM2-C.
5. **Enterprise — release attestation:** health reports `b5dff4b` while current
   `b2cf7b6` frontend and new POST route are deployed. Correct the version evidence and
   prove one coherent release; route presence alone is not operator acceptance.
6. **OM1 Phone / Enterprise:** Lianne delivery, activation and login remain unproven.
7. **Laptop1 Phone:** physical Mobile acceptance remains pending.
8. **OM1 ECO:** live QBO production Company binding, token/realm readability and a
   bounded complete catalog remain unavailable.

PR #216 (`663cbd48fc44da9ea504aec46da0d1df936f2af7`) and PR #215
(`724398348b566f655d2bc7127c20beeb6be52d6c`) remain open, unintegrated and therefore
undeployed. Their focused deployed acceptance remains correctly gated.

## Safety result

No Preview mutation, real Customer/Employee communication, real or payable punch,
payment, refund, Accounting posting, money movement, HCP/QBO mutation, or Production
operation occurred.
