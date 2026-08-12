# MMQ.7 — Current Enterprise Multi-Lane Queue Reconciliation

**Status:** `MMQ.7 — IN PROGRESS`

**Refresh instant:** 2026-08-11, America/New_York

**Operating window:** the next five continuous development days after owner acceptance

**Environment boundary:** local development only; Preview and Production are prohibited

## Authority and safety boundary

This document preserves `LAP-B` as the Laptop 1 queue-reconciliation capacity. It
is a planning overlay,
not a status mutation of the [Master Milestone Queue](master-milestone-queue.md),
the [Version 1 roadmap](version-1-implementation-roadmap.md), or the
[Continuous Production Scheduler](continuous-production-scheduler.md). Those files
remain authoritative and are not changed by MMQ.7.

The owner-supplied active assignments are preserved: `OM1: PHONE.FINAL`, `MIG:
MIG.PREP.3`, `ECO: BE.VECTORS.1`, and `LAP-B: MMQ.7`. MMQ.7 does not duplicate,
inspect, modify,
integrate, or interrupt their work. A future assignment shown here is not
executable unless its dependencies, complete execution contract, capacity and
migration position remain current and its existing authorization permits Start.

For a newly approved milestone during this five-day sprint, Start authorizes this
routine non-Production lifecycle within the packet's exact boundary:

```text
IMPLEMENT → routine refactor → TEST → VALIDATE → STAGE exact boundary → COMMIT
→ FETCH → mechanical integration/reconciliation when unambiguous
→ revalidate when required → normal fast-forward PUSH → COMPLETE
```

It never authorizes scope expansion, schema not named in the packet, semantic
conflict resolution, import/cutover, Preview, Production, deployment, irreversible
work, force-push, or an explicit roadmap checkpoint. These are mandatory STOPs.

## Reconciled production state

### Git and evidence inspected

| Repository/ref | Fetched tip | Finding |
| --- | --- | --- |
| Enterprise `origin/customer-management-v1` | `9f3612b883015bc9e63ab2b026a4e8c9c77bd105` | Current linear tip. Adds PHONE-WEEKEND.2 Checkpoint 2, EST.4, current Inventory lineage, DISP.2, and controlled TECH.1 readiness plus execution-safety fixes. |
| Migration `origin/customer-migration-workstream` | `40f76e1cf2aa8e1b6de003dc1c8352aa23c01022` | MIG.PREP.3 preflight closure: deterministic read-only readiness code/tests/documentation; no import, environment operation, Preview, Production, or MIG.2 promotion |
| Economics `origin/business-economics-foundation` | `8942a5ec1f01b2941fcee11d9020a8dc5e87061d` | BE.VECTORS.1 synthetic reconciliation/replay contract pending owner review; TYPE A documentation only and no BE.9/BE.10 promotion |
| Inventory architecture | `dd4a620aa93e209fee813f556bebefe9946cb12a` | Approved Inventory/Purchasing boundary evidence |
| Commercial workflow architecture | `f418c368d41c713d1396086632c9d1431f15effc` | Approved commercial boundary evidence |
| `origin/main` | `96dc3d0f5dadfc83728003093fc5f0ef654ae689` | Not the Enterprise delivery authority |

Relevant architecture inspected includes the module map, platform principles,
authorization/tenant security, transaction contract, notification outbox,
Dispatch workspace, Jobs domain, Inventory/Purchasing boundary, and commercial
workflow contract. Domain ownership stays with the owning service; repositories
enforce tenant predicates; network/provider work stays outside transactions; no
module writes another module's tables.

### Current facts and uncertainty

| Area | Reconciled fact | Evidence grade / uncertainty |
| --- | --- | --- |
| Enterprise | EST.4 is complete at `62c0d84`; DISP.2 at `98ae825`; current Inventory implementation at `d892cf9` plus `9c2b114`; PHONE-WEEKEND.2 Checkpoint 2 at `ff3db82`. PHONE.FINAL remains owner-supplied active on OM1. TECH.1 is the sole durable READY milestone. | Git boundaries and scheduler manifest prove completions/readiness. No `PHONE.FINAL` code exists in repository metadata, so its exact alias/boundary is owner-supplied and must not be inferred as TECH.1. |
| Inventory | INV.3-LEGACY is integrated historical evidence, distinct from roadmap INV.3. The current linear migration chain includes reservation/material issue and EST.4 schema work. INV.2A remains scheduler-blocked pending explicit residual-scope reconciliation. | The subjects do not by themselves prove INV.2A complete; the current durable manifest explicitly keeps it blocked. |
| Migration | MIG.1, MIG.PREP.2, and MIG.PREP.3 are complete/pushed. MIG.2 remains blocked by accepted IC.2, accepted RPT.3, approved immutable non-Production dataset/environment evidence, and separate TYPE C approval. | MIG.PREP.3 explicitly says only MIG.1 is complete among execution gates. |
| Economics | BE.8, BE.PLAN.1, BE.REVIEW.1, BE.EVIDENCE.1, and BE.GAP.1 are complete. BE.VECTORS.1 is implemented at `8942a5e` and pending owner review. BE.9 remains blocked by RPT.1, ACC.2, source-authority closure and Finance acceptance. | BE.VECTORS.1 is synthetic TYPE A documentation and explicitly creates no runtime or policy authority. |
| Laptop | PHONE-WEEKEND.2 implementation is complete; PHONE.FINAL remains active on OM1. LAP-A is idle but IC.1 is blocked. LAP-B owns MMQ.7 only. | Multiple preserved PHONE worktrees exist. MMQ.7 does not inspect or modify their state. |
| Worktrees | LAP-B is isolated at current Enterprise. Other worktrees are PHONE-owned. | No independent product worktree for an idle lane is accessible; absence is not completion evidence. |
| Alembic | Authoritative Enterprise has exactly one head, `u6k8f0h2j497`, through `u6k8g0c2d497 → v7l9h1d3e508 → u6k8f0h2j497`. | Static revision-graph validation. All later schema work must descend from the then-current head; sibling heads remain prohibited. |

