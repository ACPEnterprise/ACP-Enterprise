# Scheduling and Dispatch operations maximum 2

## Authority

- Starting protected authority: `4574d17a27104ea997dd92f2e53bda7cb31b90fb`
- Branch: `work/om2c-scheduling-dispatch-operations-maximum-2`
- Reused calendar candidate: `636e2e99dc4e070025442f053cc2f8fe28f28238` (product `8bb3f802`, packet `537af291`), replayed without redesign as commits `29fba172` and `73b3554c`.
- Frozen Dispatch-board candidate `acdfb2c3` was not amended, merged, or rewritten.

## Product state

The reused calendar candidate supplies Day, Week, Work Week, Month, Needs Scheduling, dense-day overflow and drilldown, deterministic ordering, Branch-local date handling, current/open distinctions, Customer/Job navigation, readiness, conflict visibility, and responsive cards.

This successor adds:

- an authorized immutable Dispatch assignment-history read endpoint;
- actor, time, reason, prior/new state, and version in Appointment detail;
- current primary technician and additional crew in Appointment detail;
- canonical Workforce eligibility consumption on Appointment detail;
- visible blocked technicians rather than silent omission;
- bounded readiness labels derived from existing Workforce reason codes;
- machine-readable, non-executable future action-intent contracts;
- a real-record-only Preview acceptance checklist with an explicit owner mutation gate.

Primary replacement, crew add/remove, assignment release, conflict detection, optimistic versioning, replay protection, rescheduling, and controlled exception evidence already exist in protected authority and were not duplicated. The eligibility service remains Workforce-owned. `IDENTITY_NOT_READY` and `MEMBERSHIP_NOT_READY` are not emitted by the current canonical eligibility contract, so OM2-C does not fabricate those classifications; the closest canonical evidence remains `missing_workforce_profile`, `wrong_branch`, capability, availability, conflict, and inactive reasons.

## Cross-domain truth

- Office assignment to Employee My Day is already served through the canonical own-day projection and Mobile refresh/stale handling; this candidate does not implement Mobile UI.
- Job instructions remain bounded by existing Job, Location, Appointment-window, own-assignment, and field-service contracts. No financial or unrestricted Customer data was added.
- Beacon already catalogs unassigned Appointment, overdue Appointment, awaiting Dispatch, unavailable assigned resource, stalled Dispatch state, and arrival/execution mismatch. Unsupported policy-dependent signals remain explicitly unavailable rather than inferred.
- LIA's deterministic acceptance corpus already includes today, tomorrow, week, Needs Scheduling, unassigned, assigned-to-Job, conflicts, technician assignments, and exception/incomplete-evidence questions. LIA retains no mutation authority.

## Qualification

- Frontend Scheduling/Dispatch/Appointment detail: 14 files / 69 tests passed.
- Backend Dispatch API: 8 tests passed.
- Backend Dispatch service against a fresh isolated PostgreSQL database: 8 tests passed.
- Operations contract tests: qualified separately with the backend focused suite.
- Fresh zero-to-head Alembic migration passed; no migration was added by this candidate.
- Changed Python Ruff passed.
- Changed frontend ESLint passed.
- TypeScript and production build passed.
- Python compilation, MyPy, diff and protected-data checks are final-candidate gates.

## Owner gate

No real Customer, Appointment, Job, or Employee record was mutated. Real closure remains dependent on owner certification of the real technicians, an explicitly sanctioned real Appointment, coherent Preview deployment, and execution of `backend/operations/scheduling-dispatch-real-acceptance.v1.json` through normal product UI. Synthetic fallback is prohibited.

Preview and Production were not changed.
