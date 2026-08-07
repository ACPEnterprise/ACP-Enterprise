# Continuous Production Scheduler

## Authority and safety boundary

This document is the machine-readable planning architecture incorporated by
`MMQ.5` into the [Master Milestone Queue](master-milestone-queue.md). It expands
the [Version 1 roadmap](version-1-implementation-roadmap.md) without granting
implementation, Git, Preview, migration-execution, cutover, or Production
authority. The Master Milestone Queue remains the status authority.

The scheduler may select only a milestone recorded as `READY`. A visible
`PLANNED`, `BLOCKED`, or conditionally sequenced item is not permission to start.
Every owner approval is milestone-specific. Routine implementation,
refactoring, testing, and local validation within an approved scope do not need
intermediate approval, but scope expansion and every privileged transition do.

## Permanent capacity identities

Capacity identity is stable and independent of assignment.

| ID | Permanent identity | Primary boundary |
| --- | --- | --- |
| `OM1` | Office Machine 1 Enterprise | Enterprise domain implementation |
| `OM2` | Office Machine 2 Enterprise | Parallel Enterprise domain implementation |
| `MIG` | Customer Migration | Isolated migration product/data workstream |
| `ECO` | Business Economics | Isolated economics workstream |
| `LAP` | Laptop 1 Integration / Release / PMO | Serialized integration, release evidence, and PMO documentation |

## Lifecycle and READY promotion

The only scheduler states are `PLANNED`, `READY`, `IN PROGRESS`,
`WAITING FOR OWNER REVIEW`, `DEPLOYING / VALIDATING`, `COMPLETE`, and `BLOCKED`.
Commit, push, and merge are handoff gates, not additional milestone states.

| State | Scheduler meaning |
| --- | --- |
| `PLANNED` | Defined intent or dependency slot; implementation is not authorized |
| `READY` | Complete execution contract is approved, assigned, and unblocked; explicit Start is still required |
| `IN PROGRESS` | Owner explicitly started the milestone on its assigned capacity |
| `WAITING FOR OWNER REVIEW` | Implementation and required pre-review validation have immutable evidence |
| `DEPLOYING / VALIDATING` | A separately approved target and immutable artifact are under environment validation |
| `COMPLETE` | Owner accepted the required evidence and the queue records the completion boundary |
| `BLOCKED` | Work cannot safely advance; blocker, last safe state, responsible decision, and next action are recorded |

Promotion from `PLANNED` to `READY` requires all of the following in one reviewed
queue update:

1. Every prerequisite is `COMPLETE`, or an explicitly approved non-blocking
   dependency contract is recorded.
2. Exact repository and capacity are assigned.
3. Branch/worktree strategy is explicit and collision-free.
4. Starting commit is a full immutable SHA, or the resolution rule requires an
   immediate fetch and records the resolved full SHA before workspace creation.
5. Purpose, included files/domains, exclusions, and acceptance evidence define
   the scope boundary.
6. Implementation type, migration impact, shared-contract impact, parallel
   classification, integration checkpoint, and Preview/Production impact are
   known.
7. Validation boundary and automatic stop conditions are executable.
8. The owner explicitly approves this complete definition. `READY` never
   implies Start.

Any `UNKNOWN` in these fields prevents `READY`.

## Implementation classification

| Type | Meaning | Scheduling rule |
| --- | --- | --- |
| `TYPE A` | Domain-local parallel implementation with no shared schema or integration collision | May implement and integrate concurrently when file/resource claims are disjoint |
| `TYPE B` | Migration, shared authorization/contract/event, financial ownership, tenant/security, or cross-domain work | May implement in isolation in parallel; final integration is serialized |
| `TYPE C` | Owner-controlled Preview, Production, migration/import execution, cutover, or irreversible operation | Requires separate operation approval; always serialized |

`TYPE B` dominates `TYPE A` when uncertainty exists. `TYPE C` dominates both.

## Repository and starting-commit rules

| Token | Repository | Starting-commit resolution rule |
| --- | --- | --- |
| `ACP` | `ACP-Enterprise` | Immediately before workspace creation, fetch `origin`; require 0 behind; resolve and record full `origin/customer-management-v1` SHA |
| `MIGR` | `/Users/michaelfouse/Development/ACP-Enterprise` isolated migration ref | Fetch `origin/customer-migration-workstream`; require tip `f4e54775090b7c21afda079912a3729583662313` or stop for reconciliation; create a uniquely named worktree only after Start |
| `ECOR` | `/Users/michaelfouse/Development/ACP-Enterprise` isolated economics ref | Fetch `origin/business-economics-foundation`; require tip `49261468f443273ffefcf78d200048dccf097e0f` or stop for reconciliation; create a uniquely named worktree only after Start |

Unless a row says otherwise, branch/worktree strategy is `UNKNOWN` until `READY`;
the approved strategy must use one unique isolated worktree and branch derived
from the resolved start. Suggested capacity is not assignment approval.

