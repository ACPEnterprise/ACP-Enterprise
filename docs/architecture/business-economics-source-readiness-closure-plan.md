# Business Economics Source Readiness Closure Plan

Status: BE.GAP.1 — closure plan complete

Classification: TYPE A — Architecture / dependency planning

## Purpose and authority

This plan converts the frozen
[BE.EVIDENCE.1 matrix](business-economics-source-authority-evidence-matrix.md)
into dependency-ordered source closure work for BE.9 through BE.13. The
[Version 1 Economics Contract](business-economics-v1-contract.md) remains
normative. The [Economics execution plan](business-economics-execution-plan.md)
and [external Phase 8 adoption review](business-economics-phase8-adoption-review.md)
remain controlling for sequencing and reuse.

This document recommends work for scheduler adoption. It does not create,
approve, start, or assign a source milestone; select financial policy; implement
runtime or persistence; authorize a migration; integrate external Phase 8; or
make BE.9 READY. Source domains retain their transactions, and QuickBooks remains
the Version 1 general-ledger authority.

## Frozen baseline

| Item | Evidence |
| --- | --- |
| Authoritative Economics ref | `origin/business-economics-foundation` |
| Starting commit | `8bf76da7672c3ab9caf25ca965f2e1591e16155e` |
| Starting subject | `docs(economics): map source authority evidence` |
| Required facts | 24 |
| AVAILABLE | 2 |
| PARTIAL | 9 |
| ABSENT | 12 |
| CONFLICTING | 0 |
| NOT APPLICABLE | 1 |

The resolved Asset/Fleet decision is fixed: Asset/Fleet owns asset/vehicle
identity, utilization, truck-days, operating periods, and cost evidence.
Workforce equipment capability is not asset or utilization evidence. The Phase 4
Workforce equipment-utilization binding remains historical and stale for Version
1; this plan does not modify it.

## Gap categories

Each closure uses one or more of these exact categories:

- **A. SOURCE CONTRACT GAP:** required identities, fields, semantics, scope, or
  effective-time contract is incomplete.
- **B. SOURCE PERSISTENCE GAP:** authoritative records/history do not exist
  durably in the owning domain.
- **C. SOURCE EVENT/EVIDENCE GAP:** version, correction, event, digest input, or
  replay evidence is incomplete.
- **D. POLICY/OWNER DECISION:** the owner must select a business definition or
  authority; technical work cannot decide it.
- **E. ACCOUNTING/FINANCE DEPENDENCY:** Finance/Accounting approval or evidence is
  required while QuickBooks retains general-ledger authority.
- **F. INTEGRATION DEPENDENCY:** accepted refs, collision review, shared contract,
  or integration checkpoint is required.

## Existing and proposed milestone ownership

At the frozen ref, the only evidenced cross-domain milestone codes relevant here
are `ACC.1`, `ACC.2`, `RPT.1`, and conditional `IC.2`, plus the approved Economics
queue. They are reused and not redefined. No authoritative coded milestone for
the missing source capabilities is present in repository documentation.

The following codes are therefore **provisional PMO recommendations**, not
approved roadmap milestones. Laptop 1/PMO must collision-check and map each to an
existing off-ref roadmap milestone before adopting a new code.