## Permanent capacity model

| Capacity | Permanent lane | Current | Scheduling authority |
| --- | --- | --- | --- |
| `OM1-A` | Enterprise product | `PHONE.FINAL` active (owner-supplied alias) | Existing authorization only; do not infer or duplicate scope |
| `OM1-B` | Additional Enterprise capacity | Available but no independently READY assignment | New assignment authority + complete packet |
| `OM1-C` | Additional Enterprise/economics support | Available but no independently READY assignment | New assignment authority + complete packet |
| `OM2-A` | Enterprise Operations | Idle; no safe assignment due TECH.1 capacity-binding conflict | Resolve manifest OM1 versus roadmap OM2 ownership before Start |
| `OM2-B` | Enterprise/Inventory | Idle; INV.2A blocked | Residual-scope owner review before any Inventory successor |
| `OM2-C` | Potential additional Enterprise capacity | Inactive standby | Activate only on measured load and an independently executable packet |
| `MIG` | Customer Migration | `MIG.PREP.3` active/review boundary | Existing preparation authority; MIG.2 separately blocked |
| `ECO` | Business Economics | `BE.VECTORS.1` active/review boundary | Existing documentation authority; BE.9 remains blocked |
| `LAP-A` | integration/release | Idle; IC.1 blocked | Serialized checkpoint only after every Phase 1 input is accepted |
| `LAP-B` | production planning/queue management | `MMQ.7` | This document; no product or integration ownership |

Capacity identity persists between assignments. No capacity may pull `PLANNED` or
blocked work merely to avoid idleness.

## Five-day critical path and concurrency

The shortest launch path is:

```text
CRM.2 complete → OPS.1 complete
→ {DISP.2 || INV.2A}
→ {TECH.1 || PUR.1}
→ EST.4 + COMMS.1 complete + MIG.1 complete + Phase 1 accepted set
→ IC.1
→ TECH.2 + INVOICE.1 + PAY.1 + PORTAL.1 + PUR.2
→ INV.3 → PUR.3 → INV.4
→ INVOICE.2 → {INVOICE.3 || PAY.2} → PAY.3 → ACC.1 → ACC.2
→ COMMS.2 + PORTAL.2 + PORTAL.3 → IC.2
→ RPT.1 → {RPT.2 || RPT.3 || BEA.6 || BE.9}
→ BEA.7 + AUTO.1 + TECH.3 → TECH.4 + MIG.2 → MIG.3
→ IC.3 → [separate Preview approval] IC.4
→ MIG.4 → REL.1 → REL.2 → IC.5
→ [separate Production approval] REL.3
```

The five-day throughput focus remains Phase 1. EST.4 and DISP.2 are complete.
TECH.1 is the sole durable READY Enterprise candidate, but its capacity binding
conflicts with the roadmap and occupied OM1; MMQ.7 does not Start it. `INV.2A` has roadmap
dependency closure but remains non-startable until INV.3-LEGACY scope and
migration reconciliation proves no duplicate ownership. `DISP.2` then unlocks
`TECH.1`; an accepted `INV.2A` unlocks `PUR.1`. MIG.1 and COMMS.1 are complete.
Shared contracts and all migrations serialize at `IC.1`.

Business goals map to the graph as follows:

| Goal | Shortest remaining path |
| --- | --- |
| Launch-ready CRM | `CRM.2` complete; validate at `IC.1` |
| Operations lifecycle | `OPS.1` complete; validate with the Phase 1 accepted set at IC.1 |
| Communications | `COMMS.1` complete → `COMMS.2` after revenue dependencies |
| Dispatch | `OPS.1 complete → DISP.2` |
| Technician/field | `OPS.1 → DISP.2 → TECH.1 → IC.1 → TECH.2 → TECH.3 → TECH.4` |
| Estimates | `CRM.2 + EST.3 → EST.4 complete` |
| Inventory/Purchasing | `OPS.1 → INV.2A → PUR.1 → {PUR.2, TECH.2→INV.3} → PUR.3 → INV.4` |
| Invoicing/Payments | `IC.1 + EST.4 + OPS.1 → INVOICE.1`; then `PAY.1`, `INVOICE.2`, `PAY.2`, `INVOICE.3`, `PAY.3` |
| Accounting/Reporting/Economics | `PAY.3 → ACC.1 → ACC.2 → IC.2 → RPT.1 → BE.9/RPT.2/RPT.3` |
| Migration proof | `MIG.1` complete; then `IC.2 + RPT.3 → MIG.2 → BE.9 + BEA.7 → MIG.3` |
| Preview readiness | all above → `IC.3`; Preview remains separately prohibited until approved |
| Phone unattended readiness | PHONE-WEEKEND.2 proof chain described below; never depends on MMQ.6 runtime changes |

## Canonical deep queue registry

Every row expands the execution profiles below and therefore records all required
fields. Status is planning eligibility, not Start authorization.

**Repository/start/worktree profiles:** `ACP` = fetch, require zero behind, record
full current `origin/customer-management-v1`, then create unique
`work/<lower-code>-<slug>` worktree after Start. `MIGR` = fetch and record full
`origin/customer-migration-workstream`, require zero divergence from the approved
starting ref, then unique worktree. `ECOR` is the equivalent rule for
`origin/business-economics-foundation`. `INT` = Laptop integration worktree from
the then-authoritative immutable accepted Enterprise tip. No reuse of LAP-A or an
active capacity worktree.

