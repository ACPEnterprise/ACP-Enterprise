# MMQ.6 — Five-Day Continuous Production Plan

**Status:** `WAITING FOR OWNER REVIEW`

**Planning instant:** 2026-08-11, America/New_York

**Operating window:** the next five continuous development days after owner acceptance
**Environment boundary:** local development only; Preview and Production are prohibited

## Authority and safety boundary

This document establishes `LAP-B` as the second permanent Laptop 1 engineering
capacity for production planning and queue management. It is a planning overlay,
not a status mutation of the [Master Milestone Queue](master-milestone-queue.md),
the [Version 1 roadmap](version-1-implementation-roadmap.md), or the
[Continuous Production Scheduler](continuous-production-scheduler.md). Those files
remain authoritative and are not changed by MMQ.6.

The owner-supplied active assignments are preserved: `OM2-A: OPS.1`, `OM2-B:
INV.3-LEGACY`, and `LAP-A: PHONE-WEEKEND.2`. MMQ.6 does not duplicate, inspect,
modify, integrate, or interrupt their work. A future assignment shown here is not
`READY` and does not authorize Start unless its packet says `STARTABLE`, all READY
evidence remains true, and the owner issues milestone Start.

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
| Enterprise `origin/customer-management-v1` | `06ba0f39b85b0eeda7e5a4d1747bb326bd28668a` | Authoritative Enterprise tip; linearly adds `OPS.1` at `c89396546a6ba6012e48694ba7737bd30e316637` and `COMMS.1` at the tip to the previously proven `PLAT.1`, `PHONE-BUG.1`, and `CRM.2` history |
| Enterprise local `customer-management-v1` | `038ac6fd932de36d3f2961de59ba9992a5eb428c` | Four commits behind; scheduler/MMQ files have pre-existing unstaged LAP-A changes and are protected |
| Migration `origin/customer-migration-workstream` | `3158e587a2a386be7c645e963e50ead65d93e0c8` | Linear descendant of `e9ab50d`; implements `MIG.1` mapping/reconciliation with code, tests, and bounded documentation. Branch documentation explicitly records CUTOVER.1 owner acceptance and CUTOVER.2 complete/pushed. |
| Economics `origin/business-economics-foundation` | `8bf76da7672c3ab9caf25ca965f2e1591e16155e` | Linear descendant of `bb27bca`; adds a source-authority evidence matrix without changing `BE.8`, `BE.PLAN.1`, BE.9 dependencies, or the external Phase 8 owner gate |
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
| Enterprise | `PLAT.1`, `PHONE-BUG.1`, `CRM.2`, `OPS.1`, and `COMMS.1` are complete in fetched authoritative history. | Git inspection proves OPS.1's Operations/Scheduling/Jobs implementation and focused tests at `c893965`; COMMS.1's domain, persistence, service/API, authorization, and focused tests are at `06ba0f3`. This is boundary evidence, not an inference from changed SHAs alone. |
| Inventory | `INV.3-LEGACY` reconciliation is active on OM2-B and owns a pending Inventory migration. | Owner-supplied. No accessible ref/worktree exposes its SHA, exact revision ID, parent, or boundary. Preserve; do not duplicate. It is distinct from roadmap `INV.3`. |
| Migration | `CUTOVER.1` is owner accepted/complete; `CUTOVER.2` is complete/pushed; `MIG.1` is implemented and pushed. `MIG.2` remains blocked by IC.2, RPT.3, and separate non-Production operation approval. | The migration branch explicitly names CUTOVER.2 in `docs/deployment/cutover-2-deterministic-planning-rehearsal.md` and records both cutover states in the MIG.PREP package. `3158e58` contains the bounded MIG.1 mapping, synthetic reconciliation tests, and freeze document; it performs no import. |
| Economics | `BE.8` and `BE.PLAN.1` are complete/pushed. `BE.9` is blocked by `RPT.1` and `ACC.2`. External Phase 8 is separate and awaits owner disposition. | Git-proven through `8bf76da`; the new matrix confirms missing source authorities and does not promote BE.9. Owner disposition remains genuine. |
| Laptop | LAP-A exclusively owns `PHONE-WEEKEND.2`, including its pending scheduler migration. LAP-B owns MMQ.6 planning. | Owner-supplied plus two preserved PHONE-WEEKEND worktrees; exact active one and migration revision/parent are uncertain. |
| Worktrees | Primary dirty worktree at `038ac6f`; PHONE worktrees at `bd034a3` and `b75f9b6`. | Git-proven. No OM2-A or OM2-B worktree is visible from this repository. |
| Alembic | Fetched Enterprise retains the recorded single head `t5j7f9b1c386`; LAP-A and OM2-B each have a pending unknown revision. | Enterprise head is static-history evidence. Runtime `alembic heads` was not available in this worktree; pending IDs/parents are unknown and block integration ordering by identity. |

