# Master Milestone Queue

## Authority and operating boundary

This is the operational status and sequencing authority for ACP Enterprise. Its
MMQ.5 baseline is branch `customer-management-v1` at
`4dd2884a25bd1e86a11792a95239f58b88c6abe8` on 2026-08-07. The
[Continuous Production Scheduler](continuous-production-scheduler.md) supplies
execution metadata and capacity depth; the
[Version 1 roadmap](version-1-implementation-roadmap.md) supplies approved
planning scope. This file controls status when the views differ.

Nothing in these documents authorizes Start, staging, commit, push, merge,
Preview, migration/import execution, cutover, deployment, or Production. Owner
approval remains milestone-specific and privileged actions remain separately
approved. Production is untouched.

## Scheduler lifecycle

The only milestone states are:

- `PLANNED`
- `READY`
- `IN PROGRESS`
- `WAITING FOR OWNER REVIEW`
- `DEPLOYING / VALIDATING`
- `COMPLETE`
- `BLOCKED`

`PLANNED` never grants work. `READY` means the complete execution definition is
approved and unblocked, but still requires explicit owner Start. The exact
promotion evidence, implementation types, repository-resolution rules, and
handoff gates are defined in
[Lifecycle and READY promotion](continuous-production-scheduler.md#lifecycle-and-ready-promotion).
Any `UNKNOWN` required execution field prevents `READY`.

## Permanent capacities

| ID | Identity | Current assignment | State | Current blocking fact |
| --- | --- | --- | --- | --- |
| `OM1` | Office Machine 1 Enterprise | None active; `PLAT.1` next | `READY` capacity | Explicit owner Start required |
| `OM2` | Office Machine 2 Enterprise | None active; `PHONE-BUG.1` next | `READY` capacity | Historical “Machine 2” Inventory work establishes this permanent identity; explicit owner Start required |
| `MIG` | Customer Migration | `CUTOVER.1` candidate handoff | `WAITING FOR OWNER REVIEW` | Candidate is isolated and unaccepted; `MIG.1` also awaits `CRM.2`/`OPS.1` |
| `ECO` | Business Economics | External Phase 8 review; roadmap `BE.8` next | `READY` next assignment | The two Phase 8 labels are distinct; explicit owner Start required for `BE.8` |
| `LAP` | Laptop 1 Integration / Release / PMO | `MMQ.5` | `WAITING FOR OWNER REVIEW` | Owner review required; no integration target is READY |

Capacity identity persists when assignments change. A free capacity cannot pull a
`PLANNED` item. See the complete
[continuous capacity schedule](continuous-production-scheduler.md#continuous-capacity-schedule).

## Daily engineering dashboard

| Signal | Current record |
| --- | --- |
| Completed in current authoritative history | `PRICEBOOK.1`; `EST.1`; `EST.2`; `INV.1`; `INV.2`; `EST.3`; `MC.1`; `MMQ.1` through `MMQ.4` |
| Currently implementing | None confirmed by accessible authoritative evidence |
| Waiting for owner review | `CUTOVER.1` isolated candidate; Economics external Phase 8 candidate; `MMQ.5` |
| Blocked | `MIG.1` awaits accepted `CUTOVER.1`, `CRM.2`, and `OPS.1`; other planned work remains dependency- or metadata-blocked |
| Urgent defects | `PHONE-BUG.1` — Mobile error-boundary / nullable source crash (`READY` for fresh implementation; candidate is evidence only; physical iPhone acceptance remains required) |
| Next expected approvals | Review `MMQ.5`; issue Start for `PLAT.1`, `PHONE-BUG.1`, or `BE.8`; review `CUTOVER.1`; start `PE-TELEMETRY-1` live validation when the owner-selected environment is available |
| Next integration checkpoint | `IC.1`, still `PLANNED`; Phase 1 inputs are not all accepted/READY |

## Continuous production schedule

Future positions are scheduling visibility, not execution approval.

| Capacity | CURRENT | NEXT | NEXT +1 | NEXT +2 | NEXT +3 |
| --- | --- | --- | --- | --- | --- |
| `OM1` | None active | `PLAT.1` — `READY` | `COMMS.1` — `PLANNED` | `OPS.1` — `PLANNED` | `PUR.1` — `PLANNED` |
| `OM2` | None active; permanent identity reconciled | `PHONE-BUG.1` — `READY` urgent | `CRM.2` — `PLANNED` | `DISP.2` — `PLANNED` | `TECH.1` — `PLANNED` |
| `MIG` | `CUTOVER.1` — `WAITING FOR OWNER REVIEW` | `MIG.1` — `PLANNED` | `MIG.2` — `PLANNED` | `MIG.3` — `PLANNED` | `MIG.4` — `PLANNED` |
| `ECO` | External Phase 8 — `WAITING FOR OWNER REVIEW` | `BE.8` — `READY` | `BE.9` — `PLANNED` | `ACC.1` finance review — `PLANNED` | `ACC.2` finance review — `PLANNED` |
| `LAP` | `MMQ.5` — `WAITING FOR OWNER REVIEW` | `PE-TELEMETRY-1` — owner-controlled validation, `READY` | `IC.1` — `PLANNED` | `IC.2` — `PLANNED` | `IC.3` — `PLANNED` |

`OM1`, `OM2`, and `ECO` each have one `READY` assignment; `LAP` has a `READY`
owner-controlled validation task. None may start without its explicit owner
Start. The scheduler retains four visible future positions.

## Integration readiness

| Gate | Milestones | Evidence / reason |
| --- | --- | --- |
| Ready to Review | `MMQ.5` | Documentation and scheduler validation complete; owner acceptance required |
| Ready to Commit | None | `MMQ.5` requires owner approval |
| Ready to Push | None | No newly approved commit exists |
| Ready to Preview | None | `IC.4` and `REL.1` remain dependency-blocked planning entries |
| Ready to Merge | None | `CUTOVER.1`, Economics Phase 8, and `PHONE-BUG.1` candidates lack accepted integration contracts |
| Ready for Production | None | `IC.5`, immutable release/cutover evidence, and explicit Production approval do not exist |

## Defect queue

| Code | Title | Priority | State | Capacity | Dependency | Current evidence | Required next decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `PHONE-BUG.1` | Mobile error-boundary / nullable source crash | Urgent | `READY` | `OM2` | Existing platform/customer paths; explicit Start | Candidate `215506fa63201b88f55b6fbd09459558e5eae5a6` changed 11 frontend files and covers nullable normalization plus route failure, but is highly divergent from Enterprise and lacks physical-iPhone acceptance | Reimplement from fetched authoritative Enterprise in `work/phone-bug-1`; review/Git gates; separately approve Preview and physical-iPhone validation |

The full scope and integration classification are in the
[Defect register](continuous-production-scheduler.md#defect-register). MMQ.5 does
not implement or approve integration of this fix.

## Evidence-reconciled milestone ledger

Only evidence-supported states are recorded. “Isolated” means accessible Git
evidence exists but is not an ancestor of the authoritative Enterprise branch.

| Code / milestone | Title | Workstream | State | Exact evidence | Evidence boundary |
| --- | --- | --- | --- | --- | --- |
| Dispatch Assignment V1 | Dispatch Assignment V1 | Enterprise | `COMPLETE` | `2749512` and `60c95f2` | Authoritative ancestors |
| `PRICEBOOK.1` | Price Book foundation | Enterprise | `COMPLETE` | `e97dc408742e0037330b79156cd0a5ba583c6649` | Authoritative ancestor |
| `EST.1` | Estimate foundation | Enterprise | `COMPLETE` | `e0f68972f65bfec7272dd133060b348375497b3e` | Authoritative ancestor |
| `EST.2` | Estimate revision and customer approval workflow | Enterprise | `COMPLETE` | `f52b184634acb89e21816533148cb3110fdce31e` | Authoritative ancestor; migration `s4i6d8e0a275` |
| `INV.1` | Inventory foundation | Enterprise | `COMPLETE` | `2389af0415161fd685c3c73b8751df2ad440f701` | Authoritative ancestor; migration `s4i6d8f0h275` |
| `INV.2` | Inventory adjustments and cycle counts | Enterprise | `COMPLETE` | `303548a7ecba9bc8b5a788237cc3a81a233c0d48` | Authoritative ancestor; migration `t5j7e9g1i386` |
| `EST.3` | Estimate-to-job conversion | Enterprise | `COMPLETE` | `7ebad9c90c7d511c0cca82395ef4210b0deea750` | Authoritative ancestor; migration `t5j7f9b1c386` |
| `LOCATION.2` | Native service-location reconciliation | Migration | `COMPLETE` | `8268737b0a1d8feee4a30e76eb245040a8e15623` — `feat(migration): add native service location reconciliation` | Linear ancestor of `SOURCE.5`; owner-supplied acceptance corroborates mapping |
| `SOURCE.5` | Native customer identity consolidation | Migration | `COMPLETE` | `915f9383ce4daeec2974cf92d23abdc1bc2a1009` — `feat(migration): add native customer identity consolidation` | Direct child of `LOCATION.2` and parent of `CUTOVER.1`; owner-supplied acceptance corroborates mapping |
| `CUTOVER.1` | Cutover readiness foundation | Migration | `WAITING FOR OWNER REVIEW` | `f4e54775090b7c21afda079912a3729583662313` — `feat(migration): add cutover readiness foundation` | Isolated branch tip; direct child of `SOURCE.5`; head `d9f5b1c7e240`; no acceptance asserted |
| `CUTOVER.2` | No milestone found | Migration | verification required | No matching code, subject, or documentation on `origin/customer-migration-workstream` | Not treated as complete or dependency evidence |
| Economics Phase 5 | Profitability intelligence contracts | Economics | `COMPLETE` | isolated evidence through `7d7aa63542c24f76283f4977e768244c3eb63e83` | Owner-supplied completion plus implementation/tests on accessible ref |
| Economics Phase 6 | Deterministic profitability computation | Economics | `COMPLETE` | isolated evidence `521ed293c8967c57b6fc9af267998d9d097b69f7` | Implementation/tests on accessible ref |
| Economics Phase 7 | Operational fact acquisition | Economics | `COMPLETE` | isolated evidence `af06a7fa83364bc877edab81d18dae96e12de7d2` | Implementation/tests on accessible ref |
| Economics external Phase 8 | Allocation and profitability engines | Economics | `WAITING FOR OWNER REVIEW` | `origin/business-economics-foundation` at `49261468f443273ffefcf78d200048dccf097e0f` | Isolated candidate; not equated with roadmap `BE.8` |
| `BE.8` | Define Version 1.0 economics contract | Economics | `READY` | Phase 7 at `af06a7fa83364bc877edab81d18dae96e12de7d2`; scheduler execution contract | Distinct contract milestone; explicit owner Start required |
| `PHONE-BUG.1` | Mobile error-boundary / nullable source crash | Enterprise defect | `READY` | candidate `215506fa63201b88f55b6fbd09459558e5eae5a6` analyzed; scheduler execution contract | Reimplement; do not integrate candidate; Preview/iPhone acceptance separately controlled |
| `PLAT.1` | Close launch platform controls | Enterprise | `READY` | Existing Platform/security foundations; scheduler execution contract | Explicit owner Start required; no migration ownership |
| `PE-TELEMETRY-1` | Live phone execution telemetry validation | Integration | `READY` | `MC.1` plus existing phone execution architecture | `TYPE C` owner-controlled validation, not implementation |
| Inventory & Purchasing Architecture V1 | Inventory/Purchasing boundary | Architecture | `COMPLETE` | `origin/architecture/inventory-purchasing-boundary-v1` at `dd4a620aa93e209fee813f556bebefe9946cb12a` | Approved isolated architecture evidence |
| Phone-first workflow | Phone-first workflow | Platform | `COMPLETE` | Owner-supplied status | Exact completion commit remains unverified |
| `MC.1` | Mission Control lineage/drift prevention | Platform | `COMPLETE` | `6ac4934623f3b573b674b62865aa6a6088d44da6` | Authoritative ancestor |
| `EST.1` Preview | Estimate foundation Preview | Integration | `COMPLETE` | Owner-supplied status | Environment/release identifier remains unverified |
| Laptop 1 capability | Integration/release capability | Integration | `COMPLETE` | Owner-supplied status | Capability evidence remains unverified |
| `MMQ.1` | Master Milestone Queue Foundation | PMO | `COMPLETE` | `4bca97293dbc6ea5f8482239dc44ecd7c634ae22` | Authoritative ancestor |
| `MMQ.2` | Phase 2 Program Control Foundation | PMO | `COMPLETE` | `4bca97293dbc6ea5f8482239dc44ecd7c634ae22` | Authoritative ancestor |
| `MMQ.3` | Automated Workstream Coordination | PMO | `COMPLETE` | local preserved evidence `547f40cd833005b11d8952269b5bc3eef1a1bfe8`; content incorporated by `4dd2884` | Original commit is on safety ref, not authoritative ancestry |
| `MMQ.4` | Version 1 milestone production roadmap | PMO | `COMPLETE` | `4dd2884a25bd1e86a11792a95239f58b88c6abe8` | Current authoritative baseline |
| `MMQ.5` | Continuous Production Scheduler | PMO | `WAITING FOR OWNER REVIEW` | Uncommitted documentation diff from `4dd2884a25bd1e86a11792a95239f58b88c6abe8` | Validation recorded below; no Git action authorized |

## Dependency and parallel ordering

The complete 50-node Version 1 graph remains in the
[roadmap dependency graph](version-1-implementation-roadmap.md#dependency-graph-and-implementation-order).
The scheduler adds these current control edges:

```text
MMQ.1 + MMQ.2 + MMQ.3 + MMQ.4 → MMQ.5

EST.1 → EST.2 → EST.3 → EST.4
INV.1 → INV.2 → INV.2A
SOURCE.5 → CUTOVER.1 → MIG.1 → MIG.2 → MIG.3 → MIG.4
Economics Phase 5 → Phase 6 → Phase 7 → external Phase 8
Economics Phase 7 → roadmap BE.8 → BE.9

Phase 1 accepted set → IC.1 → Phase 2 → IC.2 → Phase 3 → IC.3
→ IC.4 → MIG.4 → REL.1 → REL.2 → IC.5 → REL.3
```

Potential parallel groups and required serialized boundaries are authoritative in
[Parallel and serialized schedule](continuous-production-scheduler.md#parallel-and-serialized-schedule).

## Alembic scheduling

Static revision/parent inspection at the MMQ.5 baseline finds exactly one
Enterprise head: `t5j7f9b1c386`.

```text
s4i6d8e0a275  EST.2
→ s4i6d8f0h275  INV.1
→ t5j7e9g1i386  INV.2
→ t5j7f9b1c386  EST.3 (authoritative head)
```

Parallel isolated implementation is permitted only under approved contracts.
Final migration integration is always serialized: fetch immediately before
integration; compare parent/head; re-parent an unapplied incoming migration when
semantically valid; rerun migration and affected regression validation; prove
one head. Never force-push around a collision or silently create sibling heads.
A merge migration requires explicit architectural justification. See the full
[Alembic integration protocol](continuous-production-scheduler.md#alembic-integration-protocol).

## Automatic handoff

```text
IMPLEMENT
→ VALIDATE
→ WAITING FOR OWNER REVIEW
→ OWNER APPROVAL
→ COMMIT
→ FETCH / INTEGRATION CHECK
→ PUSH
→ DEPLOY / VALIDATE if required
→ COMPLETE
→ START NEXT READY MILESTONE
```

Routine in-scope implementation and validation do not need intermediate owner
approval. Every owner/Git/environment gate remains distinct. Completion never
starts a planned successor. The full contract is in
[Automatic handoff contract](continuous-production-scheduler.md#automatic-handoff-contract).

## Repository health

| Signal | MMQ.5 baseline |
| --- | --- |
| Branch | `customer-management-v1` |
| HEAD | `4dd2884a25bd1e86a11792a95239f58b88c6abe8` |
| Upstream | `origin/customer-management-v1` at the same SHA; 0 ahead / 0 behind before this uncommitted documentation change |
| Working tree | Clean at baseline; only MMQ.5 documentation is intentionally modified/untracked |
| Index | Empty |
| Alembic | One head: `t5j7f9b1c386` |
| Preview | `PHONE-BUG.1` requires a separately approved Preview after implementation; no Preview action is authorized now |
| Production | Untouched; no Production action authorized |

## MMQ.5 validation record

`MMQ.5` remains `WAITING FOR OWNER REVIEW` because the required validation passed
for this uncommitted documentation change.

| Validation | Result |
| --- | --- |
| Markdown | Passed for all three changed documents; long table lines exempted |
| Relative links | Passed; 16 local links and anchors resolved |
| Unique milestone codes | Passed; 50 Version 1 codes correspond one-to-one between roadmap and scheduler; `PHONE-BUG.1` and control codes are unique |
| Metadata completeness | Passed; all 50 scheduler rows contain all 18 fields, using explicit `UNKNOWN` only for non-READY work |
| Dependency closure / cycles | Passed; 50 nodes closed and acyclic against recorded external prerequisites |
| Machine assignments | Passed; five permanent identities and CURRENT through NEXT +3 for each |
| READY evidence | Passed; `PLAT.1`, `PHONE-BUG.1`, `BE.8`, and `PE-TELEMETRY-1` have complete contracts; every other unresolved item fails closed |
| Migration serialization | Passed; migration-bearing/operational rows are TYPE B/C with serialized checkpoints |
| Integration checkpoints | Passed; `IC.1` -> `IC.2` -> `IC.3` -> `IC.4` -> `IC.5` |
| Completed commits | Passed; authoritative commits are ancestors and isolated evidence is reachable from its stated ref |
| Queue consistency | Passed; baseline, states, defect, handoff, Alembic head, and scheduler authority agree |
| `git diff --check` | Passed for tracked files and the new scheduler document |

## Owner-resolution queue

- Review `CUTOVER.1` candidate `f4e5477` and record repository location, local
  branch, validation, integration disposition, and acceptance.
- Determine whether a separate `CUTOVER.2` exists outside the accessible ref;
  none is present on `origin/customer-migration-workstream`.
- Review Economics external Phase 8 candidate `4926146` independently from the
  distinct roadmap contract `BE.8`.
- Issue explicit Start separately for any `READY` item. `PHONE-BUG.1` must be
  freshly implemented and still requires separately approved Preview/iPhone
  evidence; `PE-TELEMETRY-1` is live validation rather than implementation.
- Review newly separated residual milestones `EST.4` and `INV.2A`; completed
  `EST.3` and `INV.2` claims remain bounded to their actual commits.
- Supply exact evidence for owner-supplied completions that remain unverified.

## Change control

Every status or assignment change updates this file and, when metadata changes,
the scheduler document in the same reviewed change. A discrepancy stops new
pulls. Neither capacity availability, queue depth, passed validation, a commit,
nor an isolated candidate grants approval for the next action.