## Version 1 execution metadata

Abbreviations: migration/shared/Preview/Production values are `YES`, `NO`, or
`UNKNOWN`; `COND` means implementation may be isolated in parallel but final
integration is serialized if the recorded impact materializes. Validation text
is the minimum boundary and does not replace the repository standards.

| Code | Title | Workstream | Dependency | Capacity | Repo | Branch/worktree | Start | Type | Mig | Shared | Preview | Prod | Parallel | Checkpoint | Validation | Owner checkpoint | Next |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `CRM.2` | Close launch CRM gaps | CRM | Existing Customer/Location foundations | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | CRM contracts/events | `UNKNOWN` | `NO` | `COND` | `IC.1` | CRM API/UI/events, tenant, deduplication | READY/Start; review; Git gates | `OPS.1` |
| `OPS.1` | Complete launch job lifecycle | Operations | `CRM.2`; existing Scheduling/Jobs | `OM1` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Jobs/Scheduling/events | `UNKNOWN` | `NO` | `COND` | `IC.1` | Lifecycle, authorization, events, end-to-end | READY/Start; review; Git gates | `DISP.2` |
| `DISP.2` | Complete dispatch execution | Dispatch | `OPS.1`; Dispatch Assignment V1 | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Workforce/Operations | `UNKNOWN` | `NO` | `COND` | `IC.1` | Assignment, arrival, exception, role tests | READY/Start; review; Git gates | `TECH.1` |
| `EST.3` | Deliver estimate-to-job conversion | Sales | `EST.2` | historical `OM1` | `ACP` | integrated authoritative history | `f52b184634acb89e21816533148cb3110fdce31e` | `TYPE B` | `YES` | Jobs/events | `NO` recorded | `NO` | Serialized integration complete | `IC.1` | Commit tests for conversion/persistence/events | Completion evidence review | `EST.4` |
| `EST.4` | Complete the launch estimate experience | Sales | `EST.3`; `CRM.2` | `OM1` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | CRM/Estimate/UI contracts | `UNKNOWN` | `NO` | `COND` | `IC.1` | Options, discounts, approvals, responsive journey | READY/Start; review; Git gates | `INVOICE.1` |
| `INV.2` | Deliver inventory adjustments and cycle counts | Inventory | `INV.1` | historical `OM2` | `ACP` | integrated authoritative history | `2389af0415161fd685c3c73b8751df2ad440f701` | `TYPE B` | `YES` | Inventory contracts | `NO` recorded | `NO` | Serialized integration complete | `IC.1` | Commit tests for adjustments/counts/concurrency | Completion evidence review | `INV.2A` |
| `INV.2A` | Complete the launch inventory control core | Inventory | `INV.2`; `OPS.1` | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Inventory/Jobs contracts | `UNKNOWN` | `NO` | `COND` | `IC.1` | Location/on-hand, reservation, transfer workflows | READY/Start; review; Git gates | `PUR.1` |
| `PUR.1` | Establish purchasing foundation | Purchasing | Inventory/Purchasing architecture; `INV.2A` | `OM1` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Inventory/Financial | `UNKNOWN` | `NO` | `COND` | `IC.1` | Domain, authorization, audit events | READY/Start; review; Git gates | `PUR.2` |
| `TECH.1` | Establish technician application shell | Field Service | `OPS.1`; `DISP.2`; Platform identity | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Identity/Jobs/Dispatch | `UNKNOWN` | `NO` | `COND` | `IC.1` | Responsive, accessibility, route/role guards | READY/Start; review; Git gates | `TECH.2` |
| `COMMS.1` | Establish launch communications | Communications | `CRM.2`; notification outbox | `OM1` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Provider/events/consent | `UNKNOWN` | `NO` | `COND` | `IC.1` | Retry, consent, delivery failure, provider boundary | READY/Start; review; Git gates | `COMMS.2` |
| `BE.8` | Define Version 1.0 economics contract | Economics | Business Economics Phase 7 | `ECO` assigned | `ECOR` | isolated worktree `work/be-8-v1-economics-contract` after Start | fetch; require `49261468f443273ffefcf78d200048dccf097e0f` | `TYPE B` | `NO` | Financial/KPI ownership | `NO` | `NO` | Isolated parallel; integration serialized | `IC.1` | KPI catalog, ownership, QuickBooks boundary, tolerances, doc/contract checks | Owner Start; review; Git gates | `BE.9` |
| `MIG.1` | Freeze migration mapping and reconciliation | Migration | `CUTOVER.1`; `CRM.2`; `OPS.1` contracts | `MIG` suggested | `MIGR` | `UNKNOWN` before `READY` | `MIGR` rule | `TYPE B` | `UNKNOWN` | All launch data contracts | `NO` | `NO` | `COND` discovery; freeze serialized | `IC.1` | Mapping, rejects, counts, synthetic dataset | READY/Start; review; Git gates | `MIG.2` |
| `PLAT.1` | Close launch platform controls | Platform | Existing Platform/security foundations | `OM1` assigned | `ACP` | isolated worktree `work/plat-1-launch-controls` after Start | fetch; require 0 behind; record `origin/customer-management-v1` SHA | `TYPE B` | `NO`; stop and replan if schema needed | Authorization/tenant/security | `NO` | `NO` | Isolated parallel; integration serialized | `IC.1` | Role matrix, negative tenant/branch tests, audit access, secrets/support runbooks, repository lint/tests, one Alembic head | Owner Start; security review; Git gates | `IC.1` |
| `IC.1` | Integrate launch foundations | Integration | All Phase 1 milestones | `LAP` suggested | `ACP` | integration workspace `UNKNOWN` | `ACP` rule | `TYPE B` | integrates impacts | all Phase 1 | `NO` | `NO` | Serialized | `IC.1` | One head, aggregate contracts/security/import skeleton | Integration approval; Git gates | `TECH.2` |
| `TECH.2` | Enable field work execution | Field Service | `TECH.1`; `EST.4`; `IC.1` | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Jobs/Estimates/events | `UNKNOWN` | `NO` | `COND` | `IC.2` | Field journey, evidence, role/branch | READY/Start; review; Git gates | `TECH.3` |
| `INV.3` | Capture job materials | Inventory | `INV.2A`; `TECH.2` | `OM1` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Jobs/Technician/Financial | `UNKNOWN` | `NO` | `COND` | `IC.2` | Ledger, concurrency, correction audit | READY/Start; review; Git gates | `INV.4` |
| `PUR.2` | Receive and reconcile purchases | Purchasing | `PUR.1`; `INV.2A`; `IC.1` | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Inventory/Financial | `UNKNOWN` | `NO` | `COND` | `IC.2` | Partial receipt, discrepancy, posting | READY/Start; review; Git gates | `PUR.3` |
| `PUR.3` | Add replenishment controls | Purchasing | `PUR.2`; `INV.3` | `OM1` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Inventory/Economics/Beacon | `UNKNOWN` | `NO` | `COND` | `IC.2` | Threshold, approval, recommendation audit | READY/Start; review; Git gates | `INV.4` |
| `INV.4` | Prove inventory launch readiness | Inventory | `INV.3`; `PUR.3` | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Migration/Reporting | `UNKNOWN` | `NO` | `COND` | `IC.2` | Counts, reconciliation, permissions, performance | READY/Start; review; Git gates | `IC.2` |
| `INVOICE.1` | Establish operational invoicing | Financial | `EST.4`; `OPS.1`; `IC.1` | `OM1` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Financial ownership/events | `UNKNOWN` | `NO` | Serialized integration | `IC.2` | Deterministic totals, tax boundary, tenant | READY/Start; finance review; Git gates | `INVOICE.2` |
| `INVOICE.2` | Deliver invoice workflow | Financial | `INVOICE.1`; `TECH.2`; `COMMS.1` | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Technician/Portal/Payments | `UNKNOWN` | `NO` | `COND` | `IC.2` | End-to-end invoice and communication | READY/Start; finance review; Git gates | `INVOICE.3` |
| `INVOICE.3` | Add controlled corrections | Financial | `INVOICE.2` | `OM1` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Financial balance/audit | `UNKNOWN` | `NO` | Serialized integration | `IC.2` | Void/credit/recompute/audit invariants | READY/Start; finance review; Git gates | `PAY.3` |
| `PAY.1` | Establish payment provider boundary | Financial | `INVOICE.1`; `PLAT.1` | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Security/provider/financial | `UNKNOWN` | `NO` | Serialized integration | `IC.2` | Threat, token, webhook, idempotency failures | READY/Start; security/finance review | `PAY.2` |
| `PAY.2` | Collect and record payments | Financial | `PAY.1`; `INVOICE.2` | `OM1` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Invoice/Portal/Technician | `UNKNOWN` | `NO` | Serialized integration | `IC.2` | Duplicate-charge, retries, receipts, totals | READY/Start; finance review; Git gates | `PAY.3` |
| `PAY.3` | Reconcile refunds and failures | Financial | `PAY.2`; `INVOICE.3` | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Accounting/Reporting/Beacon | `UNKNOWN` | `NO` | Serialized integration | `IC.2` | Refund, late webhook, settlement recovery | READY/Start; finance review; Git gates | `ACC.1` |
| `ACC.1` | Define QuickBooks handoff | Accounting boundary | `INVOICE.3`; `PAY.3`; `BE.8` | `OM1` + `ECO` review | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Financial ownership/QuickBooks | `UNKNOWN` | `NO` | Serialized integration | `IC.2` | Mapping, idempotency, control matrix | READY/Start; finance owner review | `ACC.2` |
| `ACC.2` | Implement accounting reconciliation | Accounting boundary | `ACC.1` | `OM1` + `ECO` review | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | QuickBooks/Reporting/Migration | `UNKNOWN` | `NO` | Serialized integration | `IC.2` | Export, acknowledgement, variance, retry | READY/Start; finance owner review | `RPT.3` |
| `PORTAL.1` | Establish customer portal trust boundary | Customer Portal | `CRM.2`; `PLAT.1`; `IC.1` | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Identity/tenant/CRM | `UNKNOWN` | `NO` | Serialized integration | `IC.2` | Account linking, enumeration, tenant security | READY/Start; security review; Git gates | `PORTAL.2` |
| `PORTAL.2` | Expose commercial self-service | Customer Portal | `PORTAL.1`; `EST.4`; `INVOICE.2`; `PAY.2` | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Sales/Financial/Communications | `UNKNOWN` | `NO` | `COND` | `IC.2` | Customer journey, authorization, accessibility | READY/Start; review; Git gates | `IC.2` |
| `PORTAL.3` | Expose appointment self-service | Customer Portal | `PORTAL.1`; `OPS.1`; `COMMS.1` | `OM1` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Scheduling/Operations | `UNKNOWN` | `NO` | `COND` | `IC.2` | Safe request handoff, authorization, accessibility | READY/Start; review; Git gates | `IC.2` |
| `COMMS.2` | Complete launch notification journeys | Communications | `COMMS.1`; `DISP.2`; `EST.4`; `INVOICE.2`; `PAY.2` | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Cross-domain events/templates | `UNKNOWN` | `NO` | Serialized integration | `IC.2` | Consent, delivery, retry, observability | READY/Start; review; Git gates | `IC.2` |
| `IC.2` | Integrate revenue and experience | Integration | All Phase 2 milestones | `LAP` suggested | `ACP` | integration workspace `UNKNOWN` | `ACP` rule | `TYPE B` | integrates impacts | all Phase 2 | `NO` | `NO` | Serialized | `IC.2` | One head, booked-to-cash, idempotency/reconciliation | Integration approval; Git gates | `RPT.1` |
| `RPT.1` | Establish launch reporting projections | Analytics | `IC.2`; `BE.8` | `OM1` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Event/projection schemas | `UNKNOWN` | `NO` | `COND` | `IC.3` | Rebuild, freshness, totals, tenant | READY/Start; review; Git gates | `RPT.2` |
| `RPT.2` | Deliver operational dashboards | Analytics | `RPT.1` | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE A` if no shared change | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `NO` | `UNKNOWN` until READY | `IC.3` | Dashboard totals, drill-down, accessibility | READY/Start; review; Git gates | `BEA.6` |
| `RPT.3` | Deliver launch reports and exports | Analytics | `RPT.1`; `ACC.2`; `INV.4` | `OM1` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Finance/Migration exports | `UNKNOWN` | `NO` | Serialized integration | `IC.3` | Export controls and reconciled totals | READY/Start; finance review; Git gates | `MIG.2` |
| `BE.9` | Validate launch economics | Economics | `BE.8`; `RPT.1`; `ACC.2` | `ECO` suggested | `ECOR` | `UNKNOWN` before `READY` | `ECOR` rule | `TYPE B` | `UNKNOWN` | KPI/financial ownership | `NO` | `NO` | `COND` | `IC.3` | KPI/source/report variance | READY/Start; economics/finance review | `BEA.7` |
| `BEA.6` | Surface bounded operational exceptions | Beacon | `RPT.1`; existing Beacon foundation | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Reporting/Mission Control | `UNKNOWN` | `NO` | `COND` | `IC.3` | Signal source, stale state, acknowledgement audit | READY/Start; owner review; Git gates | `BEA.7` |
| `BEA.7` | Add launch health summaries | Beacon | `BEA.6`; `RPT.2`; `BE.9` | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Reporting/Economics/Release | `UNKNOWN` | `NO` | `COND` | `IC.3` | Source links, freshness, summary accuracy | READY/Start; owner review; Git gates | `IC.3` |
| `AUTO.1` | Add bounded launch automation | Automation | `COMMS.2`; `BEA.6`; `PLAT.1` | `OM1` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Authorization/events/module APIs | `UNKNOWN` | `NO` | Serialized integration | `IC.3` | Audit, retry, kill switch, negative authorization | READY/Start; owner/security review | `IC.3` |
| `MIG.2` | Execute representative dry run | Migration | `MIG.1`; `IC.2`; `RPT.3` | `MIG` suggested | `MIGR` | operation workspace `UNKNOWN` | approved immutable inputs | `TYPE C` | import execution | all data owners | approved non-prod required | `NO` | Serialized | `IC.3` | Timed run, counts, rejects, teardown | Separate operation approval; review | `MIG.3` |
| `MIG.3` | Prove repeatable migration | Migration | `MIG.2`; `BE.9`; `BEA.7` | `MIG` suggested | `MIGR` | operation workspace `UNKNOWN` | approved immutable inputs | `TYPE C` | import execution | all data owners | approved non-prod required | `NO` | Serialized | `IC.3` | Repeatability, delta, thresholds, rollback | Separate operation approval; review | `MIG.4` |
| `TECH.3` | Complete technician closeout | Field Service | `TECH.2`; `INV.3`; `INVOICE.2` | `OM2` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE B` | `UNKNOWN` | Inventory/Financial | `UNKNOWN` | `NO` | `COND` | `IC.3` | Arrival-to-closeout, evidence, handoff | READY/Start; review; Git gates | `TECH.4` |
| `TECH.4` | Harden technician experience | Field Service | `TECH.3`; `COMMS.2` | `OM1` suggested | `ACP` | `UNKNOWN` before `READY` | `ACP` rule | `TYPE A` if no shared change | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `NO` | `UNKNOWN` until READY | `IC.3` | Device, retry/stale state, performance/accessibility | READY/Start; physical-device review | `IC.3` |
| `IC.3` | Integrate Version 1.0 candidate | Integration | Phase 3 accepted set | `LAP` suggested | `ACP` | integration workspace `UNKNOWN` | `ACP` rule | `TYPE B` | integrates impacts | all V1 modules | `NO` | `NO` | Serialized | `IC.3` | One head, regression, traceability | Integration approval; Git gates | `IC.4` |
| `IC.4` | Validate production-like Preview | Release | `IC.3` | `LAP` suggested | `ACP` | release workspace `UNKNOWN` | approved immutable candidate | `TYPE C` | executes approved Preview migrations | all launch workflows | `YES` | `NO` | Serialized | `IC.4` | Preview journeys, security, performance, backup/restore | Separate Preview approval; acceptance | `MIG.4` |
| `MIG.4` | Prepare immutable cutover package | Migration | `MIG.3`; `IC.4` | `MIG` suggested | `MIGR` | package workspace `UNKNOWN` | approved immutable evidence | `TYPE C` | cutover plan; execution separate | Housecall Pro/QuickBooks | `NO` | package only | Serialized | `IC.5` | Checksums, reconciliation, rollback, authorities | Package approval; no execution | `REL.1` |
| `REL.1` | Run controlled pilot | Release | `IC.4`; `MIG.4` | `LAP` suggested | `ACP` | release workspace `UNKNOWN` | approved immutable candidate | `TYPE C` | `UNKNOWN` | all launch workflows | `YES` if Preview pilot | `NO` | Serialized | `IC.5` | Pilot journeys, support/training metrics | Separate pilot approval; acceptance | `REL.2` |
| `REL.2` | Close Version 1.0 readiness | Release | `REL.1`; `RPT.3`; `TECH.4`; `ACC.2` | `LAP` suggested | `ACP` | PMO workspace `UNKNOWN` | approved evidence set | `TYPE B` | `NO` | readiness dossier | `NO` | `NO` | Serialized | `IC.5` | Checklist evidence and residual risks | Multidisciplinary owner review | `IC.5` |
| `IC.5` | Obtain Version 1.0 go/no-go | Release | `REL.2` | `LAP` suggested | `ACP` | PMO workspace `UNKNOWN` | immutable release/cutover package | `TYPE C` | no execution | all release contracts | `NO` | approval only | Serialized | `IC.5` | Closed blockers, signatures, rollback readiness | Explicit go/no-go; no deploy | `REL.3` |
| `REL.3` | Execute separately approved release | Release | `IC.5`; separate Production approval | `LAP` suggested | `ACP` | release workspace `UNKNOWN` | approved immutable artifact SHA | `TYPE C` | Production migration possible | all launch contracts | preceding Preview required | `YES` | Serialized | Production | Smoke, monitoring, reconciliation, rollback | Explicit Production action approval | `COMPLETE` |

