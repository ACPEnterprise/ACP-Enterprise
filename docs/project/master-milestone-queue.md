# Master Milestone Queue

## Authority and use

This file is the single version-controlled sequencing and status record for ACP
Enterprise milestones across the workstreams below. Its recorded baseline is the
`customer-management-v1` repository at
`e0f68972f65bfec7272dd133060b348375497b3e` on 2026-08-05. Production is not a
queue target and must remain untouched unless a separate, explicit production
approval is recorded outside this document.

Only these status values are valid:

- `PLANNED`
- `READY`
- `IN PROGRESS`
- `WAITING FOR OWNER REVIEW`
- `DEPLOYING / VALIDATING`
- `COMPLETE`
- `BLOCKED`

An entry marked **provisional** reserves sequence only. Its code, title, scope,
dependency, assignment, and approval remain subject to owner confirmation; it
does not authorize work. No provisional entry represents completed work.

## Phase 2 program control

### Development strategy

Phase 2 uses this queue as the authoritative control plane for development,
integration, preview validation, release readiness, and owner acceptance. Work
proceeds as small owner-approved milestones on explicitly assigned machines or
isolated repositories. Enterprise Product, Customer Migration, and Business
Economics may progress in parallel only while their code, data, and Alembic
boundaries remain isolated. Architecture is approved and recorded independently
before or alongside implementation; an approved architecture document never
implies that its implementation is complete.

Integration is serialized through Laptop 1 after a workstream records review
evidence, an exact commit, and a clean handoff. Preview validation remains
separate from commit and push approval, owner acceptance remains separate from
preview success, and Production requires its own explicit release approval.
Provisional queue slots preserve planning visibility but grant no implementation
or integration authority.

### Owner dashboard

This is the Phase 2 single-page executive view as of 2026-08-05.

| Executive signal | Current record |
| --- | --- |
| Completed today | `MMQ.1` — Master Milestone Queue Foundation; `MMQ.2` — Phase 2 Program Control Foundation |
| Currently running | `EST.2` on Office Machine 1; `INV.1` on “Machine 2”; `CUTOVER.1` in the Migration Repository; Business Economics `Phase 7` in the Business Economics Repository |
| Waiting for review | None recorded |
| Blocked | No milestone is currently recorded as `BLOCKED`; unresolved assignments and future sequencing remain owner decisions |
| Next approvals expected | Assign and Start `PE-TELEMETRY-1`; confirm `EST.2`/`INV.1` integration order and isolated lineage |

### Pipeline dashboard

“Next three milestones” lists the three positions after the current milestone.
Provisional positions remain non-authorizing.

| Pipeline | Current milestone | Next milestone | Next three milestones | Assigned machine | Current status | Blocking dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| Enterprise | `EST.2` and parallel isolated `INV.1` | `EP-TBD-1` (provisional) | `EP-TBD-1`; then two undefined provisional positions | Office Machine 1 (`EST.2`); “Machine 2” (`INV.1`) | `IN PROGRESS` | Integration order, exact branches/commits, and isolated Alembic parents are unconfirmed |
| Migration | `CUTOVER.1` | `CM-TBD-1` (provisional) | `CM-TBD-1`; `CM-TBD-2`; then one undefined provisional position | Migration Repository; execution machine not recorded | `IN PROGRESS` | Exact dependency set, branch, commit, machine, and active migration parent are unconfirmed |
| Business Economics | `Phase 7` | `BE-TBD-1` (provisional) | `BE-TBD-1`; `BE-TBD-2`; then one undefined provisional position | Business Economics Repository; execution machine not recorded | `IN PROGRESS` | Phase 7 scope evidence, branch, commit, assignment, and migration base are unconfirmed |
| Architecture | `ARCH-TBD-1` (provisional) | `ARCH-TBD-2` (provisional) | `ARCH-TBD-2`; `ARCH-TBD-3`; then one undefined provisional position | Unassigned | `PLANNED` | Owner must approve the first Phase 2 architecture code, title, scope, and sequence |
| Platform | `PE-TELEMETRY-1` | `PE-TBD-1` (provisional) | `PE-TBD-1`; `PE-TBD-2`; then one undefined provisional position | Repository `ACP-Enterprise`; no machine assigned | `READY` | Telemetry requires machine assignment and explicit Start |
| AI | `AI-TBD-1` (provisional) | `AI-TBD-2` (provisional) | `AI-TBD-2`; `AI-TBD-3`; then one undefined provisional position | Unassigned | `PLANNED` | No AI milestone code, scope, dependency, repository, or approval is recorded |
| Integration / Release | `IR-TBD-1` (provisional) | `IR-TBD-2` (provisional) | `IR-TBD-2`; `IR-TBD-3`; then one undefined provisional position | Laptop 1 capability; no milestone assigned | `PLANNED` | No integration target is approved; active workstream commits and Alembic order are unknown |