## Permanent capacity model

| Capacity | Permanent lane | Current | Scheduling authority |
| --- | --- | --- | --- |
| `OM1-A` | Enterprise product | Available/next approved Enterprise work | Owner Start + packet |
| `OM1-B` | Migration | Available after `MIG.1`; `MIG.2` blocked | Owner Start + separate TYPE C operation packet |
| `OM1-C` | Business Economics | Available; `BE.9` blocked | Owner Start + economics packet |
| `OM2-A` | Enterprise Operations | Available after `OPS.1` completion evidence | New owner Start + packet before reassignment |
| `OM2-B` | Enterprise/Inventory | `INV.3-LEGACY` active | Existing owner Start; no reassignment until completion evidence |
| `LAP-A` | scheduler runtime/integration | `PHONE-WEEKEND.2` active | Exclusively its existing execution contract |
| `LAP-B` | production planning/queue management | `MMQ.6` | This document; no runtime or integration ownership |

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

The five-day throughput focus remains Phase 1. `EST.4` and `DISP.2` have satisfied
Git-proven prerequisites and can start independently after owner Start. OPS.1 is
complete; its completion also makes `INV.2A` dependency-eligible only after the
active INV.3-LEGACY scope/migration reconciliation clears. `DISP.2` then unlocks
`TECH.1`; `INV.2A` unlocks `PUR.1`. MIG.1 and COMMS.1 are already implemented.
All new implementations may be isolated concurrently, but shared contracts and
migrations serialize at `IC.1`.

Business goals map to the graph as follows:

| Goal | Shortest remaining path |
| --- | --- |
| Launch-ready CRM | `CRM.2` complete; validate at `IC.1` |
| Operations lifecycle | `OPS.1` complete; validate with the Phase 1 accepted set at IC.1 |
| Communications | `COMMS.1` complete → `COMMS.2` after revenue dependencies |
| Dispatch | `OPS.1 complete → DISP.2` |
| Technician/field | `OPS.1 → DISP.2 → TECH.1 → IC.1 → TECH.2 → TECH.3 → TECH.4` |
| Estimates | `CRM.2 + EST.3 → EST.4` |
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
| `DISP.2` | Complete dispatch execution; Dispatch | OPS.1, Dispatch Assignment V1 | OM2-A / OM1-A | ACP | B; U; C; B | IC.1; NO; NO | assignment, arrival, exceptions, roles | R; `TECH.1,COMMS.2`; OPS accepted + packet |
| `EST.3` | Estimate-to-job conversion; Sales | EST.2 | historical OM1 | ACP integrated | B; Y; C; B | IC.1; NO; NO | conversion/persistence/events | complete; `EST.4`; Git evidence |
| `EST.4` | Complete launch estimate experience; Sales | EST.3, CRM.2 | OM1-A / OM2-A | ACP | B; U; C; B | IC.1; NO; NO | options, discounts, approval, responsive/auth | R; `INVOICE.1,PORTAL.2,COMMS.2`; dependencies + approved packet |
| `INV.2` | Adjustments/cycle counts; Inventory | INV.1 | historical OM2 | ACP integrated | B; Y; C; B | IC.1; NO; NO | concurrency/audit/regression | complete; `INV.2A`; Git evidence |
| `INV.2A` | Launch inventory control core; Inventory | INV.2, OPS.1 | OM2-B / OM1-A | ACP | B; Y; C; B | IC.1; NO; NO | on-hand, reservation, transfer, concurrency | R; `PUR.1,INV.3,PUR.2`; OPS accepted + legacy reconciliation clear + packet |
| `PUR.1` | Purchasing foundation; Purchasing | architecture, INV.2A | OM1-A / OM2-B | ACP | B; Y; C/F; B | IC.1; NO; NO | vendor/PO lifecycle, auth, audit | R; `PUR.2`; INV.2A accepted + packet |
| `TECH.1` | Technician application shell; Field | OPS.1, DISP.2, identity | OM2-A / OM1-A | ACP | B; U; C; B | IC.1; NO; NO | responsive/accessibility/routes/roles | R; `TECH.2`; dependencies + packet |
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
that can be routed between `OM1-A`, `OM2-A`, and `OM2-B` only after dependencies
and file claims permit. Each of those Enterprise capacities therefore has a
20-plus candidate deep queue without duplicating active work. Specialist depth is
truthfully smaller: OM1-B has future `MIG.2`–`MIG.4` (3), OM1-C has `BE.9` plus finance
review roles (3), LAP-A has five integration checkpoints plus four release gates
(9), and LAP-B has MMQ.6 plus planning/review support. No filler is invented.

