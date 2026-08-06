# Master Milestone Queue

## Authority and use

This file is the single version-controlled sequencing and status record for ACP
Enterprise milestones across the workstreams below. Its recorded baseline is the
`customer-management-v1` repository at
`7ebad9c90c7d511c0cca82395ef4210b0deea750` on 2026-08-05. Production is not a
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

### Daily engineering dashboard

This is the Phase 2 single-page executive view as of 2026-08-05.

| Executive signal | Current record |
| --- | --- |
| Completed today | `MMQ.1` — Master Milestone Queue Foundation; `MMQ.2` — Phase 2 Program Control Foundation; `MMQ.3` — Automated Workstream Coordination |
| Currently running | `EST.2` on Office Machine 1; `INV.1` on “Machine 2”; `CUTOVER.1` in the Migration Repository; Business Economics `Phase 7` in the Business Economics Repository |
| Waiting for review | `MMQ.4` — Phase 2 Enterprise Implementation Roadmap (documentation validation complete; owner review required) |
| Blocked | No milestone is currently recorded as `BLOCKED`; unresolved assignments and future sequencing remain owner decisions |
| Next expected approvals | Review `MMQ.4`; assign and Start `PE-TELEMETRY-1`; confirm `EST.2`/`INV.1` integration order and isolated lineage |

### Workstream timeline