### Machine registry

Repository and branch values are recorded only when authoritative. A repository
entry in this table can represent an isolated execution capacity even when its
physical machine is not recorded.

| Machine / capacity | Repository | Branch | Current milestone | Status | Last completed milestone |
| --- | --- | --- | --- | --- | --- |
| Office Machine 1 | Repository not recorded | Branch not recorded | `EST.2` | `IN PROGRESS` | Not recorded |
| Office Machine 2 | Repository not recorded | Branch not recorded | Unassigned; relationship to “Machine 2” is unconfirmed | `READY` (assignment unconfirmed) | Not recorded |
| Laptop 1 | Integration repository not recorded | Branch not recorded | No active milestone | `READY` | Laptop 1 integration/release capability |
| Migration Repository | Repository location not recorded | Branch not recorded | `CUTOVER.1` | `IN PROGRESS` | `SOURCE.5` |
| Business Economics Repository | Repository location not recorded | Branch not recorded | `Phase 7` | `IN PROGRESS` | `Phase 6` |

The supplied active assignment for `INV.1` remains “Machine 2.” Until the owner
confirms that label means Office Machine 2, it is not assigned to the Office
Machine 2 registry record.

### Capacity dashboard

No completion dates were supplied. “Unknown” is therefore used instead of an
invented estimate.

| Machine | Repository | Current milestone | Estimated completion | Next queued milestone |
| --- | --- | --- | --- | --- |
| Office Machine 1 | Not recorded | `EST.2` | Unknown | No approved successor; `EP-TBD-1` is provisional |
| Office Machine 2 | Not recorded | Unassigned | Not applicable | None approved; `INV.1` relationship requires owner confirmation |
| Laptop 1 | Integration repository not recorded | No active milestone | Not applicable | `IR-TBD-1` is provisional and not approved |
| Migration Repository | Location not recorded | `CUTOVER.1` | Unknown | `CM-TBD-1` (provisional) |
| Business Economics Repository | Location not recorded | `Phase 7` | Unknown | `BE-TBD-1` (provisional) |

### Workstream health

Health is a delivery signal, not a milestone status. `GREEN` means the recorded
work can proceed within known controls, `YELLOW` means progress exists but an
owner decision or missing control record needs attention, and `RED` means work
must stop. These ratings do not replace milestone status.

| Workstream | Health | Explanation |
| --- | --- | --- |
| Enterprise | `YELLOW` | Two milestones are active in parallel, but their integration order, exact commits, and migration parents are not recorded |
| Migration | `YELLOW` | `CUTOVER.1` is active, but its machine, branch, current commit, exact dependencies, and Alembic parent remain unknown |
| Economics | `YELLOW` | Phase 7 is active, but its assignment, branch, commit, evidence, and migration base remain unknown |
| Platform | `GREEN` | MMQ.1 and MMQ.2 are owner-approved as `COMPLETE`, and the next telemetry milestone is defined as `READY` |

### Integration queue