**Gate profiles:** Owner checkpoint `R` = owner Start, batched completion review;
`S` adds security review; `F` adds finance review; `D` requires separate
Preview/deployment approval; `P` requires explicit Production/irreversible
approval. Universal STOPs are the mandatory STOPs in the authority section.
Migration `U` means unresolved until READY and schema discovery is a STOP; `N`
means no migration authorized; `Y` means likely schema-bearing and final
integration must use the migration ledger; `X` means migration/import operation
and is TYPE C. Shared impact `L` is domain-local, `C` shared contract/event, `A`
authorization/security, `M` migration/all-domain, `F` financial, `I` integration.
Parallel `A` is disjoint TYPE A; `B` is isolated implementation/serialized final
integration; `C` is owner-controlled operation. Preview is `NO` unless `YES*`
requires a new separate approval. Production is always `NO`, except `REL.3` is
`YES*` and remains prohibited here.

| Code | Title/objective; domain | Dependencies | Preferred / safe alternate | Repo profile | Type; migration; shared; parallel | IC; Preview; Production | Validation boundary | Owner; successors; READY evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `CRM.2` | Close launch CRM gaps; CRM | Customer/Location foundations | historical OM2 / none | ACP (integrated `b75f9b6`) | B; N; C; B | IC.1; NO; NO | API/UI/events, tenant, dedupe | complete; `OPS.1,EST.4,COMMS.1,PORTAL.1,MIG.1`; Git evidence |
| `OPS.1` | Complete launch job lifecycle; Operations | CRM.2, Scheduling/Jobs | historical OM2-A / none | ACP (integrated `c893965`) | B; N; C; B | IC.1; NO; NO | lifecycle, auth, events, E2E | complete; `DISP.2,INV.2A,INVOICE.1,PORTAL.3,MIG.1`; Git boundary/tests |
| `DISP.2` | Complete dispatch execution; Dispatch | OPS.1, Dispatch Assignment V1 | historical OM2 / none | ACP (integrated `98ae825`) | B; N; C; B | IC.1; NO; NO | assignment, arrival, exceptions, roles | complete; `TECH.1,COMMS.2`; Git boundary/tests |
| `EST.3` | Estimate-to-job conversion; Sales | EST.2 | historical OM1 | ACP integrated | B; Y; C; B | IC.1; NO; NO | conversion/persistence/events | complete; `EST.4`; Git evidence |
| `EST.4` | Complete launch estimate experience; Sales | EST.3, CRM.2 | historical OM1 / none | ACP (integrated `62c0d84`) | B; Y; C; B | IC.1; NO; NO | options, discounts, approval, responsive/auth | complete; `INVOICE.1,PORTAL.2,COMMS.2`; Git boundary/tests |
| `INV.2` | Adjustments/cycle counts; Inventory | INV.1 | historical OM2 | ACP integrated | B; Y; C; B | IC.1; NO; NO | concurrency/audit/regression | complete; `INV.2A`; Git evidence |
| `INV.2A` | Launch inventory control core; Inventory | INV.2, OPS.1 | OM2-B / OM1-A | ACP | B; Y; C; B | IC.1; NO; NO | on-hand, reservation, transfer, concurrency | R; `PUR.1,INV.3,PUR.2`; OPS accepted + legacy reconciliation clear + packet |
| `PUR.1` | Purchasing foundation; Purchasing | architecture, INV.2A | OM1-A / OM2-B | ACP | B; Y; C/F; B | IC.1; NO; NO | vendor/PO lifecycle, auth, audit | R; `PUR.2`; INV.2A accepted + packet |
| `TECH.1` | Technician application shell; Field | OPS.1, DISP.2, identity | durable manifest OM1; roadmap OM2 conflict | ACP | B; N; C; B | IC.1; NO; NO | responsive/accessibility/routes/roles | READY with machine boundary; `TECH.2`; owner must resolve occupied OM1 versus roadmap OM2 binding before idle-lane assignment |
| `COMMS.1` | Launch communications; Communications | CRM.2, outbox | historical Enterprise / none | ACP (integrated `06ba0f3`) | B; N; C; B | IC.1; NO; NO | consent, retry, provider failures, transactions | complete; `COMMS.2,INVOICE.2,PORTAL.3`; Git boundary/tests |
| `BE.8` | Version 1 economics contract; Economics | Economics Phase 7 | historical OM1-C | ECOR integrated | B; N; F; B | IC.1; NO; NO | KPI ownership/tolerances | complete; `BE.9,ACC.1`; Git evidence |
| `MIG.1` | Freeze mapping/reconciliation; Migration | CUTOVER.1/2, CRM.2, OPS.1 | historical OM1-B / none | MIGR (integrated `3158e58`) | B; N; M; B | IC.1; NO; NO | maps, rejects, counts, synthetic set | complete; `MIG.2`; Git boundary/tests/documentation |
| `PLAT.1` | Launch platform controls; Platform | platform/security foundations | historical OM1 | ACP integrated | B; N; A; B | IC.1; NO; NO | role/tenant/branch/audit/runbooks | complete; `IC.1,PAY.1,PORTAL.1,AUTO.1`; Git evidence |
| `IC.1` | Integrate launch foundations; Integration | all Phase 1 rows | LAP-A / LAP-B only if reassigned after PHONE | INT | B; M; I; B | IC.1; NO; NO | aggregate contracts, regression, one head | R; Phase 2; all accepted + immutable SHAs + migration slots |
| `TECH.2` | Enable field execution; Field | TECH.1, EST.4, IC.1 | OM2-A / OM1-A | ACP | B; Y; C; B | IC.2; NO; NO | field journey/evidence/role/branch | R; `INV.3,INVOICE.2,TECH.3`; dependencies + packet |
| `INV.3` | Capture job materials; Inventory | INV.2A, TECH.2 | OM2-B / OM1-A | ACP | B; Y; C/F; B | IC.2; NO; NO | ledger/concurrency/corrections | R; `PUR.3,INV.4,TECH.3`; legacy scope reconciled + packet |
| `PUR.2` | Receive/reconcile purchases; Purchasing | PUR.1, INV.2A, IC.1 | OM2-B / OM1-A | ACP | B; Y; C/F; B | IC.2; NO; NO | partial receipt/discrepancy/posting | R; `PUR.3`; dependencies + packet |
| `PUR.3` | Replenishment controls; Purchasing | PUR.2, INV.3 | OM1-A / OM2-B | ACP | B; U; C/F; B | IC.2; NO; NO | threshold/approval/recommendation audit | R; `INV.4`; dependencies + packet |
| `INV.4` | Inventory launch readiness; Inventory | INV.3, PUR.3 | OM2-B / OM1-A | ACP | B; U; C/M; B | IC.2; NO; NO | counts/reconcile/permissions/performance | R; `IC.2,RPT.3`; dependencies + packet |
| `INVOICE.1` | Operational invoicing; Financial | EST.4, OPS.1, IC.1 | OM1-A / OM2-A | ACP | B; Y; F; B | IC.2; NO; NO | totals/tax/tenant/idempotency | F; `INVOICE.2,PAY.1`; finance decisions closed + packet |
| `INVOICE.2` | Invoice workflow; Financial | INVOICE.1, TECH.2, COMMS.1 | OM2-A / OM1-A | ACP | B; Y; F/C; B | IC.2; NO; NO | end-to-end generation/send/receipt | F; `INVOICE.3,PAY.2,COMMS.2,PORTAL.2,TECH.3`; packet |
| `INVOICE.3` | Controlled invoice corrections; Financial | INVOICE.2 | OM1-A / OM2-A | ACP | B; Y; F; B | IC.2; NO; NO | void/credit/recompute/audit | F; `PAY.3,ACC.1`; packet |
| `PAY.1` | Payment provider boundary; Financial | INVOICE.1, PLAT.1 | OM2-A / OM1-A | ACP | B; Y; A/F; B | IC.2; NO; NO | threat/token/webhook/idempotency | S+F; `PAY.2`; provider decision + packet |
| `PAY.2` | Collect/record payments; Financial | PAY.1, INVOICE.2 | OM1-A / OM2-A | ACP | B; Y; F; B | IC.2; NO; NO | duplicate charge/retry/receipt/totals | F; `PAY.3,PORTAL.2,COMMS.2`; packet |
| `PAY.3` | Refund/failure reconciliation; Financial | PAY.2, INVOICE.3 | OM2-A / OM1-A | ACP | B; Y; F; B | IC.2; NO; NO | refunds/late webhook/settlement | F; `ACC.1,COMMS.2`; packet |
| `ACC.1` | Define QuickBooks handoff; Accounting | INVOICE.3, PAY.3, BE.8 | OM1-A + OM1-C review / none | ACP | B; U; F; B | IC.2; NO; NO | mapping/idempotency/control matrix | F; `ACC.2`; finance ownership decision + packet |
| `ACC.2` | Accounting reconciliation; Accounting | ACC.1 | OM1-A + OM1-C review / none | ACP | B; Y; F; B | IC.2; NO; NO | export/ack/variance/retry | F; `RPT.3,BE.9,IC.2`; packet |
| `PORTAL.1` | Portal trust boundary; Portal | CRM.2, PLAT.1, IC.1 | OM2-A / OM1-A | ACP | B; Y; A/C; B | IC.2; NO; NO | linking/enumeration/tenant security | S; `PORTAL.2,PORTAL.3`; identity decision + packet |
| `PORTAL.2` | Commercial self-service; Portal | PORTAL.1, EST.4, INVOICE.2, PAY.2 | OM2-A / OM1-A | ACP | B; U; C/F; B | IC.2; NO; NO | journey/auth/accessibility | R; `IC.2`; packet |
| `PORTAL.3` | Appointment self-service; Portal | PORTAL.1, OPS.1, COMMS.1 | OM1-A / OM2-A | ACP | B; U; C; B | IC.2; NO; NO | safe request/auth/accessibility | R; `IC.2`; packet |
| `COMMS.2` | Launch notification journeys; Communications | COMMS.1, DISP.2, EST.4, INVOICE.2, PAY.2 | OM2-A / OM1-A | ACP | B; Y; C/F; B | IC.2; NO; NO | consent/delivery/retry/observability | R; `IC.2,AUTO.1,TECH.4`; packet |
| `IC.2` | Integrate revenue/experience; Integration | all Phase 2 accepted | LAP-A / LAP-B if assigned | INT | B; M; I/F; B | IC.2; NO; NO | booked-to-cash/reconciliation/one head | F; Phase 3; immutable inputs + slots |
| `RPT.1` | Reporting projections; Analytics | IC.2, BE.8 | OM1-A / OM2-A | ACP | B; Y; C/F; B | IC.3; NO; NO | rebuild/freshness/totals/tenant | R; `RPT.2,RPT.3,BE.9,BEA.6`; packet |
| `RPT.2` | Operational dashboards; Analytics | RPT.1 | OM2-A / OM1-A | ACP | A if local; U; L; A/B | IC.3; NO; NO | totals/drilldown/accessibility | R; `BEA.7,IC.3`; packet |
| `RPT.3` | Reports/exports; Analytics | RPT.1, ACC.2, INV.4 | OM1-A / OM2-A | ACP | B; U; F/M; B | IC.3; NO; NO | export controls/reconciled totals | F; `MIG.2,IC.3,REL.2`; packet |
| `BE.9` | Validate launch economics; Economics | BE.8, RPT.1, ACC.2 | OM1-C / none | ECOR | B; U; F/C; B | IC.3; NO; NO | KPI/source/report variance | F; `BEA.7,MIG.3,IC.3`; external Phase 8 disposition + packet |
| `BEA.6` | Operational exceptions; Beacon | RPT.1, Beacon foundation | OM2-A / OM1-A | ACP | B; U; C; B | IC.3; NO; NO | sources/staleness/ack audit | R; `BEA.7,AUTO.1`; packet |
| `BEA.7` | Launch health summaries; Beacon | BEA.6, RPT.2, BE.9 | OM2-A / OM1-A | ACP | B; U; C/F; B | IC.3; NO; NO | links/freshness/accuracy | R; `MIG.3,IC.3`; packet |
| `AUTO.1` | Bounded launch automation; Automation | COMMS.2, BEA.6, PLAT.1 | OM1-A / OM2-A | ACP | B; U; A/C; B | IC.3; NO; NO | audit/retry/kill switch/negative auth | S; `IC.3`; rule decisions + packet |
| `MIG.2` | Representative dry run; Migration | MIG.1, IC.2, RPT.3 | OM1-B / none | MIGR | C; X; M; C | IC.3; YES*; NO | timed counts/rejects/teardown | D; `MIG.3`; separate non-prod operation approval |
| `MIG.3` | Repeatable migration proof; Migration | MIG.2, BE.9, BEA.7 | OM1-B / none | MIGR | C; X; M; C | IC.3; YES*; NO | repeatability/delta/threshold/rollback | D; `MIG.4,IC.3`; separate operation approval |
| `TECH.3` | Technician closeout; Field | TECH.2, INV.3, INVOICE.2 | OM2-A / OM1-A | ACP | B; Y; C/F; B | IC.3; NO; NO | arrival-to-closeout/evidence/handoff | R; `TECH.4`; packet |
| `TECH.4` | Harden technician experience; Field | TECH.3, COMMS.2 | OM1-A / OM2-A | ACP | A/B; U; L/C; A/B | IC.3; NO; NO | device/retry/stale/perf/accessibility | R + device review; `IC.3,REL.2`; packet |
| `IC.3` | Integrate V1 candidate; Integration | Phase 3 accepted set | LAP-A / LAP-B if assigned | INT | B; M; I; B | IC.3; NO; NO | full regression/traceability/one head | R; `IC.4`; immutable inputs + slots |
| `IC.4` | Production-like Preview validation; Release | IC.3 | LAP-A / none | INT | C; X; I; C | IC.4; YES*; NO | journeys/security/perf/backup | D; `MIG.4,REL.1`; explicit Preview approval |
| `MIG.4` | Immutable cutover package; Migration | MIG.3, IC.4 | OM1-B / none | MIGR | C; X; M; C | IC.5; NO; NO | checksums/reconcile/rollback/authority | P; `REL.1`; package approval, no execution |
| `REL.1` | Controlled pilot; Release | IC.4, MIG.4 | LAP-A / none | INT | C; X; I; C | IC.5; YES*; NO | journeys/support/training metrics | D; `REL.2`; separate pilot approval |
| `REL.2` | Close V1 readiness; Release | REL.1, RPT.3, TECH.4, ACC.2 | LAP-A / LAP-B planning support | INT | B; N; I; B | IC.5; NO; NO | checklist/residual risks | R; `IC.5`; complete dossiers |
| `IC.5` | V1 go/no-go; Release | REL.2 | LAP-A / none | INT | C; N; I; C | IC.5; NO; NO | blockers/signatures/rollback readiness | P; `REL.3`; explicit go/no-go |
| `REL.3` | Separately approved release; Release | IC.5, Production approval | LAP-A / none | INT | C; X; I; C | Production; YES*; YES* | smoke/monitor/reconcile/rollback | P; complete; explicit Production action approval |