| Provisional code and title | Bounded output | Economics dependency satisfied |
| --- | --- | --- |
| `SRC.DISPATCH.1 — Actual Field Activity Evidence Contract` | Actual Technician assignment, work/travel intervals, trips and corrections | Dispatch/productive-time inputs for BE.9–BE.11 |
| `SRC.SALES.1 — Estimate and Price Book Lineage Contract` | Accepted option plus immutable Price Book item/version/effective pricing | Estimate/Price Book inputs for BE.9–BE.11 |
| `SRC.WORKFORCE.1 — Paid Time and Burden Evidence Contract` | Protected paid-time and Finance-approved burden components/rates | Labor inputs and drivers for BE.9–BE.12 |
| `SRC.INVENTORY.1 — Material Consumption and Costing Evidence Contract` | Consumption/return/transfer identity and approved costing layer | Direct material inputs for BE.9–BE.11 |
| `SRC.PURCHASING.1 — Purchasing Evidence Contract` | Purchase/vendor/currency/correction evidence and unassigned status | Purchasing exception inputs for BE.9–BE.11 |
| `SRC.ASSET-FLEET.1 — Asset and Fleet Operating Evidence Contract` | Asset identity, utilization, operating periods, truck-days and cost | Equipment/truck inputs for BE.9–BE.12 |
| `SRC.FINANCIAL.1 — Revenue and Settlement Correction Contract` | Versioned invoices/payments, credits, refunds, reversals and recognition evidence | Revenue/cash inputs for BE.9–BE.11 |
| `SRC.JOB-QUALITY.1 — Callback and Warranty Evidence Contract` | Original/follow-up Job linkage, responsibility taxonomy and corrections | Quality-cost inputs for BE.9–BE.11 |
| `SRC.MARKETING.1 — Marketing Attribution and Spend Contract` | Campaign/source versions, effective attribution and financial spend linkage | Marketing allocation inputs for BE.9/BE.12 |
| `SRC.PLATFORM.1 — Organization and Party Version Contract` | Version/effective semantics for Company, Branch, Customer and Employee identity | Dimension/source conformance for BE.9/BE.10 |
| `SRC.EVENTS.1 — Economic Event Evidence Contract` | Non-null scope rules, stored source version and correction/replay semantics | Event acquisition evidence for BE.10/BE.11 |
| `SRC.FRESHNESS.1 — Source Freshness Policy Contract` | Owner/Finance-approved SLA versions, cutoff and close effects | Staleness validation for BE.10/BE.15 |

`ACC.1 → ACC.2` owns accepted Accounting/Finance boundaries, including source
pool and financial reporting inputs where its approved scope says so. `RPT.1 →
IC.2` when required owns reporting projection/source-of-truth integration. No
provisional source milestone may redefine those milestones.

## Twenty-four-fact closure scorecard

Every BE.EVIDENCE.1 fact appears exactly once. `Likely` migration impact means
the owning domain appears to lack required durable fields/tables; it is planning
evidence, not migration authorization. `TBD after contract` means architecture
must be approved before persistence impact can be known.