## Reconciled READY execution contracts

These contracts are approved as scheduler definitions by the bounded MMQ.5
readiness pass. `READY` still requires a separate explicit owner Start.

| Code | Execution boundary | Contract |
| --- | --- | --- |
| `PLAT.1` | `OM1`; `/Users/michaelfouse/Development/ACP-Enterprise`; `work/plat-1-launch-controls` isolated worktree | Immediately before creation fetch `origin`, require 0 behind, and record the full `origin/customer-management-v1` SHA. Scope is the launch role matrix, branch enforcement, audit access, secrets boundary, and support runbooks. Migration ownership is `NO`; stop and replan if schema work is discovered. Shared authorization/tenant/security impact makes this `TYPE B`: implementation may run isolated with `PHONE-BUG.1` and `BE.8`, but `IC.1` integration is serialized. Preview and Production are `NO`. Validate role/tenant/branch negative cases, audit access, repository lint/tests, runbooks, and one Alembic head. Owner checkpoints are Start, security/review acceptance, and each Git gate. |
| `PHONE-BUG.1` | `OM2`; `/Users/michaelfouse/Development/ACP-Enterprise`; `work/phone-bug-1` isolated worktree | Fetch, require 0 behind, and record the full authoritative branch SHA before creation. Reimplement the bounded nullable-source and mobile error-boundary fix on current Enterprise; do not cherry-pick `215506f`. Migration ownership is `NO`. Customer response/type and router impacts make this `TYPE B`; implementation can run with `PLAT.1`, but final contract/router integration is serialized at `IC.1`. Validate exact reproduction, normalization of null/undefined/legacy values, absence of unsafe string calls, targeted customer/router tests, frontend lint/typecheck/build, regression, and a separately approved Preview physical-iPhone run. Production is `NO`. Owner checkpoints are Start, review/Git gates, separate Preview approval, and physical-device acceptance. |
| `BE.8` | `ECO`; `/Users/michaelfouse/Development/ACP-Enterprise` at isolated economics ref; `work/be-8-v1-economics-contract` | Fetch and require `origin/business-economics-foundation` at `49261468f443273ffefcf78d200048dccf097e0f`, otherwise stop. Scope is the roadmap KPI catalog, ownership map, attribution/profitability inputs, QuickBooks boundary, and reconciliation tolerances; it is not external Phase 8 engine implementation. Migration ownership is `NO`; shared financial/KPI ownership makes it `TYPE B`, with serialized `IC.1` integration. Preview and Production are `NO`. Validate documentation/contracts, source ownership, terminology, links, and applicable economics contract tests. Owner checkpoints are Start, economics/finance review, and Git gates. |
| `PE-TELEMETRY-1` | `LAP`; read-only owner-controlled live validation on the existing MC.1/phone execution architecture | `TYPE C`, not product implementation. At Start, fetch and record the authoritative Enterprise SHA and owner-selected existing non-Production environment; make no workspace, code, migration, or deployment change. Capture live owner-started phone progress/telemetry evidence and stop if the approved environment is unavailable. Owner Start and evidence acceptance are the only remaining checkpoints. Production is `NO`; no integration commit is expected. |

