# OM2-C morning launch decision — 2026-09-12

## Authority

- Mission: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Mission file SHA-256:
  `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`
- Qualified protected authority: `2d8709c895e60faf7cc0251d6c8ac82311013613`
- Observed Preview backend: `b5dff4b0203fe9a725a0ff844279876f410cba12`
- Preview/current frontend index SHA-256:
  `a7a3a9a038a71ea2ef00e00638b4b4b642f6988a5e47ce8387a8b1dc81a842d7`

Preview health still names protected ancestor `b5dff4b`, but the production frontend
is byte-identical to current `2d8709c` and a read-only method probe proves the new
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
| CSR Customer → Location → Job → Appointment → calendar → Dispatch | Yes | Yes through `2d8709c` | Current frontend and Job-schedule route present; health version stale | No authenticated/source-backed run |
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

1. **OM1 Migration — qualification defect:** focused MyPy produces 15
   `attr-defined` errors in
   `backend/app/operational_migration/hcp_legacy_projection_preview_command.py` because
   `bindings` is typed as `tuple[object, ...]` while binding attributes are accessed.
2. **OM1 Migration — source gate:** 1,389 holds, 22 open Jobs without Location IDs,
   292 partially unmapped Appointments, native-field drift, and absent backup/restore
   receipt prohibit admission.
3. **OM2-B — pending implementation candidate:**
   `724398348b566f655d2bc7127c20beeb6be52d6c` exposes existing operating Payroll
   calculation evidence and tightens QBO consumer validation; it is not protected or
   deployed and was not substituted into OM2-C.
4. **Enterprise — release attestation:** health reports `b5dff4b` while current
   `2d8709c` frontend and new POST route are deployed. Correct the version evidence and
   prove one coherent release; route presence alone is not operator acceptance.
5. **OM1 Phone / Enterprise:** Lianne delivery, activation and login remain unproven.
6. **Laptop1 Phone:** physical Mobile acceptance remains pending.
7. **OM1 ECO:** live QBO production Company binding, token/realm readability and a
   bounded complete catalog remain unavailable.

## Safety result

No Preview mutation, real Customer/Employee communication, real or payable punch,
payment, refund, Accounting posting, money movement, HCP/QBO mutation, or Production
operation occurred.