Universal exclusions for every row: no unapproved adjacent feature, no foreign
domain table write, no LAP-A file/worktree use, no Preview/Production, no import,
and no force-push. Each row's validation plus repository standards, affected
regression, tenant/authorization negatives, `git diff --check`, and exactly one
Alembic head (when integrated) forms its completion evidence.

### Queue depth by capacity

The registry provides 37 legitimate future Enterprise implementation candidates
that can be routed between Enterprise capacities only after dependencies
and file claims permit. Each of those Enterprise capacities therefore has a
deep candidate pool without duplicating active work; it is not permission to put
the same milestone on multiple lanes. Specialist depth is truthfully smaller:
MIG has future `MIG.2`–`MIG.4` (3), ECO has BE.VECTORS.1 followed by dependency-
blocked Economics work, LAP-A has protected PHONE-WEEKEND.2 then integration/
release gates, and LAP-B has MMQ.7 plus planning/review support. No filler is
invented.

The roadmap also names 12 explicitly deferred, non-Version-1 placeholders:
`ACC.GL.1`, `ACC.AP.1`, `ACC.CLOSE.1`, `INV.5`, `TECH.5`, `PORTAL.4`, `BEA.8`,
`LUM.1`, `LUM.2`, `LIA.1`, `LIA.2`, and `SAAS.1`. They lack approved Version 1
scope and are deliberately not schedulable assignments or execution packets.