## Defect register

| Code | Severity | Status | Evidence | Required scope | Candidate evidence | Capacity | Type | Readiness gaps | Integration |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `PHONE-BUG.1` | Urgent | `READY` | iPhone developer error screen; undefined `source` reached a string operation; default React Router error screen rendered | Reproduce on authoritative paths; normalize nullable/legacy `source`; prevent unsafe string operations; add mobile-safe application/route error handling; targeted regression coverage; physical iPhone validation | Candidate `215506fa63201b88f55b6fbd09459558e5eae5a6` changed 11 customer-response/form/detail/router files and added nullable-source plus route-failure tests; it is 18 commits off the merge base while authoritative Enterprise is 83 commits off, so use as review evidence only and reimplement from current Enterprise | `OM2` assigned | `TYPE B` due shared frontend contract/router; migration `NO` | `ACP`; worktree `work/phone-bug-1` after Start; fetch, require 0 behind, record authoritative SHA; frontend lint/typecheck/build, targeted customer/router tests, regression, then separately approved Preview and physical iPhone evidence | Serialize customer contract/router integration at `IC.1`; owner Start, review/Git gates, then separate Preview approval; Production `NO` |

The candidate commit is evidence, not completion and not permission to cherry-pick.
MMQ.5 does not implement the defect.