The roadmap also names 12 explicitly deferred, non-Version-1 placeholders:
`ACC.GL.1`, `ACC.AP.1`, `ACC.CLOSE.1`, `INV.5`, `TECH.5`, `PORTAL.4`, `BEA.8`,
`LUM.1`, `LUM.2`, `LIA.1`, `LIA.2`, and `SAAS.1`. They lack approved Version 1
scope and are deliberately not schedulable assignments or execution packets.

## Five-day production board

| Capacity | CURRENT | NEXT | NEXT +1 | NEXT +2 | NEXT +3 | Deeper backlog | Blocker / migration risk / integration |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OM1-A | Available | `EST.4` startable | `DISP.2` startable alternate | `PUR.1` conditional | `INVOICE.1` blocked | 31 Enterprise candidates | Owner Starts; PUR waits INV.2A; U/Y migrations serialize at IC.1 |
| OM1-B | Available after `MIG.1` | `MIG.2` blocked | `MIG.3` blocked | `MIG.4` blocked | Evidence/review support only | 0 beyond three | IC.2 + RPT.3 + separate operation approval; IC.3/5 |
| OM1-C | Available; external Phase 8 review pending | Finance contract review | `BE.9` blocked | ACC.1 review blocked | ACC.2 review blocked | 0 legitimate | RPT.1/ACC.2 and Phase 8 disposition; IC.3 |
| OM2-A | Available after `OPS.1` | `DISP.2` startable | `TECH.1` conditional | `TECH.2` blocked | `PAY.1` blocked | 30 candidates | Owner Start; possible schema; IC.1/IC.2 |
| OM2-B | `INV.3-LEGACY` active | `INV.2A` conditional | `PUR.1` conditional fallback | `PUR.2` blocked | roadmap `INV.3` blocked | 29 candidates | Legacy scope/migration reconciliation and OPS; IC.1/IC.2 |
| LAP-A | `PHONE-WEEKEND.2` active | phone-selected successor only | `IC.1` blocked | `IC.2` blocked | `IC.3` blocked | 6 integration/release gates | Pending scheduler migration first/second slot by accepted order; protected |
| LAP-B | `MMQ.6` | Owner-review batching | readiness refresh | integration-ledger audit | Day-5 rollover plan | registry maintenance only | No implementation; MMQ.6 owner review |

### Day-by-day control board

| Day | Parallel production | Serialized/batched control |
| --- | --- | --- |
| 1 | Continue INV.3-LEGACY and PHONE-WEEKEND.2. Owner may Start EST.4 and DISP.2. | Capture immutable current SHAs and pending migration identities. Morning Start window; end-of-day evidence batch. |
| 2 | Continue eligible work; reconcile INV.3-LEGACY boundary before any INV.2A Start. MIG.1 and COMMS.1 remain completed inputs. | First accepted migration enters Slot 1 only; shared CRM/Jobs contract review batch. |
| 3 | If legacy reconciliation clears, Start INV.2A. If DISP.2 completes, prepare TECH.1 without starting before its own approval. OM1-B remains safely idle because MIG.2 is blocked. | Slot 2 migration after Slot 1 push and new head fetch; finance/security decision window if needed. |
| 4 | If DISP accepted, Start TECH.1. If INV.2A accepted, Start PUR.1. | Shared Workforce/Jobs and Inventory contracts batch; next serialized migration slot. |
| 5 | Complete/revalidate Phase 1 candidates; do not start IC.1 until every Phase 1 dependency is accepted. | Final evidence batch, one-head proof, owner rollover/Start decisions, MMQ.6 refresh. |

Predicted starvation points are OM1-B until IC.2 and RPT.3 permit MIG.2; OM1-C until owner
Phase 8 disposition and later RPT/Accounting dependencies; LAP-A after
PHONE-WEEKEND.2 if its independently READY successor is absent; and OM2-B if
legacy scope/migration identity is not reconciled before INV.2A. OM1-A is the
near-term pressure relief through EST.4 and DISP.2.

## Reusable execution packets

The common packet rules are: unique isolated worktree; fetch and record the
profile's full remote tip; require zero behind/divergence; never use LAP-A's
worktrees; exact-scope changes only; apply the streamlined non-Production Git
lifecycle stated above; STOP on every universal or row-specific STOP; completion
evidence is changed-file list, immutable commit SHA, commands/results, affected
regression, contract/migration impact, one-head proof where applicable, fetch/
fast-forward push evidence, and final clean worktree. Owner Start remains required.