| # | Fact; state today → target | Owner and gap categories | Closure contract; first blocked milestone | Source persistence / migration likelihood | Parallel safety and checkpoint | Required completion evidence |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | Job identity/lifecycle; AVAILABLE → AVAILABLE | Jobs; no closure gap | Existing contract; BE.10 consumes | Existing / none expected | Parallel-safe; BE.10 source-conformance review | Frozen model/ref, version replay, lifecycle and Company/Branch fixtures |
| 2 | Scheduled Appointment context; AVAILABLE → AVAILABLE | Scheduling; no closure gap | Existing contract; BE.10 consumes | Existing / none expected | Parallel-safe; BE.10 source-conformance review | Planned-versus-actual distinction, version/reschedule and scope fixtures |
| 3 | Actual Dispatch/Technician activity/trips; ABSENT → AVAILABLE | Dispatch/Field; A+B+C+F | `SRC.DISPATCH.1`; blocks BE.9 | New durable activity likely / migration likely | Can run parallel; Dispatch/Field owner review then BE.9 checkpoint | Actual interval/trip identities, Company/Branch/Job/Technician links, versions, corrections, digests, tests |
| 4 | Accepted Estimate/option; PARTIAL → AVAILABLE | Sales; A+C+F | `SRC.SALES.1`; blocks BE.9 | Existing Estimate extension likely / migration likely | Parallel with other sources; Sales review then BE.9 checkpoint | Accepted option/version/effective time, correction lineage, Price Book links and conformance fixtures |
| 5 | Price Book lineage; ABSENT → AVAILABLE | Sales/catalog; A+B+C+F | `SRC.SALES.1`; blocks BE.9 | New/other-ref catalog persistence likely / migration likely | Same Sales track as #4; BE.9 checkpoint | Immutable item/version/effective prices and expected component lineage |
| 6 | Issued Invoice revenue; PARTIAL → AVAILABLE | Financial/Invoicing; A+C+D+E+F | `SRC.FINANCIAL.1` plus ACC.2; blocks BE.9 | Existing schema extension likely / migration likely | Technical design parallel; recognition decision before final contract; Accounting checkpoint | Versioned issue/credit/void/adjustment identities, effective dates, recognition matrix, correction/replay tests |
| 7 | Payment/cash evidence; PARTIAL → AVAILABLE | Financial/Payments; A+C+D+E+F | `SRC.FINANCIAL.1` plus ACC.2; blocks BE.9 | Existing schema extension likely / migration likely | Parallel with Invoice work; Accounting checkpoint | Versioned success/refund/reversal amounts, Invoice linkage, acknowledgements and replay tests |
| 8 | Employee/Technician identity; PARTIAL → AVAILABLE | Platform/Workforce; A+C+F | `SRC.PLATFORM.1`; blocks BE.9 | Existing identity extension possible / migration likely | Parallel; Platform/Workforce owner review then BE.9 checkpoint | Stable source version/effective identity, Company/home-Branch semantics, correction and privacy tests |
| 9 | Paid time; ABSENT → AVAILABLE | Workforce/payroll; A+B+C+D+E+F | `SRC.WORKFORCE.1`; blocks BE.9 | New protected time persistence likely / migration likely | Contract design parallel; owner/Finance decision gates completion | Time/pay-period identities, paid classification, effective version, corrections, authorization and aggregate evidence |
| 10 | Productive Job time; ABSENT → AVAILABLE | Field/Operations; A+B+C+F | `SRC.DISPATCH.1`; blocks BE.9 | Durable work intervals likely / migration likely | Parallel with Dispatch; Field/Workforce integration checkpoint | Measured intervals, shared work, Job/Technician links, corrections, scope/replay tests |
| 11 | Burdened labor components/rate; ABSENT → AVAILABLE | Workforce/payroll + Finance; A+B+C+D+E+F | `SRC.WORKFORCE.1` plus ACC.2; blocks BE.9 | Protected effective rates likely / migration likely | Technical envelope parallel; Finance decision gates values | Approved components, rate/effective version, correction, least-privilege and calculation fixtures |
| 12 | Material purchase/unassigned purchasing; ABSENT → AVAILABLE | Procurement/Financial; A+B+C+F | `SRC.PURCHASING.1`; blocks BE.9 | New purchase persistence likely / migration likely | Parallel; Procurement/Financial owner checkpoint | Purchase/vendor/currency/version/correction evidence and explicit unassigned state |
| 13 | Material consumption/returns; ABSENT → AVAILABLE | Inventory/Field; A+B+C+D+F | `SRC.INVENTORY.1`; blocks BE.9 | New inventory movement/cost layer likely / migration likely | Contract design parallel; costing decision gates completion | Consumption/return/transfer versions, Job linkage, costing layer/effective date and balance fixtures |
| 14 | Equipment utilization/cost; ABSENT → AVAILABLE | Asset/Fleet; A+B+C+E+F | `SRC.ASSET-FLEET.1`; blocks BE.9 | New asset/activity/cost persistence likely / migration likely | Parallel after owner resolution; Asset/Fleet and Finance checkpoint | Asset/utilization/period/cost identities, effective Branch, correction, digest and isolation tests |
| 15 | Fleet utilization/truck-day/cost; ABSENT → AVAILABLE | Asset/Fleet; A+B+C+D+E+F | `SRC.ASSET-FLEET.1`; blocks BE.9 | New fleet/activity/cost persistence likely / migration likely | Technical model parallel; truck-day definition gates completion | Vehicle/activity identity, approved truck-day rules, operating periods/cost, corrections and replay tests |
| 16 | Overhead/administrative pools; ABSENT → AVAILABLE | Finance/Accounting; A+B+C+D+E+F | ACC.1/ACC.2 then BE.POLICY.1; first blocks BE.12, not BE.9 unless ACC.2 declares it required | Accounting pool persistence likely / migration TBD after ACC.2 | Finance-serialized; BE.12 policy checkpoint | Pool identities/versions/effective periods, eligibility, currency/basis, correction and approval evidence |
| 17 | Customer/Service Location context; PARTIAL → AVAILABLE | Customers/Platform; A+C+F | `SRC.PLATFORM.1`; blocks BE.9 | Existing schema/version contract / migration possible | Parallel; Customer/Platform checkpoint | Source version, effective identity, correction history and explicit non-inferred Branch rules |
| 18 | Marketing attribution; PARTIAL → AVAILABLE | Marketing + Financial; A+B+C+D+E+F | `SRC.MARKETING.1`; blocks BE.9 for marketing-enabled scope; first numerical allocation BE.12 | Campaign/spend persistence likely / migration likely | Technical contract parallel; eligibility/driver decision gates BE.12 | Campaign/source versions, effective attribution, spend/pool linkage, corrections and approved driver evidence |
| 19 | Callback/warranty linkage; ABSENT → AVAILABLE | Jobs/Field quality; A+B+C+D+F | `SRC.JOB-QUALITY.1`; blocks BE.9 | Job relationship/history likely / migration likely | Taxonomy design may run parallel; owner decision before contract acceptance | Original/follow-up Job identity, responsibility/reason taxonomy, effective corrections and quality-cost fixtures |
| 20 | Business Event economic envelope; PARTIAL → AVAILABLE | Events + emitting source owners; A+C+F | `SRC.EVENTS.1`; first blocks BE.10 | Existing event extension possible / migration likely for stored version/scope constraints | Parallel; Events/source-owner checkpoint before BE.10 | Required scope/version schema, correction semantics, digest/replay and malformed-event fixtures |
| 21 | Company identity; PARTIAL → AVAILABLE | Platform; A+C+F | `SRC.PLATFORM.1`; blocks BE.9 | Existing schema extension possible / migration possible | Parallel; Platform checkpoint | Stable source version/effective status, correction and tenant-isolation fixtures |
| 22 | Branch identity; PARTIAL → AVAILABLE | Platform; A+C+F | `SRC.PLATFORM.1`; blocks BE.9 | Existing schema extension possible / migration possible | Parallel; Platform checkpoint | Stable source version/effective Company relation, correction and branch-isolation fixtures |
| 23 | Source-specific freshness policy; ABSENT → AVAILABLE | Source owners + Finance/Economics; A+C+D+E+F | `SRC.FRESHNESS.1`; first blocks BE.10 | Policy persistence TBD / migration TBD after contract | Per-source analysis parallel; Finance/Economics approval serialized | Versioned SLA, cutoff, outage/grace/escalation, close impact and stale-boundary fixtures |
| 24 | QuickBooks GL evidence; NOT APPLICABLE → NOT APPLICABLE | QuickBooks/Accounting; D+E+F, not an acquisition gap | ACC.1/ACC.2 and BE.14; first blocks BE.14 | Provider-neutral evidence exists; transport/persistence TBD later | Accounting-serialized; BE.14 checkpoint | Approved export grain, acknowledgement/rejection, exception owner, replay and exact reconciliation evidence |