Candidate `215506fa63201b88f55b6fbd09459558e5eae5a6` changed exactly:

- `frontend/src/api/customerResponses.test.ts`
- `frontend/src/api/customerResponses.ts`
- `frontend/src/api/customers.ts`
- `frontend/src/components/customers/CustomerDetailView.tsx`
- `frontend/src/components/customers/CustomerForm.tsx`
- `frontend/src/components/customers/CustomerManagement.tsx`
- `frontend/src/components/customers/PropertyForm.tsx`
- `frontend/src/routing/RouteErrorBoundary.tsx`
- `frontend/src/routing/router.test.tsx`
- `frontend/src/routing/router.tsx`
- `frontend/src/types/customers.ts`

It adds nullable/legacy `source` normalization and guards optional string
operations, plus tests for nullable migrated responses and a synthetic route
render failure. It does not contain physical-iPhone evidence. Its merge-base
comparison with authoritative Enterprise is 18 candidate-side commits versus 83
Enterprise-side commits, so direct adoption is unsafe; bounded reimplementation
and current-regression review are required.

## Continuous capacity schedule

`CURRENT` records active or review work. Future positions are visible scheduling
intent. Only a row explicitly marked `READY` may be started after owner Start.

| Capacity | CURRENT | NEXT | NEXT +1 | NEXT +2 | NEXT +3 | Blocking facts |
| --- | --- | --- | --- | --- | --- | --- |
| `OM1` | Idle after repository-evidenced EST.2/EST.3 history | `PLAT.1` — `READY` | `COMMS.1` — `PLANNED` | `OPS.1` — `PLANNED` | `PUR.1` — `PLANNED` | `PLAT.1` still requires explicit owner Start; later items await `CRM.2` and residual inventory scope |
| `OM2` | Idle; historical “Machine 2” Inventory capacity is reconciled as permanent `OM2` | `PHONE-BUG.1` — `READY` urgent | `CRM.2` — `PLANNED` | `DISP.2` — `PLANNED` | `TECH.1` — `PLANNED` | Defect requires explicit Start and fresh implementation; later items await `CRM.2`/`OPS.1`/`DISP.2` |
| `MIG` | `CUTOVER.1` — `WAITING FOR OWNER REVIEW` on isolated ref candidate | `MIG.1` — `PLANNED` | `MIG.2` — `PLANNED` | `MIG.3` — `PLANNED` | `MIG.4` — `PLANNED` | `CUTOVER.1` lacks acceptance; `CRM.2` and `OPS.1` are incomplete; `CUTOVER.2` is absent from the ref |
| `ECO` | External Phase 8 — `WAITING FOR OWNER REVIEW` at `4926146` | `BE.8` — `READY` | `BE.9` — `PLANNED` | `ACC.1` finance review — `PLANNED` | `ACC.2` finance review — `PLANNED` | External Phase 8 is distinct from roadmap `BE.8`; `BE.8` requires explicit Start and serialized `IC.1` integration |
| `LAP` | `MMQ.5` — `WAITING FOR OWNER REVIEW` | `PE-TELEMETRY-1` — owner-controlled validation, `READY` | `IC.1` — `PLANNED` | `IC.2` — `PLANNED` | `IC.3` — `PLANNED` | Telemetry requires owner-started live phone evidence, not implementation; checkpoints await accepted inputs |