## Five-day production board

| Capacity | CURRENT | NEXT | NEXT +1 | NEXT +2 | NEXT +3 | Deeper backlog | Blocker / migration risk / integration |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OM1-A | `PHONE.FINAL` active | Completion/review | `TECH.1` only after binding/alias reconciliation | `PUR.1` blocked | `INVOICE.1` blocked | Enterprise roadmap | PHONE.FINAL exact repository alias is owner-supplied; do not overlap TECH.1 blindly |
| OM1-B | Idle | No executable assignment | `TECH.1` only after explicit durable reassignment | `PUR.1` blocked | `PAY.1` blocked | Candidate pool only | Sole READY item is bound to occupied OM1 identity; safe idle |
| OM1-C | Idle | No executable assignment | Finance/source review only if separately defined | `ACC.1` blocked | `BE.9` blocked | Candidate pool only | No machine-enforceable packet; safe idle |
| OM2-A | Idle | No safe assignment now | `TECH.1` after capacity-binding decision | `TECH.2` blocked | `PAY.1` blocked | Enterprise roadmap | Roadmap suggests OM2, durable manifest binds TECH.1 to OM1; contradiction is STOP |
| OM2-B | Idle | No safe assignment now | `INV.2A` after residual-scope decision | `PUR.1` after INV.2A | `PUR.2` blocked | Inventory/Purchasing path | Integrated Inventory does not automatically satisfy blocked INV.2A code |
| OM2-C | Inactive standby | No assignment | TECH.1 only after activation and binding decision | — | — | Candidate pool only | No independently READY packet assigned to OM2-C |
| MIG | `MIG.PREP.3` active/review | Completion evidence | `MIG.2` blocked | `MIG.3` blocked | `MIG.4` blocked | 0 beyond three | IC.2 + RPT.3 + immutable input/environment + TYPE C approval |
| ECO | `BE.VECTORS.1` active/review | Completion evidence | `BE.POLICY.1` owner-evidence blocked | `BE.9` blocked | `BE.10` blocked | deeper BE.11–BE.20 | Synthetic vectors do not close source/Finance gates |
| LAP-A | Idle | No executable assignment | `IC.1` blocked | `IC.2` blocked | `IC.3` blocked | later release gates | IC.1 waits INV.2A, PUR.1, TECH.1 and complete accepted Phase 1 set |
| LAP-B | `MMQ.7` active | validation/commit | post-completion ref refresh | migration-ledger audit | owner queue batch | registry maintenance only | No product execution |