Rows are chronological within each workstream. A date is shown only when commit
evidence supplies one; otherwise the sequence reflects the supplied milestone
history and the date remains unrecorded. Provisional future slots are tracked in
[Future queue](#future-queue), not as historical events.

| Workstream | Sequence | Date | Milestone | Recorded event |
| --- | ---: | --- | --- | --- |
| Enterprise | 1 | 2026-08-04 | Dispatch Assignment V1 | `COMPLETE` in commits `2749512` and `60c95f2` |
| Enterprise | 2 | 2026-08-04 | `PRICEBOOK.1` | `COMPLETE` in commit `e97dc40` |
| Enterprise | 3 | 2026-08-05 | `EST.1` | `COMPLETE` in commit `e0f68972f65bfec7272dd133060b348375497b3e` |
| Enterprise | 4 | Not recorded | `EST.2` | `IN PROGRESS` on Office Machine 1 |
| Enterprise | 4 (parallel) | Not recorded | `INV.1` | `IN PROGRESS` on “Machine 2”; relative integration order with `EST.2` is undecided |
| Migration | 1 | Not recorded | `LOCATION.2` | `COMPLETE`; exact evidence not recorded |
| Migration | 2 | Not recorded | `SOURCE.5` | `COMPLETE`; exact evidence not recorded |
| Migration | 3 | Not recorded | `CUTOVER.1` | `IN PROGRESS` |
| Economics | 1 | Not recorded | Phase 5 | `COMPLETE`; exact evidence not recorded |
| Economics | 2 | Not recorded | Phase 6 | `COMPLETE`; exact evidence not recorded |
| Economics | 3 | Not recorded | Phase 7 | `IN PROGRESS` |
| Architecture | 1 | Not recorded | Inventory & Purchasing Architecture V1 | `COMPLETE`; exact evidence not recorded |
| Platform | 1 | Not recorded | Phone-first workflow | `COMPLETE`; exact evidence not recorded |
| Platform | 2 | 2026-08-04 | `MC.1` | `COMPLETE`; shared baseline includes evidence commit `6ac4934` |
| Platform | 3 | 2026-08-05 | `MMQ.1` | `COMPLETE`; recorded by commit `4bca97293dbc6ea5f8482239dc44ecd7c634ae22` |
| Platform | 4 | 2026-08-05 | `MMQ.2` | `COMPLETE`; recorded by commit `4bca97293dbc6ea5f8482239dc44ecd7c634ae22` |
| Platform | 5 | 2026-08-05 | `MMQ.3` | `COMPLETE`; recorded by commit `547f40cd833005b11d8952269b5bc3eef1a1bfe8` |
| Platform | 6 | 2026-08-05 | `MMQ.4` | `WAITING FOR OWNER REVIEW`; roadmap documentation and validation are the current evidence |
| Platform | 7 | Not started | `PE-TELEMETRY-1` | `READY`; assignment and explicit Start are pending |

### Dependency graph

“Not recorded” is intentional: it prevents sequence from being mistaken for an
approved dependency. A planned relationship remains non-authorizing until the
owner approves its complete execution contract.

| Milestone | Prerequisite milestones | Downstream milestones | Blocking relationship |
| --- | --- | --- | --- |
| Dispatch Assignment V1 | Not recorded | Not recorded | None recorded; milestone is complete |
| `PRICEBOOK.1` | Not recorded | Not recorded | None recorded; milestone is complete |
| `EST.1` | Not recorded | `EST.2`; `EST.1` Preview deployment | Satisfied for both downstream milestones; milestone is complete |
| `EST.2` | `EST.1` | `EST.3` (planned) | Blocks its own review handoff; integration order with `INV.1` is unresolved |
| `INV.1` | Not recorded | `INV.2` (planned) | Missing prerequisite record and unresolved order with `EST.2` block integration |
| `LOCATION.2` | Not recorded | Not recorded | None recorded; milestone is complete |
| `SOURCE.5` | Not recorded | `CUTOVER.1` | Supplied prerequisite is satisfied; exact remaining cutover dependencies are unknown |
| `CUTOVER.1` | `SOURCE.5` and prior migration readiness; exact set not recorded | `MIG.1` (planned) | Missing exact dependency and lineage records block integration |
| Phase 5 | Not recorded | Phase 6 | Satisfied for Phase 6; milestone is complete |
| Phase 6 | Phase 5 | Phase 7 | Satisfied for Phase 7; milestone is complete |
| Phase 7 | Phase 6 | `BE.8` (planned) | Missing evidence, assignment, and lineage records block integration |
| Inventory & Purchasing Architecture V1 | Not recorded | `INV.1` (related implementation) | Architecture is complete; no implementation prerequisite is asserted because none was supplied |
| Phone-first workflow | Not recorded | `PE-TELEMETRY-1` | Satisfied for `PE-TELEMETRY-1` |
| `MC.1` | Not recorded | `PE-TELEMETRY-1` | Satisfied for `PE-TELEMETRY-1` |
| `MMQ.1` | Not recorded | `MMQ.2`; `MMQ.3` | None; milestone is complete |
| `MMQ.2` | `MMQ.1` | `MMQ.3` | None; milestone is complete |
| `MMQ.3` | `MMQ.1`; `MMQ.2` | `MMQ.4` | None; milestone is complete |
| `MMQ.4` | `MMQ.1`; `MMQ.2`; `MMQ.3` | Version 1.0 roadmap catalog; `PE-TELEMETRY-1` remains separately queued | Owner review blocks commit readiness; roadmap entries remain non-authorizing |
| `PE-TELEMETRY-1` | Phone-first workflow; `MC.1` | Not recorded | Machine assignment and explicit Start block execution |
| `EST.1` Preview deployment | `EST.1` | Not recorded | None recorded; milestone is complete |
| Laptop 1 integration/release capability | Not recorded | Future approved integration milestone | No milestone is currently assigned |

### Pipeline dashboard

“Next three milestones” lists the three positions after the current milestone.
Provisional positions remain non-authorizing.

| Pipeline | Current milestone | Next milestone | Next three milestones | Assigned machine | Current status | Blocking dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| Enterprise | `EST.2` and parallel isolated `INV.1` | `CRM.2` planning approval | `CRM.2`; `OPS.1`; then dependency-ready `EST.3` / `INV.2` | Office Machine 1 (`EST.2`); “Machine 2” (`INV.1`) | `IN PROGRESS` | Integration order, exact branches/commits, and isolated Alembic parents are unconfirmed |
| Migration | `CUTOVER.1` | `MIG.1` planning approval | `MIG.1`; `MIG.2`; `MIG.3` | Migration Repository; execution machine not recorded | `IN PROGRESS` | Exact dependency set, branch, commit, machine, and active migration parent are unconfirmed |
| Business Economics | `Phase 7` | `BE.8` planning approval | `BE.8`; `BE.9`; then accepted reporting integration | Business Economics Repository; execution machine not recorded | `IN PROGRESS` | Phase 7 scope evidence, branch, commit, assignment, and migration base are unconfirmed |
| Architecture | `MMQ.4` roadmap review | First domain brief required by an approved Phase 1 milestone | Architecture risks, financial contracts, and provider decisions | `ACP-Enterprise`; physical machine not recorded | `WAITING FOR OWNER REVIEW` | Roadmap approval does not approve any implementation milestone or unresolved architecture decision |
| Platform | `MMQ.4` | `PE-TELEMETRY-1` | `PE-TELEMETRY-1`; roadmap Phase 1; roadmap Phase 2 | Repository `ACP-Enterprise`; physical machine not recorded | `WAITING FOR OWNER REVIEW` | Owner review blocks commit readiness; roadmap entries require separate approval before execution |
| AI / Advisory | `BEA.6` planning approval | `BEA.7` | `BEA.7`; deferred `BEA.8`; deferred `LUM.1` | Unassigned | `PLANNED` | Beacon remains advisory; Luminary lacks an approved architecture and is deferred |
| Integration / Release | `IC.1` planning approval after Phase 1 acceptance | `IC.2` | `IC.2`; `IC.3`; `IC.4` | Laptop 1 capability; no milestone assigned | `PLANNED` | No integration target is approved; active workstream commits and Alembic order are unknown |

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

### Capacity forecast

No completion dates were supplied. “Unknown” is therefore used instead of an
invented estimate.

| Machine | Repository | Current milestone | Estimated completion | Next queued milestone |
| --- | --- | --- | --- | --- |
| Current ACP Enterprise execution capacity (physical machine not recorded) | `ACP-Enterprise`, `customer-management-v1` | `MMQ.4` | Roadmap implementation complete; validation and owner review pending | `PE-TELEMETRY-1` (`READY`, assignment and Start pending) |
| Office Machine 1 | Not recorded | `EST.2` | Unknown | No approved successor; `OPS.1` / `EST.3` are planned candidates after prerequisites |
| Office Machine 2 | Not recorded | Unassigned | Not applicable | None approved; `INV.1` relationship requires owner confirmation |
| Laptop 1 | Integration repository not recorded | No active milestone | Not applicable | `IC.1` is planned and not approved |
| Migration Repository | Location not recorded | `CUTOVER.1` | Unknown | `MIG.1` (planned, not approved) |
| Business Economics Repository | Location not recorded | `Phase 7` | Unknown | `BE.8` (planned, not approved) |

### Repository health

This is a read-only snapshot taken before the uncommitted `MMQ.4` documentation
change. “Synchronization” compares the recorded local branch with its configured
upstream; it does not imply that other isolated workstream repositories are
synchronized.

| Signal | Current record |
| --- | --- |
| Branch | `customer-management-v1` |
| HEAD | `7ebad9c90c7d511c0cca82395ef4210b0deea750` |
| Working tree | Clean at the milestone baseline; this `MMQ.4` documentation change is intentionally unstaged and uncommitted |
| Synchronization | `origin/customer-management-v1`; 0 commits ahead and 0 behind at the reconciled baseline; no push is authorized by `MMQ.4` |
| Alembic lineage | One repository head, `t5j7f9b1c386`, extending Inventory adjustments/cycle counts through Estimate job conversion; repository presence does not change active milestone acceptance status |
| Deployment state | `EST.1` Preview is recorded `COMPLETE`; no current preview candidate and no Production authorization or deployment are recorded |

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
| Platform | `GREEN` | MMQ.1 through MMQ.3 are `COMPLETE`; MMQ.4 awaits owner review; the telemetry milestone remains `READY` |

### Integration readiness

An item appears in the earliest gate it has reached. Empty gates are explicit so
absence is not confused with missing tracking. Movement between gates requires
the approval and evidence described in [Governance rules](#governance-rules).

| Gate | Milestones | Required evidence or current reason |
| --- | --- | --- |
| Ready to Review | `MMQ.4` | Roadmap documentation and local validation are complete; owner acceptance is required |
| Ready to Commit | None | `MMQ.4` must pass validation and owner review before commit approval |
| Ready to Push | None | Commit `547f40c` containing `MMQ.3` is local and unpushed; no push approval is recorded |
| Ready to Preview | None | No pushed integration candidate is recorded |
| Ready to Merge | None | No reviewed source branch or immutable integration candidate is recorded |
| Ready for Production | None | No accepted release candidate, rollback record, or explicit Production approval is recorded |

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

1. **Before implementation:** every milestone must enter the active register or
   the incorporated roadmap. Implementation may start only after the owner
   approves the complete milestone definition, assigns its execution boundary,
   and changes its state to `READY`, followed by explicit Start and
   `IN PROGRESS`.
2. **When approved:** record the approval boundary, dependencies, assignment,
   acceptance evidence, and migration ownership, then change the queue state in
   the same reviewed documentation change.
3. **After commit:** record the immutable commit and branch in the milestone and
   release/integration ledgers. A commit does not authorize a push; update
   [Integration readiness](#integration-readiness) only after the separate
   review decision.
4. **After deployment:** record the environment, preview/release identifier,
   deployed commit, validation result, rollback reference, and state change.
   Preview deployment does not authorize Production.
5. **After owner acceptance:** record the acceptance evidence and date, update
   the milestone to `COMPLETE`, and update the completed and release ledgers in
   the same change.
6. Every transition into `WAITING FOR OWNER REVIEW`, `DEPLOYING / VALIDATING`,
   `COMPLETE`, or `BLOCKED` must include the evidence, responsible boundary, and
   next action. Missing evidence prevents advancement.
7. The Timeline, Dependency, Pipeline, Machine, Capacity, Repository Health,
   Integration Readiness, Release, Architecture, Workstream Health, Daily
   Engineering Dashboard, Future Queue, active, completed, commit, and Alembic
   views must agree. A discrepancy stops new milestone pulls until the owner
   reconciles this file.

## Immediate queue

Position 1 is current or next. Roadmap entries in later positions are planning
definitions and remain non-authorizing until separately approved.

| Workstream | 1 | 2 | 3 |
| --- | --- | --- | --- |
| Enterprise Product | `EST.2` — `IN PROGRESS` | `INV.1` — `IN PROGRESS` in parallel on its isolated assignment | `CRM.2` — `PLANNED` roadmap entry |
| Customer Migration | `CUTOVER.1` — `IN PROGRESS` | `MIG.1` — `PLANNED` roadmap entry | `MIG.2` — `PLANNED` roadmap entry |
| Business Economics | `Phase 7` — `IN PROGRESS` | `BE.8` — `PLANNED` roadmap entry | `BE.9` — `PLANNED` roadmap entry |
| Architecture | `MMQ.4` — `WAITING FOR OWNER REVIEW` | First approved Phase 1 domain brief | Financial/provider risk decisions |
| Platform / Engineering | `MMQ.4` — `WAITING FOR OWNER REVIEW` | `PE-TELEMETRY-1` — `READY` | Version 1.0 Phase 1 roadmap — `PLANNED` |
| AI / Advisory | `BEA.6` — `PLANNED` roadmap entry | `BEA.7` — `PLANNED` roadmap entry | `LUM.1` — `PLANNED` but deferred post-1.0 |
| Integration / Release | `IC.1` — `PLANNED` roadmap entry | `IC.2` — `PLANNED` roadmap entry | `IC.3` — `PLANNED` roadmap entry |

## Future queue

Active work is excluded from this view. An entry appears in exactly one category
so planning visibility cannot be mistaken for execution authority.

| Category | Milestones | Meaning |
| --- | --- | --- |
| Approved | `PE-TELEMETRY-1` | Defined as `READY`; machine assignment and explicit Start are still required |
| Planned | 48 Version 1.0 entries in the [implementation roadmap](version-1-implementation-roadmap.md#version-10-milestone-catalog) | Defined planning architecture only; each entry requires separate milestone approval and Start |
| Backlog | Five unsequenced candidates in the [roadmap backlog](version-1-implementation-roadmap.md#backlog) | Memberships, route optimization, financing/coaching, warranty/equipment depth, and campaign attribution remain unapproved candidates |
| Deferred | 12 coded milestones in the [deferred roadmap](version-1-implementation-roadmap.md#deferred) | Full accounting, post-launch depth, autonomous Beacon, Luminary, operational LIA, and SaaS administration remain outside Version 1.0 |

## Active and ready milestone register

| Code | Milestone title | Workstream | Status | Assigned machine or repository | Dependency | Completion evidence or current authoritative commit | Next approved milestone | Scope boundary | Migration / Alembic notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `EST.2` | Estimate continuation | Enterprise Product | `IN PROGRESS` | Office Machine 1; repository/branch not recorded | `EST.1` | Current workstream commit unknown; shared authoritative repository baseline is `7ebad9c90c7d511c0cca82395ef4210b0deea750` | No successor is approved; `EST.3` is planned after `CRM.2` | Continue only the owner-approved estimate milestone; do not absorb invoice, migration, release, or production work | Any schema work must remain isolated until its base revision and integration order are recorded; do not independently extend shared Alembic head |
| `INV.1` | Inventory foundation | Enterprise Product | `IN PROGRESS` | Machine 2; repository/branch not recorded | Dependency not recorded | Current workstream commit unknown; shared authoritative repository baseline is `7ebad9c90c7d511c0cca82395ef4210b0deea750` | No successor is approved; `INV.2` is planned after `OPS.1` | Implement only the owner-approved inventory milestone; do not absorb estimate, migration, release, or production work | Treat inventory migration work as isolated from `EST.2`; integration must serialize both branches onto the then-authoritative Alembic head |
| `CUTOVER.1` | Customer cutover | Customer Migration | `IN PROGRESS` | Machine and repository/branch not recorded | `SOURCE.5` and prior migration readiness; exact dependency set not recorded | Current workstream commit unknown | No successor is approved; `MIG.1` is planned | Customer migration cutover preparation/execution within the approved non-production boundary; no Production mutation is authorized | Customer Migration owns its isolated migration chain until reconciliation; no Production Alembic execution is authorized |
| `Phase 7` | Business Economics Phase 7 | Business Economics | `IN PROGRESS` | Machine and repository/branch not recorded | `Phase 6` | Current workstream commit unknown | No successor is approved; `BE.8` is planned | Only the approved Phase 7 economics outcome; no production accounting entries, production ledger authority, or unrelated product work | Any schema revision must be isolated from Enterprise Product and Customer Migration and rebased/reparented only during approved integration |
| `MMQ.4` | Phase 2 Enterprise Implementation Roadmap | Platform / Engineering | `WAITING FOR OWNER REVIEW` | Repository `ACP-Enterprise`, branch `customer-management-v1`; physical machine not recorded | `MMQ.1`; `MMQ.2`; `MMQ.3` | Reconciled uncommitted documentation diff based on `7ebad9c90c7d511c0cca82395ef4210b0deea750`; Markdown, cross-reference, duplicate, dependency, queue, and `git diff --check` validation passed after reconciliation | `PE-TELEMETRY-1` remains the next separately approved milestone | Documentation, planning, and architecture through Version 1.0 only; roadmap entries grant no execution or privileged-action authority | Documentation-only; Alembic lineage records the new repository head without changing migration files |
| `PE-TELEMETRY-1` | Live owner-started progress telemetry evidence | Platform / Engineering | `READY` | Repository `ACP-Enterprise`; machine not assigned | Phone-first workflow and `MC.1` | Ready-state evidence supplied by owner; current authoritative commit `7ebad9c90c7d511c0cca82395ef4210b0deea750` | No automatic successor; roadmap work requires separate approval | Collect and record live evidence for owner-started progress telemetry; no unrelated runtime expansion, deployment, or Production mutation | No migration is expected from evidence collection; any discovered schema need requires a separately approved milestone |

## Version 1.0 roadmap control

The complete [Version 1.0 Enterprise Implementation Roadmap](version-1-implementation-roadmap.md)
is incorporated into this queue as the authoritative Phase 2 planning catalog.
It defines 48 Version 1.0 milestones and 12 coded deferred milestones. All are
`PLANNED` and non-authorizing unless separately promoted in the active register.

| Control view | Queue record |
| --- | --- |
| Phase grouping | Phase 1 foundation contracts -> `IC.1`; Phase 2 revenue/experience -> `IC.2`; Phase 3 intelligence/migration proof -> `IC.3`; Phase 4 preview/release readiness -> `IC.4` and `IC.5` |
| Dependency ordering | Current active handoffs -> Phase 1 -> `IC.1` -> Phase 2 -> `IC.2` -> Phase 3 -> `IC.3` -> `IC.4` -> `MIG.4` -> `REL.1` -> `REL.2` -> `IC.5` -> separately approved `REL.3` |
| Parallel grouping | Independent domain slices may share a wave only with isolated files/resources and satisfied prerequisites; each checkpoint and all shared migrations are serialized |
| Integration checkpoints | `IC.1` foundation; `IC.2` booked-to-cash; `IC.3` release candidate; `IC.4` production-like preview; `IC.5` go/no-go |
| Future backlog | Five unsequenced candidates remain without execution codes or approval |
| Deferred milestones | 12 coded post-Version 1.0 milestones cover accounting depth, post-launch product depth, Beacon autonomy, Luminary, operational LIA, and SaaS |

The roadmap's milestone catalog supplies purpose, scope, prerequisites, outputs,
integration points, implementation and validation complexity, expected
repository, and suggested capacity. Its dependency graph, parallel plan,
serialized boundaries, risks, forecast, backlog, and deferred register are part
of this queue by reference. Status changes still occur only in this file.

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
| Shared `ACP-Enterprise` repository, branch `customer-management-v1` | `7ebad9c90c7d511c0cca82395ef4210b0deea750` | Reconciled queue baseline; `MMQ.3` evidence remains preserved at `547f40c` on the safety branch |
| Dispatch Assignment V1 | `2749512` with permission follow-up `60c95f2` | Repository evidence for completed dispatch assignment implementation |
| PRICEBOOK.1 | `e97dc40` | Repository evidence for completed price book foundation |
| EST.1 | `e0f68972f65bfec7272dd133060b348375497b3e` | Repository evidence for completed estimate foundation |
| `EST.2`, `INV.1`, `CUTOVER.1`, Business Economics `Phase 7` | Unknown | Active isolated-workstream commits were not supplied and are not asserted |

## Alembic lineage by isolated workstream

This table records known repository lineage and the required integration base; it
does not authorize migration edits or execution. Static revision/parent
inspection finds one linear repository head at `t5j7f9b1c386`.

| Isolated workstream | Known lineage or base | Current isolation rule | Integration requirement |
| --- | --- | --- | --- |
| Shared Enterprise Product | `p1f3a5c7d942` (Dispatch) -> `q2g4b6d8e053` (Price Book) -> `r3h5c7d9f164` (Estimate) -> `s4i6d8e0a275` (Estimate approval workflow) -> `s4i6d8f0h275` (Inventory foundation) -> `t5j7e9g1i386` (Inventory adjustments/cycle counts) -> `t5j7f9b1c386` (Estimate job conversion) | `t5j7f9b1c386` is the repository head at this reconciled baseline; presence in lineage does not change milestone acceptance status | Any new revision must be based on the latest owner-accepted integrated head, not merely a present or stale local head |
| `EST.2` | Repository contains `s4i6d8e0a275`; active workstream revision/acceptance boundary is not recorded | Must not assume repository presence equals owner-accepted integration | Record the exact milestone revision boundary before review and reconcile it with `INV.1` |
| `INV.1` | Repository contains `s4i6d8f0h275`; active workstream revision/acceptance boundary is not recorded | Must not assume repository presence equals owner-accepted integration | Record the exact milestone revision boundary and owner-approved order, then rerun migration validation |
| Customer Migration / `CUTOVER.1` | Known historical chain includes `e8b4c6d2a917` -> `f1c7d9e3b825` and `a2d8e4f6c930` -> `b3e9f5a7d041` -> `c4f0a6b8e152` -> `d5a1b7c9f263`; active local revision unknown | Migration-owned staging and cutover work remains isolated from product work | Reconcile against the latest shared head through reviewed integration; never execute against Production from a workstream machine |
| Business Economics / `Phase 7` | Active base and revision unknown | Maintain a dedicated isolated chain; do not attach a child concurrently to a shared base already claimed by another workstream | Owner-approved integration records the final parent and validates a single head |
| Platform / Engineering | Shared history through `o0e2f4a6c931`; no migration expected for `PE-TELEMETRY-1` | Evidence collection must not mutate lineage | A schema requirement becomes a separately approved milestone |
| AI / Advisory | No active roadmap lineage recorded | No revision may be created from a planning entry | Establish ownership and base before any separately approved schema work |
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

Capacity availability, a completed capability, or a planned roadmap position
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
| `MMQ.1` | Master Milestone Queue Foundation | Platform / Engineering | `COMPLETE` | Owner-approved completion recorded in commit `4bca97293dbc6ea5f8482239dc44ecd7c634ae22` |
| `MMQ.2` | Phase 2 Program Control Foundation | Platform / Engineering | `COMPLETE` | Owner-approved completion recorded in commit `4bca97293dbc6ea5f8482239dc44ecd7c634ae22` |
| `MMQ.3` | Automated Workstream Coordination | Platform / Engineering | `COMPLETE` | Owner-approved completion recorded in commit `547f40cd833005b11d8952269b5bc3eef1a1bfe8` |

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
- Select and separately approve the first dependency-ready Version 1.0 roadmap
  milestone; roadmap planning does not grant execution authority.
- Approve or revise the Beacon Version 1.0 advisory boundary and define
  Luminary architecture before any deferred Luminary implementation.
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