### STARTABLE after owner Start — EST.4

- Scope: remaining estimate options, controlled discounts, customer approval
  presentation, responsive end-to-end estimate UX, authorization and tests.
- Exclude: estimate-to-job conversion redesign, invoicing, payment, portal,
  technician runtime, new schema unless separately reclassified and approved.
- Ownership: Estimates owns estimate state; CRM owns customer/location; Price Book
  owns pricing references; Jobs owns converted jobs.
- Validate: options/discount invariants, approval concurrency, tenant/role
  negatives, responsive accessibility, frontend lint/typecheck/build, backend and
  affected EST/CRM regression.
- Migration: `U`; STOP immediately if schema is necessary. Integration at IC.1.

### STARTABLE after owner Start — DISP.2

- Scope: workforce availability projection consumption, durable assignment
  workflow, arrival states, dispatch exceptions, board/API/events and tests.
- Exclude: Jobs lifecycle ownership, Scheduling timing, invented technician
  capabilities, route optimization/GPS, automatic assignment.
- Ownership: Dispatch owns assignment; Jobs owns work lifecycle; Scheduling owns
  appointments; Workforce owns capability/availability facts.
- Validate: assignment concurrency, Branch eligibility, arrival/exception paths,
  dispatcher/technician authorization, event idempotency and E2E evidence.
- Migration: `U`; OPS.1 is immutable at `c893965`. STOP if required Workforce
  capability authority is absent, schema is needed without approval, or the
  Dispatch/Jobs/Scheduling boundary becomes ambiguous.

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

### NOT STARTABLE — TECH.1 (OPS.1 and DISP.2 acceptance required)

- Scope: role-scoped itinerary/job context, protected navigation, responsive and
  accessible technician shell, typed APIs and device-oriented tests.
- Exclude: job lifecycle, assignment, materials, time/payroll, invoice/payment,
  GPS/offline sync not expressly approved.
- Ownership: Field UI composes immutable Jobs/Dispatch/CRM projections; owning
  domains retain writes and authorization.
- Validate: route/role/Branch negatives, loading/error/stale states, accessibility,
  responsive device matrix, API contracts, lint/typecheck/build.
- Migration: `U`, expected none; schema discovery is STOP.

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

Packets prepared: 6 total; 2 dependency-eligible/startable after owner Start and
4 conditional `NOT STARTABLE`. Completed OPS.1, COMMS.1, and MIG.1 require no new
packet. INV.3-LEGACY and PHONE-WEEKEND.2 receive no new packet because they remain
active under separate contracts.

## Migration serialization ledger

Implementation may run in parallel. Final migration integration is a single
global queue; sibling heads are forbidden.

| Slot | Candidate | Admission requirement | Current disposition |
| --- | --- | --- | --- |
| 0 | Authoritative Enterprise | fetched tip + current head | Baseline `06ba0f3`, recorded head `t5j7f9b1c386`; OPS.1 and COMMS.1 add no revision |
| 1 | LAP-A PHONE-WEEKEND.2 or OM2-B INV.3-LEGACY | both immutable accepted commits, exact revision IDs/parents, owner-selected order based on acceptance/readiness | Order unresolved; neither may integrate until identities are recorded |
| 2 | The other of PHONE-WEEKEND.2 / INV.3-LEGACY | Slot 1 pushed, fresh authoritative fetch/head | Must be re-parented mechanically to Slot 1 head if unapplied and semantically independent; otherwise STOP |
| 3 | First accepted EST.4/INV.2A/DISP.2 schema change | prior slot pushed; approved schema boundary | Candidate order by acceptance, never by machine |
| 4+ | PUR.1/TECH.1 and later schema-bearing work | same rule | One at a time through IC.1 and later checkpoints |

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
accept/reject/remediate; exact PHONE-WEEKEND.2 versus INV.3-LEGACY migration order
after identities are known; any schema discovered in an `U` milestone; provider,
tax, payment, QuickBooks, and accounting ownership choices when their milestones
approach READY; and every IC/Preview/Production gate.

## Automatic successor and fallback rules

On CURRENT completion, the capacity records immutable evidence and the scheduler
re-evaluates dependencies. `NEXT` becomes dependency-eligible automatically, but
never starts automatically: its packet must be complete and the owner must have
issued Start. If Start was issued for the full packet, routine Git completion is
already authorized; if not, use the next owner window.