### Day-by-day control board

| Day | Parallel production | Serialized/batched control |
| --- | --- | --- |
| 1 | Continue PHONE.FINAL, MIG.PREP.3, BE.VECTORS.1, and MMQ.7. Keep idle lanes safe. | Record immutable refs/head; raise TECH.1 capacity conflict for owner/scheduler disposition. |
| 2 | If TECH.1 binding is resolved and PHONE.FINAL is non-overlapping, Start it only on the authorized capacity. | Fetch current Enterprise and enforce its fingerprinted migration-free boundary. |
| 3 | Reconcile current Inventory outputs against INV.2A; do not implement residual scope without owner acceptance. | Do not run MIG.2; its TYPE C and dependency gates remain open. |
| 4 | If TECH.1 is accepted and all Phase 1 inputs close, reassess PUR.1 and IC.1; otherwise preserve blockers. | Serialize any future schema change from current head `u6k8f0h2j497`. |
| 5 | Refresh refs, accepted evidence and queues; never infer completion from subjects alone. | Batch owner decisions and roll forward only independently executable work. |

Predicted starvation is real and safe: OM1-B/OM1-C and OM2-A lack an unconflicted
machine-bound READY assignment; OM2-B waits for INV.2A residual-scope authority;
LAP-A waits for the full IC.1 input set; MIG waits for MIG.2 TYPE C dependencies;
and ECO waits after BE.VECTORS.1 review for approved source/policy work. OM1 remains
occupied by PHONE.FINAL.

## Reusable execution packets

The common packet rules are: unique isolated worktree; fetch and record the
profile's full remote tip; require zero behind/divergence; never use LAP-A's
worktrees; exact-scope changes only; apply the streamlined non-Production Git
lifecycle stated above; STOP on every universal or row-specific STOP; completion
evidence is changed-file list, immutable commit SHA, commands/results, affected
regression, contract/migration impact, one-head proof where applicable, fetch/
fast-forward push evidence, and final clean worktree. Owner Start remains required.

### NOT STARTABLE — INV.2A (legacy reconciliation required)

- Scope: residual inventory location/on-hand, reservation, release and transfer
  workflows not already delivered by INV.2 or INV.3-LEGACY.
- Exclude: duplicate legacy scope, roadmap INV.3 job consumption, purchasing,
  invoicing, costing/economics.
- Ownership: Inventory owns stock ledger; Jobs supplies stable references; no
  direct foreign-table writes.
- Validate: ledger balance, concurrency/locking, reservation idempotency,
  transfer authorization, correction audit, tenant/Branch isolation.
- Migration: likely `Y`; exact legacy revision and semantic overlap must be
  resolved before Start, not during implementation.

### READY but NOT ASSIGNABLE to an idle lane — TECH.1

- Scope: role-scoped itinerary/job context, protected navigation, responsive and
  accessible technician shell, typed APIs and device-oriented tests.
- Exclude: job lifecycle, assignment, materials, time/payroll, invoice/payment,
  GPS/offline sync not expressly approved.