## Dependency closure graph and critical paths

The graph is acyclic. Source tracks may proceed in parallel, but their accepted
outputs converge only at owner-governed checkpoints.

```text
current: BE.EVIDENCE.1 + BE.GAP.1
  |
  +-> source contracts/persistence/events (#3-15, #17-22)
  |      -> source-owner approval + immutable refs -------------------+
  |
  +-> ACC.1 -> ACC.2 -----------------------------------------------+|
  +-> RPT.1 -> IC.2 when RPT.1 requires it -------------------------||
  +-> owner decisions needed by enabled BE.9 scope -----------------||
  +-> collision analysis and explicit Start ------------------------||
                                                                    ||
                                                                    ++-> BE.9 READY
                                                                         -> BE.9 approval
                                                                         -> BE.VECTORS.1 evidence
                                                                         -> frozen source refs
                                                                         -> BE.10 READY
                                                                              -> BE.10 approval
                                                                              -> adapter boundary/persistence decision
                                                                              -> BE.11 READY
                                                                                   -> BE.11 approval
                                                                                   -> Finance pools/drivers + BE.POLICY.1
                                                                                   -> D1/D2/D5/D6/D7 as applicable
                                                                                   -> BE.12 READY
                                                                                        -> BE.12 approval
                                                                                        -> external Phase 8 selective-reuse mapping
                                                                                        -> one materialization authority
                                                                                        -> persistence compatibility
                                                                                        -> BE.13 READY
```