An item appears in the earliest gate it has reached. Empty gates are explicit so
absence is not confused with missing tracking. Movement between gates requires
the approval and evidence described in [Governance rules](#governance-rules).

| Gate | Milestones | Required evidence or current reason |
| --- | --- | --- |
| Waiting for Review | None | No reviewed milestone is waiting for an owner decision |
| Ready for Commit | `MMQ.1`; `MMQ.2` | Owner approved one documentation commit; commit state at document finalization is pending until the commit containing this file is created |
| Ready for Push | None | No committed milestone has explicit push approval |
| Ready for Preview | None | No pushed integration candidate is recorded |
| Ready for Owner Acceptance | None | No Phase 2 preview candidate awaits acceptance |

### Release ledger

This ledger tracks milestones represented as production-quality by supplied
completion state or repository evidence. “Not recorded” never implies that a
push, preview, deployment, or Production release occurred. Production remains
untouched.

| Milestone | Commit | Branch | Preview release | Deployment status | Rollback reference |
| --- | --- | --- | --- | --- | --- |
| Dispatch Assignment V1 | `2749512`; permission follow-up `60c95f2` | `customer-management-v1` | Not recorded | Not recorded | Not recorded |
| `PRICEBOOK.1` | `e97dc40` | `customer-management-v1` | Not recorded | Not recorded | Not recorded |
| `EST.1` | `e0f68972f65bfec7272dd133060b348375497b3e` | `customer-management-v1` | `EST.1` Preview deployment is `COMPLETE`; release identifier not recorded | Preview complete; Production not authorized or recorded | Not recorded |
| `LOCATION.2` | Not recorded | Not recorded | Not recorded | Not recorded | Not recorded |
| `SOURCE.5` | Not recorded | Not recorded | Not recorded | Not recorded | Not recorded |
| Business Economics Phase 5 | Not recorded | Not recorded | Not recorded | Not recorded | Not recorded |
| Business Economics Phase 6 | Not recorded | Not recorded | Not recorded | Not recorded | Not recorded |
| Phone-first workflow | Not recorded | Not recorded | Not recorded | Not recorded | Not recorded |
| `MC.1` | Evidence includes `6ac4934`; exact completion boundary not recorded | `customer-management-v1` | Not recorded | Not recorded | Not recorded |

The architecture completion and Laptop 1 capability are tracked in their owning
ledgers rather than represented as deployable product releases.

### Architecture ledger

Architecture approval and implementation completion are independent records.
Only the supplied approved architecture milestone is listed; no approval is
inferred from the presence of other files under `docs/architecture/`.

| Architecture record | Architecture status | Document / evidence | Related implementation | Implementation status | Notes |
| --- | --- | --- | --- | --- | --- |
| Inventory & Purchasing Architecture V1 | `COMPLETE` | Approved document path and commit not recorded | `INV.1` | `IN PROGRESS` | Architecture completion does not mark invoice implementation complete |

### Governance rules

This queue is the authoritative Phase 2 program-control record. No milestone may
skip it, and no branch, machine state, commit, preview, or deployment silently
changes queue state.

1. **Before implementation:** every milestone must enter the active or
   provisional register. Implementation may start only after the owner replaces
   any provisional definition, approves the milestone, assigns its execution
   boundary, and changes its state to `READY`, followed by explicit Start and
   `IN PROGRESS`.
2. **When approved:** record the approval boundary, dependencies, assignment,
   acceptance evidence, and migration ownership, then change the queue state in
   the same reviewed documentation change.
3. **After commit:** record the immutable commit and branch in the milestone and
   release/integration ledgers. A commit does not authorize a push; update the
   Integration Queue only after the separate review decision.
4. **After deployment:** record the environment, preview/release identifier,
   deployed commit, validation result, rollback reference, and state change.
   Preview deployment does not authorize Production.
5. **After owner acceptance:** record the acceptance evidence and date, update
   the milestone to `COMPLETE`, and update the completed and release ledgers in
   the same change.
6. Every transition into `WAITING FOR OWNER REVIEW`, `DEPLOYING / VALIDATING`,
   `COMPLETE`, or `BLOCKED` must include the evidence, responsible boundary, and
   next action. Missing evidence prevents advancement.
7. The Pipeline, Machine, Capacity, Integration, Release, Architecture, Health,
   Owner, active, completed, commit, and Alembic views must agree. A discrepancy
   stops new milestone pulls until the owner reconciles this file.

## Immediate queue

Position 1 is current or next. Positions 2 and 3 are intentionally provisional
where the owner has not supplied an approved code or order.

| Workstream | 1 | 2 | 3 |
| --- | --- | --- | --- |
| Enterprise Product | `EST.2` — `IN PROGRESS` | `INV.1` — `IN PROGRESS` in parallel on its isolated assignment | `EP-TBD-1` — `PLANNED` (provisional) |
| Customer Migration | `CUTOVER.1` — `IN PROGRESS` | `CM-TBD-1` — `PLANNED` (provisional) | `CM-TBD-2` — `PLANNED` (provisional) |
| Business Economics | `Phase 7` — `IN PROGRESS` | `BE-TBD-1` — `PLANNED` (provisional) | `BE-TBD-2` — `PLANNED` (provisional) |
| Architecture | `ARCH-TBD-1` — `PLANNED` (provisional) | `ARCH-TBD-2` — `PLANNED` (provisional) | `ARCH-TBD-3` — `PLANNED` (provisional) |
| Platform / Engineering | `PE-TELEMETRY-1` — `READY` | `PE-TBD-1` — `PLANNED` (provisional) | `PE-TBD-2` — `PLANNED` (provisional) |
| AI Platform | `AI-TBD-1` — `PLANNED` (provisional) | `AI-TBD-2` — `PLANNED` (provisional) | `AI-TBD-3` — `PLANNED` (provisional) |
| Integration / Release | `IR-TBD-1` — `PLANNED` (provisional) | `IR-TBD-2` — `PLANNED` (provisional) | `IR-TBD-3` — `PLANNED` (provisional) |

## Active and ready milestone register

| Code | Milestone title | Workstream | Status | Assigned machine or repository | Dependency | Completion evidence or current authoritative commit | Next approved milestone | Scope boundary | Migration / Alembic notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `EST.2` | Estimate continuation | Enterprise Product | `IN PROGRESS` | Office Machine 1; repository/branch not recorded | `EST.1` | Current workstream commit unknown; shared authoritative repository baseline is `e0f68972f65bfec7272dd133060b348375497b3e` | Unknown; `EP-TBD-1` is only a provisional queue slot | Continue only the owner-approved estimate milestone; do not absorb invoice, migration, release, or production work | Any schema work must remain isolated until its base revision and integration order are recorded; do not independently extend shared Alembic head |
| `INV.1` | Invoice foundation | Enterprise Product | `IN PROGRESS` | Machine 2; repository/branch not recorded | Dependency not recorded | Current workstream commit unknown; shared authoritative repository baseline is `e0f68972f65bfec7272dd133060b348375497b3e` | Unknown; `EP-TBD-1` is only a provisional queue slot | Implement only the owner-approved invoice milestone; do not absorb estimate, migration, release, or production work | Treat invoice migration work as isolated from `EST.2`; integration must serialize both branches onto the then-authoritative Alembic head |
| `CUTOVER.1` | Customer cutover | Customer Migration | `IN PROGRESS` | Machine and repository/branch not recorded | `SOURCE.5` and prior migration readiness; exact dependency set not recorded | Current workstream commit unknown | Unknown; `CM-TBD-1` is only a provisional queue slot | Customer migration cutover preparation/execution within the approved non-production boundary; no Production mutation is authorized | Customer Migration owns its isolated migration chain until reconciliation; no Production Alembic execution is authorized |
| `Phase 7` | Business Economics Phase 7 | Business Economics | `IN PROGRESS` | Machine and repository/branch not recorded | `Phase 6` | Current workstream commit unknown | Unknown; `BE-TBD-1` is only a provisional queue slot | Only the approved Phase 7 economics outcome; no production accounting entries, production ledger authority, or unrelated product work | Any schema revision must be isolated from Enterprise Product and Customer Migration and rebased/reparented only during approved integration |
| `PE-TELEMETRY-1` | Live owner-started progress telemetry evidence | Platform / Engineering | `READY` | Repository `ACP-Enterprise`; machine not assigned | Phone-first workflow and `MC.1` | Ready-state evidence supplied by owner; current authoritative commit `e0f68972f65bfec7272dd133060b348375497b3e` | Unknown; `PE-TBD-1` is only a provisional queue slot | Collect and record live evidence for owner-started progress telemetry; no unrelated runtime expansion, deployment, or Production mutation | No migration is expected from evidence collection; any discovered schema need requires a separately approved milestone |

## Provisional queue-slot register

The following are planning placeholders, not approved execution milestones. Each
has status `PLANNED` solely to make its queue state machine-readable. An owner
must replace its provisional code/title and approve its scope before it can move
to `READY`.

| Code | Milestone title | Workstream | Status | Assigned machine or repository | Dependency | Completion evidence or current authoritative commit | Next approved milestone | Scope boundary | Migration / Alembic notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `EP-TBD-1` | Enterprise Product milestone TBD (provisional) | Enterprise Product | `PLANNED` | Unassigned; repository TBD | `EST.2` / `INV.1` ordering decision | None; not started | None approved | No work authorized until owner defines the milestone | Migration ownership TBD; cannot create a revision |
| `CM-TBD-1` | Customer Migration milestone TBD (provisional) | Customer Migration | `PLANNED` | Unassigned; repository TBD | `CUTOVER.1` | None; not started | None approved | No work authorized until owner defines the milestone | Migration ownership TBD; cannot create a revision |
| `CM-TBD-2` | Customer Migration milestone TBD (provisional) | Customer Migration | `PLANNED` | Unassigned; repository TBD | `CM-TBD-1` (provisional) | None; not started | None approved | No work authorized until owner defines the milestone | Migration ownership TBD; cannot create a revision |
| `BE-TBD-1` | Business Economics milestone TBD (provisional) | Business Economics | `PLANNED` | Unassigned; repository TBD | `Phase 7` | None; not started | None approved | No work authorized until owner defines the milestone | Migration ownership TBD; cannot create a revision |
| `BE-TBD-2` | Business Economics milestone TBD (provisional) | Business Economics | `PLANNED` | Unassigned; repository TBD | `BE-TBD-1` (provisional) | None; not started | None approved | No work authorized until owner defines the milestone | Migration ownership TBD; cannot create a revision |
| `ARCH-TBD-1` | Architecture milestone TBD (provisional) | Architecture | `PLANNED` | Unassigned; repository TBD | Owner sequencing decision | None; not started | None approved | No work authorized until owner defines the milestone | Architecture work must not create migrations unless separately approved |
| `ARCH-TBD-2` | Architecture milestone TBD (provisional) | Architecture | `PLANNED` | Unassigned; repository TBD | `ARCH-TBD-1` (provisional) | None; not started | None approved | No work authorized until owner defines the milestone | Migration ownership TBD; cannot create a revision |
| `ARCH-TBD-3` | Architecture milestone TBD (provisional) | Architecture | `PLANNED` | Unassigned; repository TBD | `ARCH-TBD-2` (provisional) | None; not started | None approved | No work authorized until owner defines the milestone | Migration ownership TBD; cannot create a revision |
| `PE-TBD-1` | Platform / Engineering milestone TBD (provisional) | Platform / Engineering | `PLANNED` | Unassigned; repository TBD | `PE-TELEMETRY-1` | None; not started | None approved | No work authorized until owner defines the milestone | Migration ownership TBD; cannot create a revision |
| `PE-TBD-2` | Platform / Engineering milestone TBD (provisional) | Platform / Engineering | `PLANNED` | Unassigned; repository TBD | `PE-TBD-1` (provisional) | None; not started | None approved | No work authorized until owner defines the milestone | Migration ownership TBD; cannot create a revision |
| `AI-TBD-1` | AI Platform milestone TBD (provisional) | AI Platform | `PLANNED` | Unassigned; repository TBD | Owner sequencing decision | None; not started | None approved | No AI Platform implementation is authorized by this placeholder | Migration ownership TBD; cannot create a revision |
| `AI-TBD-2` | AI Platform milestone TBD (provisional) | AI Platform | `PLANNED` | Unassigned; repository TBD | `AI-TBD-1` (provisional) | None; not started | None approved | No AI Platform implementation is authorized by this placeholder | Migration ownership TBD; cannot create a revision |
| `AI-TBD-3` | AI Platform milestone TBD (provisional) | AI Platform | `PLANNED` | Unassigned; repository TBD | `AI-TBD-2` (provisional) | None; not started | None approved | No AI Platform implementation is authorized by this placeholder | Migration ownership TBD; cannot create a revision |
| `IR-TBD-1` | Integration / Release milestone TBD (provisional) | Integration / Release | `PLANNED` | Laptop 1 capability available; assignment and repository TBD | Owner sequencing and integration readiness decision | None; not started | None approved | No merge, push, deployment, release, or Production action is authorized | Integration must reconcile all isolated revisions into one reviewed lineage before any release validation |
| `IR-TBD-2` | Integration / Release milestone TBD (provisional) | Integration / Release | `PLANNED` | Unassigned; repository TBD | `IR-TBD-1` (provisional) | None; not started | None approved | No merge, push, deployment, release, or Production action is authorized | No migration execution is authorized |
| `IR-TBD-3` | Integration / Release milestone TBD (provisional) | Integration / Release | `PLANNED` | Unassigned; repository TBD | `IR-TBD-2` (provisional) | None; not started | None approved | No merge, push, deployment, release, or Production action is authorized | No migration execution is authorized |

## Machine assignments

| Machine | Current assignment | Workstream | Status | Pull-next permission |
| --- | --- | --- | --- | --- |
| Office Machine 1 | `EST.2` | Enterprise Product | `IN PROGRESS` | No; complete the review/integration handoff and satisfy the pull rules below |
| Machine 2 | `INV.1` | Enterprise Product | `IN PROGRESS` | No; complete the review/integration handoff and satisfy the pull rules below |
| Laptop 1 | Integration/release capability established; no active milestone assigned | Integration / Release | `COMPLETE` capability | No automatic pull; owner must assign a defined milestone |
| Unrecorded machine | `CUTOVER.1` | Customer Migration | `IN PROGRESS` | No |
| Unrecorded machine | `Phase 7` | Business Economics | `IN PROGRESS` | No |
| Unassigned | `PE-TELEMETRY-1` | Platform / Engineering | `READY` | Only after explicit owner start/assignment |

Machine labels reflect the supplied authoritative state. “Machine 2” is retained
verbatim and is not assumed to mean “Office Machine 2.”

## Current authoritative commits

| Authority | Commit | Meaning |
| --- | --- | --- |
| Shared `ACP-Enterprise` repository, branch `customer-management-v1` | `e0f68972f65bfec7272dd133060b348375497b3e` | Queue baseline and current shared authoritative commit |
| Dispatch Assignment V1 | `2749512` with permission follow-up `60c95f2` | Repository evidence for completed dispatch assignment implementation |
| PRICEBOOK.1 | `e97dc40` | Repository evidence for completed price book foundation |
| EST.1 | `e0f68972f65bfec7272dd133060b348375497b3e` | Repository evidence for completed estimate foundation |
| `EST.2`, `INV.1`, `CUTOVER.1`, Business Economics `Phase 7` | Unknown | Active isolated-workstream commits were not supplied and are not asserted |

## Alembic lineage by isolated workstream

This table records known repository lineage and the required integration base; it
does not authorize migration edits or execution. The current repository has one
linear head at `r3h5c7d9f164`.

| Isolated workstream | Known lineage or base | Current isolation rule | Integration requirement |
| --- | --- | --- | --- |
| Shared Enterprise Product | `p1f3a5c7d942` (Dispatch) -> `q2g4b6d8e053` (Price Book) -> `r3h5c7d9f164` (Estimate) | `r3h5c7d9f164` is the shared authoritative head at this baseline | Any new revision must be based on the latest approved integrated head, not a stale local head |
| `EST.2` | Expected integration base is `r3h5c7d9f164`; local revision unknown | Must not share or assume the same child revision/base as `INV.1` | Record revision ID and parent before review; serialize integration with `INV.1` |
| `INV.1` | Expected integration base is `r3h5c7d9f164`; local revision unknown | Must remain isolated from `EST.2` migration work | The later-integrated workstream must rebase/reparent onto the accepted head and rerun migration validation |
| Customer Migration / `CUTOVER.1` | Known historical chain includes `e8b4c6d2a917` -> `f1c7d9e3b825` and `a2d8e4f6c930` -> `b3e9f5a7d041` -> `c4f0a6b8e152` -> `d5a1b7c9f263`; active local revision unknown | Migration-owned staging and cutover work remains isolated from product work | Reconcile against the latest shared head through reviewed integration; never execute against Production from a workstream machine |
| Business Economics / `Phase 7` | Active base and revision unknown | Maintain a dedicated isolated chain; do not attach a child concurrently to a shared base already claimed by another workstream | Owner-approved integration records the final parent and validates a single head |
| Platform / Engineering | Shared history through `o0e2f4a6c931`; no migration expected for `PE-TELEMETRY-1` | Evidence collection must not mutate lineage | A schema requirement becomes a separately approved milestone |
| AI Platform | No active lineage recorded | No revision may be created from provisional slots | Establish ownership and base before schema work |
| Integration / Release | Integrates rather than independently owning a feature lineage | Preserve applied history; do not rewrite accepted revisions | Prove one reviewed head and upgrade/downgrade/drift behavior in disposable non-production storage |

## Approval and execution rules

### Milestone-level approval

1. A milestone may move from `PLANNED` to `READY` only when the owner approves
   its code, title, purpose, scope boundary, dependencies, machine/repository,
   acceptance evidence, and migration ownership.
2. `READY` means defined and unblocked; it does not mean started. Only an explicit
   owner Start and machine assignment may move it to `IN PROGRESS`.
3. A machine stops at the approved milestone boundary. Scope expansion requires
   a new or amended owner approval and a queue update.
4. A completed implementation moves to `WAITING FOR OWNER REVIEW` with its exact
   commit/evidence and validation record. Owner approval is required before
   integration or release activity.
5. `DEPLOYING / VALIDATING` requires a separately approved target environment,
   immutable revision, migration plan where applicable, validation plan, and
   rollback boundary. Preview approval never implies Production approval.
6. `COMPLETE` requires accepted completion evidence. A commit, push, merge, or
   deployment alone does not imply completion.
7. Use `BLOCKED` only with the blocking fact, owner/action needed, and last known
   safe state recorded in this queue.

The repository's [Workstream Standard](../engineering/workstream-standard.md),
[Definition of Done](../engineering/definition-of-done.md), and
[Validation Standard](../engineering/validation-standard.md) remain applicable.

### Preventing parallel Alembic collisions

1. Each schema-changing milestone declares one migration owner, repository,
   branch/worktree, intended parent revision, and isolation boundary before work.
2. Two active workstreams must not independently publish children of the same
   Alembic head. Parallel local work stays isolated and is integrated serially.
3. Before integration, compare the accepted shared head with the recorded local
   parent. If they differ, the later workstream must rebase/reparent through an
   owner-reviewed migration edit; never create an accidental multi-head lineage.
4. Never rewrite a revision already applied to a shared environment. Resolve an
   accepted divergence with a reviewed merge migration only when deliberate and
   explicitly approved.
5. Integration validation must include `alembic heads`, upgrade from the agreed
   base, downgrade where safe, re-upgrade, and drift checking in disposable
   non-production storage as required by the
   [Database Standards](../engineering/database-standards.md).
6. Migration execution is a separate release action. No queue state authorizes
   Production migration execution.

### When a machine may pull the next milestone

A machine may pull only the first owner-approved `READY` milestone assigned to
it, and only when all of these are true:

- its current milestone is no longer `IN PROGRESS` and has a recorded handoff,
  review result, exact commit/evidence, and clean repository state;
- the owner has explicitly approved Start, the assignment, dependency state,
  scope, repository/branch, and migration ownership;
- the machine has refreshed from the recorded authoritative commit without
  overwriting another workstream;
- no unresolved Alembic parent collision or shared-file ownership conflict
  exists; and
- this queue is updated in the same change-control event.

Capacity availability, a completed capability, or a provisional queue position
does not grant pull authority. See also
[Branching and Release](../engineering/branching-and-release.md).

## Completed-milestone ledger

Only supplied or repository-supported completions appear here.

| Code / milestone | Title | Workstream | Status | Completion evidence |
| --- | --- | --- | --- | --- |
| Dispatch Assignment V1 | Dispatch Assignment V1 | Enterprise Product | `COMPLETE` | Commits `2749512` and `60c95f2` |
| `PRICEBOOK.1` | Price Book foundation | Enterprise Product | `COMPLETE` | Commit `e97dc40` |
| `EST.1` | Estimate foundation | Enterprise Product | `COMPLETE` | Commit `e0f68972f65bfec7272dd133060b348375497b3e` |
| `LOCATION.2` | Location migration milestone 2 | Customer Migration | `COMPLETE` | Owner-supplied status; exact completion evidence not recorded |
| `SOURCE.5` | Source migration milestone 5 | Customer Migration | `COMPLETE` | Owner-supplied status; exact completion evidence not recorded |
| Phase 5 | Business Economics Phase 5 | Business Economics | `COMPLETE` | Owner-supplied status; exact completion evidence not recorded |
| Phase 6 | Business Economics Phase 6 | Business Economics | `COMPLETE` | Owner-supplied status; exact completion evidence not recorded |
| Inventory & Purchasing Architecture V1 | Inventory & Purchasing Architecture V1 | Architecture | `COMPLETE` | Owner-supplied status; exact completion evidence not recorded |
| Phone-first workflow | Phone-first workflow | Platform / Engineering | `COMPLETE` | Owner-supplied status; exact completion evidence not recorded |
| `MC.1` | Mission Control Lineage Consolidation & Drift Prevention | Platform / Engineering | `COMPLETE` | Owner-supplied status; current shared baseline includes commit `6ac4934` (`prevent mission control contract drift`) |
| `EST.1` Preview deployment | EST.1 Preview deployment | Integration / Release | `COMPLETE` | Owner-supplied status; environment evidence not recorded in this repository baseline |
| Laptop 1 integration/release capability | Laptop 1 integration/release capability | Integration / Release | `COMPLETE` | Owner-supplied status; capability evidence not recorded |
| `MMQ.1` | Master Milestone Queue Foundation | Platform / Engineering | `COMPLETE` | Owner-approved completion in `docs/project/master-milestone-queue.md`; commit state at document finalization is pending until the commit containing this file is created |
| `MMQ.2` | Phase 2 Program Control Foundation | Platform / Engineering | `COMPLETE` | Owner-approved completion in `docs/project/master-milestone-queue.md`; commit state at document finalization is pending until the commit containing this file is created |

## Unresolved owner decisions

- Confirm the exact title and isolated repository/branch/current commit for
  `EST.2`, plus whether it or `INV.1` integrates first.
- Confirm whether “Machine 2” means “Office Machine 2”; this queue does not make
  that assumption.
- Confirm `INV.1`, `CUTOVER.1`, and Business Economics `Phase 7` dependencies,
  assignments, repository/branch names, current commits, acceptance evidence,
  and local Alembic revisions/parents.
- Supply the exact completion commits or evidence for completed milestones whose
  ledger entries currently cite owner-supplied status only.
- Define and approve the codes, titles, scopes, sequence, assignments, and
  dependencies replacing every `TBD` provisional slot, including the first AI
  Platform milestone.
- Assign a machine for `PE-TELEMETRY-1` and explicitly approve Start.
- Decide the next Integration / Release target and environment. Nothing in this
  queue authorizes a deployment or Production change.

## Change control

Every milestone status change must update this file in the same reviewed change.
The update must record the new status, date, exact evidence or authoritative
commit, assignment, dependencies, next approved milestone, scope changes,
blockers, and Alembic lineage impact. If execution state and this file disagree,
stop new pulls and reconcile the queue through owner review; do not silently
infer status from a branch, commit, machine heartbeat, preview, or deployment.