- Ownership: Field UI composes immutable Jobs/Dispatch/CRM projections; owning
  domains retain writes and authorization.
- Validate: route/role/Branch negatives, loading/error/stale states, accessibility,
  responsive device matrix, API contracts, lint/typecheck/build.
- Migration: none; schema discovery is STOP. The fingerprinted boundary permits
  only technician frontend, named router/navigation seams, and technician docs.
- Assignment STOP: durable scheduler capacity is `OM1`, currently occupied by
  PHONE.FINAL, while the roadmap suggests Office Machine 2. Owner/scheduler
  reconciliation must resolve that conflict before OM2-A or another lane starts.

### NOT STARTABLE — PUR.1 (INV.2A acceptance required)

- Scope: vendor and purchase-order domain, lifecycle, authorization, repository,
  APIs, audit events and tests within approved architecture.
- Exclude: receiving, replenishment, AP/QuickBooks, payment, costing, automatic
  ordering.
- Ownership: Purchasing owns vendors/POs; Inventory owns stock; Financial owns
  monetary posting; integrations use IDs/events.
- Validate: lifecycle/concurrency, tenant/Branch and role negatives, audit/events,
  deterministic totals boundary and repository/API regression.
- Migration: likely `Y`; serialize through IC.1.

### NOT STARTABLE — IC.1

- Scope: mechanically integrate immutable accepted Phase 1 outputs, reconcile
  shared contracts, serialize migrations and produce aggregate validation evidence.
- Exclude: feature changes, semantic conflict decisions, Preview/Production,
  accepting incomplete milestones.
- Ownership: LAP integration only after LAP-A is free or owner assigns another
  integration capacity; LAP-B planning does not imply integration authority.
- Validate: full Phase 1 dependency closure, tenant/security and E2E regression,
  migration upgrade/downgrade policy, exactly one head, immutable SHAs.
- Migration: `M`; any semantic conflict or Alembic collision is STOP.

Packets maintained: 4 total. TECH.1 is durable READY but not safely assignable to
an idle lane until its capacity conflict is resolved; INV.2A, PUR.1, and IC.1 are
`NOT STARTABLE`. Completed EST.4, DISP.2, current Inventory, OPS.1, COMMS.1, and
MIG.1 require no new packet. PHONE.FINAL remains outside MMQ.7 ownership.

## Migration serialization ledger

Implementation may run in parallel. Final migration integration is a single
global queue; sibling heads are forbidden.

| Slot | Candidate | Admission requirement | Current disposition |
| --- | --- | --- | --- |
| 0 | Authoritative Enterprise through current Inventory | fetched tip + current head | Baseline `9f3612b`; one linear head `u6k8f0h2j497` via scheduler `u6k8g0c2d497` and EST.4 `v7l9h1d3e508` |
| 1 | Next accepted schema-bearing milestone | immutable accepted implementation; fetch immediately before integration; parent equals then-current authoritative head | No candidate is currently approved/ready. Never preserve a historical parent or create a sibling head. |
| 2+ | Later Phase 1/2 schema-bearing work | prior slot pushed, fresh fetch/head, approved schema boundary | One at a time through IC checkpoints; migration imports remain separately TYPE C |

Every slot executes:

```text
FETCH authoritative branch → identify current head → compare incoming parent
→ re-parent only when semantically mechanical and revision is unapplied
→ empty + agreed-base upgrade validation → safe downgrade/re-upgrade where supported
→ metadata/head check → affected and cross-domain regression
→ prove exactly one head → commit/integrate → normal fast-forward push
```

STOP for an applied/shared revision rewrite, semantic dependency, destructive
downgrade, ambiguous ordering, data-integrity risk, merge revision need, or any
force-push. A deliberate merge migration requires separate architecture/owner
judgment; it is never the planned convenience path.

## Owner review batching and decisions

Use at most three predictable windows per day: morning Starts/decisions, midday
urgent STOP review only, and end-of-day completion evidence. A machine may proceed
to an already owner-Started READY milestone without waiting for batch review of an
unrelated completed milestone.

| Class | Batch policy |
| --- | --- |
| A. Routine completion | Batch immutable SHAs, changed files, validation, migration/shared-contract declarations, push/clean evidence at end of day; owner retains accept/reject per milestone. |
| B. Genuine decisions | Interrupt promptly only for scope, product behavior, schema ownership, security/data integrity, semantic conflict, provider/finance policy, migration ordering ambiguity, or external Phase 8 disposition. |
| C. Preview/deployment | Separate scheduled gate; none authorized in this plan. No batching with routine completion implies approval. |
| D. Production/irreversible | Separate explicit action approval with immutable package and rollback; prohibited in this plan. |

Genuine owner decisions currently queued are: external Economics Phase 8
accept/reject/remediate; the BE.GAP.1 Finance/source policy decisions; any semantic
conflict discovered while re-parenting INV.3-LEGACY; any schema discovered in an
`U` milestone; provider, tax, payment, QuickBooks, and accounting ownership choices
when their milestones approach READY; and every IC/Preview/Production gate.

## Automatic successor and fallback rules

On CURRENT completion, the capacity records immutable evidence and the scheduler
re-evaluates dependencies. `NEXT` becomes dependency-eligible automatically, but
never starts automatically: its packet must be complete and the owner must have
issued Start. If Start was issued for the full packet, routine Git completion is
already authorized; if not, use the next owner window.