## Parallel and serialized schedule

Potential concurrent groups, after separate `READY` and Start approvals:

- `OM1: PLAT.1`, `OM2: CRM.2`, and `MIG: MIG.1` discovery may run alongside
  `ECO` contract reconciliation when repositories, files, and resources remain
  isolated.
- `COMMS.1` may run with `EST.3`-downstream planning only after `CRM.2` contracts
  stabilize.
- Domain-local UI/tests may run in parallel with backend work only when the
  approved task contracts claim disjoint files and shared resources.
- `TYPE B` implementation can run in parallel in isolation, but its accepted
  migrations and shared contracts enter Laptop 1 one at a time.

Always serialized:

- Alembic integration and every integration checkpoint.
- Authorization, tenant/security, public shared schemas, event envelopes, and
  shared financial ownership changes.
- Invoice/payment/QuickBooks reconciliation facts.
- Import/migration execution, cutover, Preview, pilot, and Production.
- The `PHONE-BUG.1` shared customer-response/router contract integration.

## Alembic integration protocol

The current authoritative Enterprise head is `t5j7f9b1c386`. Multiple capacities
may implement migration-bearing milestones in isolated worktrees. Immediately
before final integration, the integrating capacity must:

1. Verify a clean handoff and immutable accepted commit.
2. Fetch `origin` and confirm the authoritative branch tip.
3. Run `alembic heads` against the incoming and authoritative histories.
4. If the incoming parent is stale, re-parent the incoming unapplied revision
   onto the then-current authoritative head only when semantically valid and
   with reviewed ownership.
