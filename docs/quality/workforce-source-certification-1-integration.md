# Workforce source certification 1 — Enterprise handoff

## Authority and boundary

- Reconciled protected authority: `fd732c76` (PR #338 integrated).
- Independent candidate: source-employee certification lineage only.
- Existing real-roster activation, onboarding, capability, availability, Dispatch,
  Mobile, Timekeeping, and Payroll contracts remain authoritative.
- Schema impact: Alembic revision `o5q7s9u1w3y5`, following
  `n4p6r8t0v2x4`.

## Durable owner certification

The candidate persists one Company-scoped current certification per exact
`source_system` and immutable `source_employee_id`, plus append-only revisions.
Each revision records the evidence reference and digest, source Branch evidence,
decision, prior revision, actor, time, reason, and any exact ACP Employee or
onboarding target.

Supported decisions are `CONFIRM`, `SELECT_EXISTING`, `CREATE_ONBOARD`, `HOLD`,
and `LEGACY_ONLY`. `CONFIRM` can use only the target already persisted in the HCP
crosswalk. `SELECT_EXISTING` requires an exact tenant-scoped Employee selected in
the UI. Hold and legacy decisions cannot carry a target. No name or email is used
as matching authority.

Optimistic revision checks prevent stale writes. The exact same decision is a
convergent replay; incompatible stale decisions fail closed. Company-scoped
foreign keys and partial unique indexes prevent cross-tenant targets and prevent
one active Employee or onboarding request from becoming the target of competing
source identities.

## Owner workflow

Team / Employees shows source identity, source system, Branch evidence, evidence
digest, mechanically supported target, current decision, and immutable history.
The owner selects an existing Employee by human-readable name/number or routes to
normal protected onboarding; no UUID entry is required. A human reason is
mandatory for every decision.

This candidate does not create a User, Employee, Membership, Branch grant, role,
credential, invitation, technician capability, availability, assignment, or
Mobile permission. `CREATE_ONBOARD` routes to the existing protected onboarding
workflow; subsequent automation remains separately audited.

## Qualification

- Source-certification and API-idempotency tests: passed (`15 passed` before
  protected reconciliation; focused suite remains green after reconciliation).
- Protected field-readiness tests: five non-database tests passed; two existing
  PostgreSQL tests could not start because host `postgres` is unavailable on this
  lane.
- Workforce route tests: `4 passed`.
- Ruff: passed.
- MyPy: passed.
- TypeScript production build: passed.
- ESLint: passed with zero warnings.
- Alembic reports one head: `o5q7s9u1w3y5`. Full offline emission is blocked by
  protected revision `k9i8g37f4d0b`, whose inspector calls are not supported by
  Alembic's `MockConnection`; this candidate does not modify that revision.
- Diff and secret checks are required again on the final commit.

## Enterprise acceptance

1. Apply Alembic through `o5q7s9u1w3y5` in the normal PostgreSQL deployment path.
2. Open Team / Employees with Workforce certification management authority.
3. Confirm one row appears per exact HCP source identity and no synthetic identity
   is presented as a real Employee.
4. Exercise each decision with exact evidence, including stale revision rejection,
   idempotent replay, competing Employee target rejection, and cross-Company target
   rejection.
5. Confirm `CREATE_ONBOARD` enters normal protected onboarding and does not itself
   create identity state.
6. Confirm the protected real-employee activation console and bounded MAIN field
   readiness remain unchanged.

No Preview or Production data was mutated, no identity was inferred, no employment
decision was automated, and no Payroll or money operation was performed.