| Capacity | Automatic eligibility test | Safe fallback if NEXT remains blocked |
| --- | --- | --- |
| OM1-A | PHONE.FINAL remains CURRENT until its existing completion boundary | TECH.1 only after proving PHONE.FINAL does not duplicate it and resolving capacity binding |
| OM1-B | No independent executable work is proven | TECH.1 only after explicit durable reassignment; otherwise idle |
| OM1-C | No independent executable work is proven | Separately approved Finance/source contract review only; never substitute for ECO ownership |
| OM2-A | No safe immediate assignment because TECH.1 has conflicting current capacity evidence | Resolve durable OM1 binding versus roadmap OM2 suggestion; otherwise idle |
| OM2-B | Current Inventory/INV.3-LEGACY is complete; INV.2A remains residual-scope blocked | PUR.1 only after accepted INV.2A; otherwise idle safely |
| OM2-C | Inactive until measured load and a disjoint executable packet justify activation | No fallback assignment merely to use hardware |
| MIG | MIG.PREP.3 completion/review does not unlock MIG.2 | MIG.2 waits for IC.2, RPT.3, immutable inputs/environment and TYPE C approval |
| ECO | BE.VECTORS.1 completion/review does not unlock BE.9/BE.10 | BE.POLICY.1 and BE.9 remain blocked; do not infer missing source policy |
| LAP-A | IC.1 remains blocked by incomplete Phase 1 accepted set | Remain idle; no product or PHONE.FINAL work may be absorbed |
| LAP-B | MMQ.7 completion → future authoritative ref refresh | Maintain ledger/board only; never absorb product/integration work |

No fallback duplicates active work. Before routing, fetch, confirm no active branch/
worktree/assignment claims the code, and record the capacity change.

## Phone-control state

PHONE-WEEKEND.2 Checkpoint 2 is integrated at `ff3db82`. PHONE.FINAL is now the
owner-supplied active OM1 assignment. MMQ.7 does not equate PHONE.FINAL with
TECH.1, modify either boundary, or move phone work to LAP-A:

```text
phone owner Start
→ unattended bounded execution
→ monotonic telemetry + heartbeat/reconnect/duplicate-Start evidence
→ phone owner review and per-milestone approval
→ scheduler proves a different successor independently READY
→ second phone Start
→ acknowledgement and nonzero progress
```

The successor must have satisfied dependencies, a complete packet, isolated
workspace, resolved starting SHA, migration position, and owner Start. MMQ.7 may
observe evidence and keep the queue supplied; it may not edit PHONE.FINAL,
PHONE-WEEKEND.2, runtime, worktrees, or status. Failure to identify a safe
successor is a STOP, not permission to start blocked work.

## OM2-C capacity decision

Do not activate OM2-C during this refresh. Current constraints are authority and
dependency throughput, not raw slots: TECH.1 is READY but capacity-conflicted,
INV.2A/PUR.1/IC.1 are blocked, and PHONE.FINAL owns OM1. Shared Docker/test
contention and collision risk remain. Reassess
after 24–48 hours only if measurements show all of the following: sustained queue
wait for at least two independently READY disjoint TYPE A/B packets, CPU/memory/
I/O headroom during parallel builds, no increase in flaky/timeout tests, and the
migration/integration queue is not the bottleneck. Activation otherwise increases
collision and review load without shortening the critical path.

## Validation ledger

| Check | Result |
| --- | --- |
| Unique codes | Passed for the 50 Version 1 roadmap nodes; the 12 explicitly deferred post-Version-1 placeholders are separately listed and not scheduled. `INV.3-LEGACY`, `PHONE-WEEKEND.2`, `PHONE.FINAL`, `MIG.PREP.3`, `BE.VECTORS.1`, and `MMQ.7` remain distinct. |
| Dependency closure/cycles | Passed against the roadmap DAG; no new product dependency introduced. Active legacy/control codes are outside the product DAG and explicitly distinguished. |
| Blocked assignment | Passed: PHONE.FINAL, MIG.PREP.3, BE.VECTORS.1 and MMQ.7 are active; TECH.1 is READY but capacity-conflicted; no blocked item is assigned. |
| Capacity consistency | Passed; one CURRENT per capacity, specialist depth not inflated, alternatives require reassignment and collision check. |
| Repository/ref consistency | Passed with explicit uncertainty for the owner-supplied PHONE.FINAL alias; other recent completion subjects and boundaries were inspected. |
| Migration serialization | Passed: authoritative head is `u6k8f0h2j497`; future revisions must use the then-current head and never form siblings. |
| IC ordering | Passed: IC.1 → IC.2 → IC.3 → IC.4 → IC.5. |
| Owner/Preview/Production gates | Preserved; Preview and Production are prohibited and TYPE C remains separately approved. |
| Historical vs roadmap | Passed: INV.3-LEGACY is not INV.3; external Phase 8 is not BE.8/BE.9; completed foundations remain historical. |
| Cross-domain ownership | Passed against inspected architecture; IDs/events/projections are integration seams and no foreign table writes are authorized. |
| Duplicate active work/LAP-A collision | Passed by plan: PHONE.FINAL, MIG.PREP.3, BE.VECTORS.1 and MMQ.7 each have one owner; protected worktrees are excluded. |
| Markdown/relative links | Relative project links used; final mechanical validation required below. |

## Owner review package

MMQ.7 stops at the queue/control boundary. One immediate owner/scheduler decision
is required before assigning the only READY product milestone: reconcile TECH.1's
durable `OM1` capacity binding with the roadmap's Office Machine 2 suggestion and
confirm it does not overlap PHONE.FINAL. Further owner action remains required for
INV.2A residual scope, Economics/Finance policy, and every TYPE C/Preview/
Production action. Keep OM2-C inactive unless measured evidence crosses the
activation threshold.

**MMQ.7 — COMPLETE / PUSH AUTHORIZED AFTER CLEAN VALIDATION**