| Capacity | Automatic eligibility test | Safe fallback if NEXT remains blocked |
| --- | --- | --- |
| OM1-A | EST.4 is dependency-eligible; DISP.2 may be routed here only if OM2-A does not own it and its separate Start names OM1-A | Approved domain-local tests/docs for the active milestone only; otherwise idle safely |
| OM1-B | MIG.2 remains blocked until MIG.1, IC.2, and RPT.3 are complete and a separate non-Production operation is approved | Read-only completion-evidence review if explicitly approved; no import or speculative schema |
| OM1-C | BE.9 only after RPT.1 + ACC.2 and Phase 8 disposition | Finance review of an independently READY ACC contract; otherwise idle |
| OM2-A | DISP.2 is dependency-eligible after completed OPS.1; TECH.1 follows accepted DISP.2 | Owner may route EST.4 if still unclaimed and file claims are disjoint |
| OM2-B | INV.2A has its roadmap dependencies but still requires legacy scope/migration reconciliation | PUR.1 only after INV.2A; otherwise a disjoint Enterprise packet routed by owner |
| LAP-A | PHONE-WEEKEND-selected successor must independently be READY | No second phone Start; preserve telemetry and await owner direction |
| LAP-B | MMQ.6 review → readiness refresh | Maintain ledger/board read-only; never absorb LAP-A runtime or integration work implicitly |

No fallback duplicates active work. Before routing, fetch, confirm no active branch/
worktree/assignment claims the code, and record the capacity change.

## PHONE-WEEKEND.2 readiness path

LAP-A exclusively proves the fastest phone-control chain:

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
workspace, resolved starting SHA, migration position, and owner Start. MMQ.6 may
observe the evidence and keep the queue supplied; it may not edit PHONE-WEEKEND.2,
its scheduler migration, runtime, worktree, or status. Failure to identify a
successor is a STOP, not permission to start blocked work.

## OM2-C capacity decision

Do not activate OM2-C during the initial window. Useful independent Phase 1 work
exists, but current constraints are integration and dependency throughput, not raw
implementation slots: two unknown pending migrations, OPS.1 as the main unlock,
shared Docker/test contention, and high shared-contract collision risk. Reassess
after 24–48 hours only if measurements show all of the following: sustained queue
wait for at least two independently READY disjoint TYPE A/B packets, CPU/memory/
I/O headroom during parallel builds, no increase in flaky/timeout tests, and the
migration/integration queue is not the bottleneck. Activation otherwise increases
collision and review load without shortening the critical path.

## Validation ledger

| Check | Result |
| --- | --- |
| Unique codes | Passed for the 50 Version 1 roadmap nodes; the 12 explicitly deferred post-Version-1 placeholders are separately listed and not scheduled. `INV.3-LEGACY`, `PHONE-WEEKEND.2`, and `MMQ.6` are distinct control/preserved codes. |
| Dependency closure/cycles | Passed against the roadmap DAG; no new product dependency introduced. Active legacy/control codes are outside the product DAG and explicitly distinguished. |
| Blocked assignment | Passed: blocked work is board visibility or `NOT STARTABLE`; only EST.4 and DISP.2 are dependency-eligible and still require Start. |
| Capacity consistency | Passed; one CURRENT per capacity, specialist depth not inflated, alternatives require reassignment and collision check. |
| Repository/ref consistency | Passed with explicit uncertainty for inaccessible active refs and literal CUTOVER.2 label. |
| Migration serialization | Passed structurally; actual Slot 1 order remains a STOP until pending revision identities and accepted commits are known. |
| IC ordering | Passed: IC.1 → IC.2 → IC.3 → IC.4 → IC.5. |
| Owner/Preview/Production gates | Preserved; Preview and Production are prohibited and TYPE C remains separately approved. |
| Historical vs roadmap | Passed: INV.3-LEGACY is not INV.3; external Phase 8 is not BE.8/BE.9; completed foundations remain historical. |
| Cross-domain ownership | Passed against inspected architecture; IDs/events/projections are integration seams and no foreign table writes are authorized. |
| Duplicate active work/LAP-A collision | Passed by plan: OPS.1, INV.3-LEGACY, PHONE-WEEKEND.2 receive no duplicate packet; protected worktrees/files are excluded. |
| Markdown/relative links | Relative project links used; final mechanical validation required below. |

## Owner review package

MMQ.6 stops here. Owner review should confirm the two startable packet choices,
accept or change the migration Slot 1 ordering rule once identities arrive, decide
external Economics Phase 8 disposition, and retain OM2-C inactive unless measured
evidence crosses the activation threshold.

**MMQ.6 — WAITING FOR OWNER REVIEW**