5. Re-run empty upgrade, agreed-base upgrade, safe downgrade/re-upgrade, metadata
   drift, affected domain regression, and cross-domain contract tests in
   disposable non-production storage.
6. Prove exactly one authoritative Alembic head before commit/push approval.

Never force-push around a collision, silently publish sibling heads, or rewrite
a revision applied to a shared environment. A merge migration requires explicit
architectural justification, owner review, and proof that deliberate parallel
lineages must remain represented.

The recent serialized evidence is:

```text
s4i6d8e0a275  EST.2 estimate approval
→ s4i6d8f0h275  INV.1 inventory foundation
→ t5j7e9g1i386  INV.2 adjustments/cycle counts
→ t5j7f9b1c386  EST.3 estimate/job conversion (current head)
```

## Automatic handoff contract

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

- Implementation through pre-review validation stays within the approved
  milestone without intermediate approval.
- Owner review does not itself authorize commit, push, Preview, or Production;
  each required privileged gate remains separately recorded.
- Fetch/integration check is mandatory even for documentation-only work.
- Completion never auto-promotes or auto-starts the next `PLANNED` item.
- The next item starts only when it independently satisfies every `READY`
  requirement and receives explicit owner Start.

## Evidence-reconciled milestone state

| Milestone | State | Commit/ref evidence | Reconciliation note |
| --- | --- | --- | --- |
| `PRICEBOOK.1` | `COMPLETE` | `e97dc408742e0037330b79156cd0a5ba583c6649` | Authoritative ancestor; foundation, migration, tests, API/UI |
| `EST.1` | `COMPLETE` | `e0f68972f65bfec7272dd133060b348375497b3e` | Authoritative ancestor; estimate foundation |
| `EST.2` | `COMPLETE` | `f52b184634acb89e21816533148cb3110fdce31e` | Authoritative ancestor; revision/customer approval workflow and migration |
| `INV.1` | `COMPLETE` | `2389af0415161fd685c3c73b8751df2ad440f701` | Authoritative ancestor; inventory foundation and migration |
| `INV.2` | `COMPLETE` | `303548a7ecba9bc8b5a788237cc3a81a233c0d48` | Authoritative ancestor; adjustments/cycle counts and migration |
| `EST.3` | `COMPLETE` | `7ebad9c90c7d511c0cca82395ef4210b0deea750` | Authoritative ancestor; estimate/job conversion and migration |
| `MC.1` | `COMPLETE` | `6ac4934623f3b573b674b62865aa6a6088d44da6` | Authoritative ancestor; Mission Control contract-drift prevention |
| `MMQ.4` | `COMPLETE` | `4dd2884a25bd1e86a11792a95239f58b88c6abe8` | Current authoritative tip before MMQ.5 |
| `PLAT.1` | `READY` | Complete execution contract above; Start resolves current `origin/customer-management-v1` | Owner Start still required; no schema ownership |
| `LOCATION.2` | `COMPLETE` | `8268737b0a1d8feee4a30e76eb245040a8e15623` — `feat(migration): add native service location reconciliation` | Isolated linear ancestor of `SOURCE.5`/tip; adds revisions through `b7d3f9a5c028`; owner-supplied acceptance corroborates mapping |
| `SOURCE.5` | `COMPLETE` | `915f9383ce4daeec2974cf92d23abdc1bc2a1009` — `feat(migration): add native customer identity consolidation` | Direct child of `LOCATION.2` and parent of `CUTOVER.1`; adds `c8e4a0b6d139`; owner-supplied acceptance corroborates mapping |
| `CUTOVER.1` | `WAITING FOR OWNER REVIEW` | `origin/customer-migration-workstream` at `f4e54775090b7c21afda079912a3729583662313` | Linear child of `SOURCE.5`; migration head `d9f5b1c7e240`; integration/acceptance not recorded |
| `CUTOVER.2` | verification required | No code, subject, or documentation label found on `origin/customer-migration-workstream` | Not treated as complete or as a dependency |
| Economics Phase 5 | `COMPLETE` | `7d7aa63542c24f76283f4977e768244c3eb63e83` — `docs(economics): define phase 5 profitability intelligence contracts` | Linear isolated ancestor; owner-supplied completion; immutable contracts, implementation/tests, no runtime sources |
| Economics Phase 6 | `COMPLETE` | `521ed293c8967c57b6fc9af267998d9d097b69f7` — `feat(economics): establish deterministic profitability computation` | Direct descendant of Phase 5; implementation/tests; no migration |
| Economics Phase 7 | `COMPLETE` | `af06a7fa83364bc877edab81d18dae96e12de7d2` — `feat(economics): establish operational fact acquisition foundation` | Direct descendant of Phase 6; provider-neutral acquisition implementation/tests |
| Economics external Phase 8 | `WAITING FOR OWNER REVIEW` | `49261468f443273ffefcf78d200048dccf097e0f` — `feat(economics): add deterministic allocation and profitability engines` | Branch tip/direct Phase 7 descendant; pure application engine, no persistence/migration/API/UI; distinct from roadmap `BE.8` |
| `BE.8` | `READY` | Phase 7 dependency `af06a7fa83364bc877edab81d18dae96e12de7d2`; complete contract above | External Phase 8 acceptance is independent; owner Start required |
| `PHONE-BUG.1` | `READY` | candidate analysis and complete fresh-implementation contract above | Candidate is review evidence only; physical-iPhone acceptance remains owner-controlled |
| `PE-TELEMETRY-1` | `READY` | Existing `MC.1` and phone execution architecture | `TYPE C` live validation only; owner must Start and select the existing non-Production environment |
| `MMQ.5` | `WAITING FOR OWNER REVIEW` | Uncommitted documentation diff from `4dd2884a25bd1e86a11792a95239f58b88c6abe8` | Scheduler validation evidence required in the same review package |

## Scheduler invariants

The scheduler is consistent only when:

- codes are unique across active, roadmap, defect, and planning registers;
- every dependency resolves to a defined or evidence-recorded milestone;
- the graph is acyclic;
- one capacity has at most one `IN PROGRESS` assignment;
- every `READY` item passes all READY evidence fields;
- `TYPE B` and migration-bearing items name a serialized checkpoint;
- checkpoint order remains `IC.1` -> `IC.2` -> `IC.3` -> `IC.4` -> `IC.5`;
- every `COMPLETE` commit exists on the stated accessible ref and the evidence
  boundary is explicit;
- current branch, commit, Alembic head, machine schedule, and status ledgers
  agree; and
- no queue state implies Preview, Production, migration execution, or Start.