### Shortest path to BE.9 READY

1. PMO maps or adopts the required source capability milestones without code
   collisions or duplicate ownership.
2. Each enabled BE.9 source produces an approved immutable contract ref; facts
   outside the enabled scope remain explicitly missing and cannot be silently
   omitted from KPI completeness.
3. ACC.1 completes before ACC.2; RPT.1 completes with IC.2 when it requires it.
4. Required owner/Finance decisions close at their latest safe points below.
5. Economics performs source/Accounting/Reporting collision analysis and receives
   an explicit BE.9 Start. This plan alone does not satisfy any of those approvals.

### Shortest paths to BE.10–BE.13 READY

- **BE.10:** approved BE.9 mappings + frozen accepted source refs + approved
  fixture-data policy + BE.VECTORS.1 + source freshness rules needed by fixtures.
- **BE.11:** approved BE.10 conformance + exact adapter/source ownership +
  authorization and persistence decision + no source drift.
- **BE.12:** approved BE.11 facts + Finance-owned pools/drivers + BE.POLICY.1 +
  required labor/material/callback/Asset-Fleet decisions + durable allocation-run
  compatibility.
- **BE.13:** approved BE.12 + selective external Phase 8 reuse mapping + accepted
  equations/bases + one computation/materialization authority + persistence
  compatibility + non-double-counting/replay evidence.

## Owner and Finance decision register

Technical schemas, fixtures, lineage manifests, and collision analysis may
continue before a decision where noted, but no implementation may encode an
unapproved choice.

| Decision | First milestone blocked | Latest safe decision point | Work allowed beforehand |
| --- | --- | --- | --- |
| Payroll/paid-time authority and burden components | BE.9 | Before accepting `SRC.WORKFORCE.1` into BE.9 | Privacy model, envelope, version/correction and test design; no component/rate selection |
| Revenue timing for deposits, partial invoices, refunds and credits | BE.9 | Before accepting `SRC.FINANCIAL.1`/ACC.2 mapping | Status/correction schema and neutral fixtures; no recognition rule |
| Source-specific freshness SLAs | BE.10 | Before BE.10 stale/current conformance approval | Inventory source latency evidence and boundary test shapes; no default SLA |
| Overhead/marketing pool eligibility and allocation drivers | BE.12 | Before BE.POLICY.1 policy adoption/BE.12 Start | Pool/driver evidence collection and alternatives; no allocation execution |
| QuickBooks export grain, acknowledgement and exception ownership | BE.14 | Before BE.14 Start | Provider-neutral checksum/replay/rejection vectors; no transport/posting |
| Finance reporting materiality | BE.14/BE.15 | Before owner-facing exception/close presentation approval | Exact zero-tolerance reconciliation tests; materiality never changes integrity |
| Callback/warranty responsibility taxonomy | BE.9 | Before `SRC.JOB-QUALITY.1` contract acceptance | Link/version/correction schema and neutral reason placeholders; no blame inference |
| Truck-day/fleet operating definition | BE.9; allocation details BE.12 | Before `SRC.ASSET-FLEET.1` contract acceptance | Asset/activity identity, periods, correction and cost envelopes; no truck-day derivation |
| Inventory costing layer and consumption effective date | BE.9 | Before `SRC.INVENTORY.1` contract acceptance | Movement/return/transfer identity and balance fixtures; no costing choice |
| Marketing attribution/spend eligibility | BE.9 for source mapping; BE.12 for allocation | Before marketing source acceptance, and again before policy adoption | Campaign/version/spend lineage design; no causal attribution or pool choice |

Contribution margin needs no new Version 1 decision: BE.8 mandates the label
“V1 contribution margin (gross basis)” until Finance approves a later definition.

## Owner-grouped closure packages

- **Dispatch/Field:** #3, #10 and operational portions of #19.
- **Sales/Price Book:** #4 and #5.
- **Financial/Payments/Accounting:** #6, #7, #11 Finance components, #12 financial
  boundary, #16, #18 spend, #23 close impact and #24.
- **Workforce/payroll:** #8 identity coordination, #9 and #11 protected labor.
- **Inventory/Purchasing:** #12 and #13, preserving purchase versus consumption.
- **Asset/Fleet:** #14 and #15 under the resolved owner decision.
- **Jobs/quality:** #19 taxonomy and immutable linkage.
- **Marketing:** #18 attribution/campaign ownership.
- **Platform/Customers:** #8 identity coordination, #17, #21 and #22.
- **Events and every emitter:** #20, without treating an arbitrary event payload
  as source authority.
- **All source owners + Finance/Economics:** #23 source-specific SLA approval.

## Recommended five-day parallel closure plan

This is a scheduler recommendation, not an assignment. Laptop 1/PMO must first
map proposed capabilities to existing off-ref milestones and preserve the
authoritative scheduler.

| Capacity | Recommended bounded work | Dependencies and stop boundary | Durable evidence |
| --- | --- | --- | --- |
| OM1 Enterprise | Audit Financial/Estimate/Invoice/Payment and Platform identity contracts (#4, #6–8, #17, #21–22); draft neutral source-version/correction deltas | Existing frozen refs; stop before policy, persistence implementation or migration | Contract gap table, exact model paths, candidate source versions/corrections, collision report |
| OM2-A | Dispatch/Field and Jobs-quality contract analysis (#3, #10, #19) | Owner taxonomy may remain unresolved; stop before inferring work/travel or responsibility | Activity/linkage schema proposal, missing-event list, neutral fixtures |
| OM2-B | Price Book, Inventory, Purchasing and Asset/Fleet evidence analysis (#5, #12–15) | Asset/Fleet owner is resolved; costing/truck-day policies may remain open | Source ownership manifests, required tables/fields/events, migration-impact assessment |
| Migration | Map available legacy fields to proposed source identities without treating migration staging as operational authority | Frozen migration artifacts; stop at unverifiable lineage or inferred attribution | Field-level provenance matrix, unavailable/collision list, correction limitations |
| ECO | Execute BE.VECTORS.1 after explicit Start: provider-neutral reconciliation/replay vectors using AVAILABLE/PARTIAL/ABSENT cases | BE.EVIDENCE.1 complete; no policy selection or runtime | Golden vector contract supporting BE.10/BE.12 validation |
| Laptop 1 integration/PMO | Collision-check provisional codes, discover existing off-ref milestones, order ACC.1/ACC.2/RPT.1/IC.2 and source checkpoints, collect owner decisions | Authoritative scheduler controls Start/READY; no automatic assignments | Adopted milestone mapping, immutable refs, dependency/status ledger and owner-decision schedule |

Work on schemas, evidence manifests, test vectors, privacy boundaries, and
migration-impact analysis can proceed in parallel. Financial policy acceptance,
shared-contract integration, and migration execution remain serialized and
separately authorized.

## Validation and acceptance evidence

BE.GAP.1 is valid only when:

1. all 24 matrix facts appear once, with their current and target states;
2. every PARTIAL/ABSENT fact has an owner, exact gap categories, remediation,
   first blocker, persistence/migration assessment, checkpoint and evidence;
3. no proposed source code is represented as existing, approved, or READY;
4. ACC.1/ACC.2/RPT.1/conditional IC.2 and Economics milestones retain their
   established dependencies;
5. the graph closes without cycles;
6. Asset/Fleet, Workforce, source transaction and QuickBooks ownership match
   normative decisions;
7. owner/Finance decisions are separated from technical work;
8. Markdown links resolve and repository-relative evidence remains traceable; and
9. only this documentation file changes, with no runtime, persistence, migration,
   API, frontend, provider, Beacon, Luminary, Preview or Production action.

## Next ECO readiness

After BE.GAP.1 approval and push, `BE.VECTORS.1 — Economics Reconciliation and
Replay Test-Vector Contract` is the highest-value bounded TYPE A candidate. Its
dependency, approved BE.EVIDENCE.1, is complete. It can encode authoritative
BE.8 equations and exact tolerances plus AVAILABLE/PARTIAL/ABSENT scenarios
without choosing payroll, revenue, freshness, costing, truck-day, overhead,
marketing, QuickBooks or materiality policy. It still requires an explicit Start
and does not make BE.9, BE.10 or BE.12 READY.
