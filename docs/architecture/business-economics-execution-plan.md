# Business Economics Execution Plan

Status: BE.PLAN.1 — WAITING FOR OWNER REVIEW

Capacity: ECO — Business Economics

Classification: TYPE A — Documentation / planning
Starting ref: `origin/business-economics-foundation` at
`815954f827134fa21d003f1249f0117b4604454b`

## Purpose and governing contract

This plan gives ECO a dependency-ordered, owner-governed production queue after
roadmap BE.8. The normative Version 1.0 economic language, KPI definitions,
source and financial ownership, attribution rules, QuickBooks boundary, and
exact reconciliation tolerances remain exclusively defined by the
[Version 1.0 Business Economics Contract](business-economics-v1-contract.md).
This plan schedules work against that contract; it neither edits nor supersedes
it.

Roadmap **BE.8 — Define Version 1.0 economics contract** is distinct from the
separately completed **external Business Economics Phase 8 — Deterministic
Allocation & Profitability Engine Foundation**. References to “external Phase 8”
below mean commit `49261468f443273ffefcf78d200048dccf097e0f` and its
[architecture record](business-economics-phase8-allocation.md), not roadmap
BE.8. External Phase 8 is review evidence only: this plan does not approve,
accept, integrate, or rewrite it.

## Status and classification vocabulary

- **READY:** objective, dependencies, authority, branch/ref, validation, and
  owner Start evidence are complete. Only the owner may place a milestone here.
- **Dependency-eligible:** bounded work is defined, but explicit owner Start or
  another named readiness artifact is absent.
- **Blocked:** a named prerequisite or owner decision required for the milestone
  is missing.
- **Future:** a legitimate successor whose detailed execution boundary must be
  confirmed after predecessors produce evidence.
- **TYPE A:** documentation, contract, planning, or validation only.
- **TYPE B:** serialized shared-contract integration at the stated integration
  checkpoint.
- **TYPE C:** isolated implementation that does not modify a shared integration
  boundary until its checkpoint.

`PLANNED` and `dependency-eligible` never mean `READY`.

## Dependency-ordered ECO queue

The graph is acyclic and ordered as follows. Square brackets are external
dependencies owned outside ECO.

```text
BE.8 (approved normative contract)
  -> BE.PLAN.1 (this plan; waiting for owner review)

[ACC.1] -> [ACC.2] ------------------------------+
[RPT.1] -> [IC.2 when RPT.1 requires it] --------+-> BE.9
source-domain accepted contracts ----------------+

BE.9 -> BE.10 -> BE.11 -> BE.12 -> BE.13 -> BE.14 -> BE.15 -> BE.16
                                               \
                                                -> BE.17

external Phase 8 -> owner disposition only
                  -> optional evidence selected by owner for a later milestone
```

The `RPT.1`, `ACC.1`, `ACC.2`, and conditional `IC.2` labels come from the
approved scheduler brief. Their implementation scope is not defined in this
repository at the starting ref, so this plan treats their accepted contract and
completion evidence as opaque prerequisites and does not invent their work.

### Milestone catalog

#### BE.PLAN.1 — Deepen and Dependency-Order the Business Economics Execution Queue

- **Objective:** establish this durable queue, dependency map, external Phase 8
  dossier, decision routing, and handoff rules.
- **Dependency:** approved roadmap BE.8 contract at the recorded starting ref.
- **Source-domain contracts:** read-only review of BE.8 ownership declarations.
- **Accounting/Reporting contracts:** dependency names and ownership boundaries
  only; no integration.
- **Classification:** TYPE A.
- **Persistence/migration impact:** none.
- **Shared-contract impact:** none; BE.8 remains unchanged.
- **Parallel safety:** safe alongside PLAT.1 and PHONE-BUG.1; no shared runtime
  integration.
- **Integration checkpoint:** none; owner review is the gate.
- **Preview / Production:** neither required nor permitted; no Production impact.
- **Validation boundary:** single file, traceability, graph closure/cycles,
  unique codes, ownership/terminology/link checks, Markdown, diff and secret scan.
- **Owner checkpoint:** approve the plan after review; separate commit and push
  authority remains required.
- **READY evidence:** explicit Start plus the exact approved BE.8 ref (satisfied
  for execution of this milestone).
- **Stop condition:** `WAITING FOR OWNER REVIEW`; stop earlier if scope requires
  runtime, persistence, migration, or external Phase 8 integration.
- **Successor:** BE.9 only after its independent readiness evidence is complete.

#### BE.9 — Adopt Version 1.0 Source and Financial Reporting Contracts

- **Objective:** bind the normative BE.8 KPI inputs and ownership map to accepted
  Reporting and Accounting contracts without transferring source ownership.
- **Dependency:** BE.PLAN.1 approval; completed/accepted `RPT.1`; completed and
  accepted `ACC.2`, which depends on `ACC.1`; accepted `IC.2` evidence when
  required by `RPT.1`; accepted contracts from every in-scope source domain.
- **Source-domain contracts:** Jobs, Dispatch, Price Book, Estimates, Inventory,
  Purchasing, Invoicing, Payments, Workforce/payroll, Fleet, and organization
  identity, limited to the authoritative facts listed in BE.8.
- **Accounting/Reporting contracts:** `ACC.2` financial ownership and `RPT.1`
  KPI publication/source-of-truth contracts, plus their accepted predecessors.
- **Classification:** TYPE B — serialized integration.
- **Persistence/migration impact:** none authorized at readiness; stop if needed.
- **Shared-contract impact:** maps accepted external contracts to BE.8; any
  normative change requires a separate BE.8 amendment decision.
- **Parallel safety:** isolated analysis may run; contract integration is
  serialized at the applicable checkpoint after external refs are frozen.
- **Integration checkpoint:** IC.2 if required by RPT.1, then the separately
  approved BE.9 integration checkpoint.
- **Preview / Production:** no Preview by default; no Production mutation.
- **Validation boundary:** contract compatibility, ownership conflicts, KPI
  source closure, financial basis, QuickBooks boundary, and exact tolerances.
- **Owner checkpoint:** Economics/Finance/source-owner review and explicit Start.
- **READY evidence:** immutable refs and approval evidence for RPT.1, ACC.1,
  ACC.2, conditional IC.2, and each required source contract; collision review;
  approved execution boundary and validation commands.
- **Stop condition:** any missing/contradictory authority, normative BE.8 change,
  or required migration/runtime work outside approved scope.
- **Successor:** BE.10.

#### BE.10 — Validate Operational Fact Contract Conformance

- **Objective:** produce durable, provider-neutral conformance fixtures and
  validation evidence showing authoritative source facts can satisfy BE.8
  identity, version, effective-time, evidence, correction, Company, and Branch
  requirements.
- **Dependency:** approved BE.9 mappings.
- **Source-domain contracts:** all mapped operational contracts from BE.9.
- **Accounting/Reporting contracts:** accounting basis, currency, period cutoff,
  and reporting projection identity from accepted ACC.2/RPT.1 artifacts.
- **Classification:** TYPE A unless owner separately authorizes isolated test
  implementation as TYPE C.
- **Persistence/migration impact:** none.
- **Shared-contract impact:** validation artifacts only.
- **Parallel safety:** source-by-source validation may run in parallel after
  contract refs are frozen; findings integrate serially.
- **Integration checkpoint:** BE.10 source-conformance review.
- **Preview / Production:** neither; no Production impact.
- **Validation boundary:** complete/missing/corrected/duplicate/stale fixtures,
  Company and Branch isolation, deterministic evidence digests.
- **Owner checkpoint:** approve conformance findings and exception owners.
- **READY evidence:** BE.9 approval, frozen source contract refs, fixture-data
  policy, test boundary, and owners for every expected exception.
- **Stop condition:** a source cannot express a required BE.8 fact without
  changing ownership or persistence.
- **Successor:** BE.11.

#### BE.11 — Integrate Authoritative Operational Fact Acquisition

- **Objective:** connect approved read-only source contracts to Economics through
  the established ingestion/ledger boundary, using only measured facts and
  explicit missing states.
- **Dependency:** approved BE.10 conformance; owner disposition of any reusable
  external Phases 5–7 acquisition contracts.
- **Source-domain contracts:** BE.10-conformant Jobs, Dispatch, Price Book,
  Estimates, Inventory, Purchasing, Invoicing, Payments, Workforce, and Fleet.
- **Accounting/Reporting contracts:** accepted basis, cutoff, classification,
  and publication identity; no GL writes.
- **Classification:** TYPE B for shared source integration.
- **Persistence/migration impact:** not presumed. Existing Phase 4 persistence
  may be used only after compatibility review; a migration requires a new owner
  authorization.
- **Shared-contract impact:** adapter bindings only; source schemas remain owned
  by their domains.
- **Parallel safety:** adapter work can be isolated per source; final binding and
  shared-file changes are serialized.
- **Integration checkpoint:** BE.11 source-binding checkpoint.
- **Preview / Production:** Preview only if separately authorized for integrated
  evidence; no Production impact during milestone.
- **Validation boundary:** read-only behavior, replay/idempotency, correction
  lineage, missing/stale/conflict handling, scope isolation, regressions.
- **Owner checkpoint:** approve implementation boundary and any Preview use.
- **READY evidence:** BE.10 approval, exact source refs, adapter ownership,
  collision analysis, persistence decision, and validation environment.
- **Stop condition:** source mutation, inferred values, unapproved migration, or
  a source contract drift.
- **Successor:** BE.12.

#### BE.12 — Adopt Allocation Policy Governance and Cost Pools

- **Objective:** bind Finance-approved cost pools and drivers to versioned,
  deterministic Economics allocation policy contracts.
- **Dependency:** BE.11 authoritative inputs; decisions D1, D2, D5, D6, D7, and
  D8 below as applicable to each enabled policy.
- **Source-domain contracts:** paid/productive time, material consumption, fleet
  utilization/truck-days, Branch/Company dimensions, and marketing attribution.
- **Accounting/Reporting contracts:** Finance pool identity, classification,
  effective period, correction authority, and exact balancing requirements.
- **Classification:** TYPE B — Finance/Economics serialized integration.
- **Persistence/migration impact:** existing policy persistence must be assessed;
  no new migration is implied or authorized here.
- **Shared-contract impact:** approved policy registry and cost classification.
- **Parallel safety:** policy design may be isolated; activation and shared
  classifications are serialized.
- **Integration checkpoint:** BE.12 Economics/Finance policy checkpoint.
- **Preview / Production:** Preview only by separate authorization; Production
  activation is a later explicit decision.
- **Validation boundary:** effective versions, allowed drivers, circularity,
  Company/Branch isolation, exact balance, deterministic remainder, lineage.
- **Owner checkpoint:** Finance approves every pool/driver and effective date.
- **READY evidence:** authoritative pools/drivers, decisions for enabled cost
  classes, policy examples, approval identities, rollback/correction contract.
- **Stop condition:** an unowned pool, unsupported driver, cross-tenant spread,
  or unapproved persistence/migration need.
- **Successor:** BE.13.

#### BE.13 — Materialize Reconciled Profitability Measurements

- **Objective:** produce Job, Technician, Branch, and Company actual/estimated
  profitability from authoritative facts and approved allocations through the
  sole Economics materialization boundary.
- **Dependency:** BE.12; owner decision on reuse or rejection of external Phase 8
  components; required revenue and contribution-margin decisions.
- **Source-domain contracts:** BE.11 facts and BE.12 drivers/pools.
- **Accounting/Reporting contracts:** accepted revenue basis, classifications,
  period cutoff, and projection contract.
- **Classification:** TYPE B — serialized financial/KPI integration.
- **Persistence/migration impact:** use of existing measurement persistence
  requires compatibility evidence; any schema change requires separate approval.
- **Shared-contract impact:** Economics measurement/publication contract.
- **Parallel safety:** pure computation validation may be isolated; durable
  materialization and shared publication are serialized.
- **Integration checkpoint:** BE.13 financial integrity checkpoint.
- **Preview / Production:** isolated Preview may be proposed separately; no
  Production behavior without approval.
- **Validation boundary:** gross/net equations, actual/estimated separation,
  missing-state propagation, quality, evidence ordering, replay, scope isolation.
- **Owner checkpoint:** Economics/Finance approve representative measurements.
- **READY evidence:** BE.12 approval, external Phase 8 disposition, compatible
  persistence decision, accepted equations/bases, fixtures and rollback plan.
- **Stop condition:** unreconciled arithmetic, opaque lineage, guessed values,
  or a required schema change lacking authorization.
- **Successor:** BE.14.

#### BE.14 — Reconcile Economics with Accounting and QuickBooks Handoff

- **Objective:** validate represented source amounts, balanced exports,
  acknowledgements, corrections, replay, and exception ownership while
  QuickBooks remains the Version 1.0 general-ledger authority.
- **Dependency:** BE.13; decisions D9 and D10; accepted ACC.2 integration
  boundary and provider-neutral transport contract if transport is in scope.
- **Source-domain contracts:** invoices, payments, corrections, source evidence.
- **Accounting/Reporting contracts:** chart/dimension mapping, export grain,
  acknowledgement evidence, reporting materiality, exception ownership.
- **Classification:** TYPE B — serialized Accounting integration.
- **Persistence/migration impact:** reconciliation/export evidence compatibility
  review required; no migration presumed.
- **Shared-contract impact:** provider-neutral accounting handoff only.
- **Parallel safety:** fixture reconciliation can be isolated; accounting
  integration and exception workflow are serialized.
- **Integration checkpoint:** BE.14 Accounting/QuickBooks boundary checkpoint.
- **Preview / Production:** provider sandbox/Preview only with separate approval;
  no live QuickBooks or Production posting.
- **Validation boundary:** exact debit/credit and identity checks, checksums,
  duplicate/rejection/correction/replay, variance and residual classification.
- **Owner checkpoint:** Finance/Accounting approve handoff evidence and owners.
- **READY evidence:** BE.13 approval, D9/D10 decisions, test provider boundary,
  non-production credentials plan, acknowledgement fixtures, exception workflow.
- **Stop condition:** credentials/live posting, QuickBooks ownership erosion,
  unexplained residual, or materiality used to weaken exact reconciliation.
- **Successor:** BE.15.

#### BE.15 — Operationalize Close Readiness and Period Audit Evidence

- **Objective:** exercise source completeness, allocation balance, measurement
  completeness, staleness, correction, reconciliation, and immutable audit
  evidence as the gate to owner-controlled financial close.
- **Dependency:** BE.14 and source freshness decisions D3/D4.
- **Source-domain contracts:** cutoff-complete source manifests and correction
  evidence from every enabled domain.
- **Accounting/Reporting contracts:** close owner, period status, unresolved
  exception projection, materiality presentation.
- **Classification:** TYPE B — financial-close integration.
- **Persistence/migration impact:** existing Phase 3/4 close artifacts require
  compatibility review; no automatic migration.
- **Shared-contract impact:** close-readiness projection and audit evidence.
- **Parallel safety:** source completeness checks may run in parallel; close
  decision and package publication are serialized.
- **Integration checkpoint:** BE.15 close-readiness checkpoint.
- **Preview / Production:** populated non-production validation requires separate
  approval; no Production close.
- **Validation boundary:** open/closing/closed/reopened transitions, late facts,
  reversals, unresolved corrections, completeness, stale evidence, audit digest.
- **Owner checkpoint:** responsible owner approves close evidence; time alone
  never closes a period.
- **READY evidence:** BE.14 approval, D3/D4 values, period owner, complete source
  manifest, reopening scenarios, audit-package retention decision.
- **Stop condition:** incomplete evidence, unresolved exact reconciliation,
  missing owner, or silent modification of a closed period.
- **Successor:** BE.16 and BE.17.

#### BE.16 — Publish Reporting and Mission Control Economics Projections

- **Objective:** publish read-only reconciled profitability, confidence,
  completeness, freshness, lineage, integrity, readiness, and exception ownership
  through accepted Reporting and Mission Control presentation boundaries.
- **Dependency:** BE.15 and accepted RPT.1/MC presentation contracts.
- **Source-domain contracts:** none directly; consume Economics projections only.
- **Accounting/Reporting contracts:** RPT.1 projection identity/format and
  Mission Control status/owner-action boundary.
- **Classification:** TYPE B — shared presentation-contract integration.
- **Persistence/migration impact:** none presumed; stop if projection storage
  changes require persistence.
- **Shared-contract impact:** read-only projection schemas; no KPI recomputation.
- **Parallel safety:** consumer fixtures may be isolated; shared contract
  integration is serialized.
- **Integration checkpoint:** BE.16 Reporting/Mission Control checkpoint.
- **Preview / Production:** Preview only with separate authorization; Production
  publication requires a later launch decision.
- **Validation boundary:** authoritative identities, visible unknown/stale states,
  no raw compensation leakage, no consumer recomputation, tenant isolation.
- **Owner checkpoint:** Economics, Reporting, Mission Control, and permission
  owners approve projections.
- **READY evidence:** BE.15 approval, frozen consumer contracts, permission/data
  classification review, fixtures, collision plan, explicit Preview authority.
- **Stop condition:** dashboard/product expansion, source editing, KPI
  recomputation, unauthorized sensitive data, or persistence scope.
- **Successor:** later owner-approved operationalization; not automatic.

#### BE.17 — Contract the Beacon and Luminary Economics Consumption Boundary

- **Objective:** define read-only signal/explanation inputs from reconciled
  Economics without implementing Beacon, Luminary, AI, rules, recommendations,
  dashboards, or provider behavior.
- **Dependency:** BE.15; approved Beacon and Luminary ownership/authorization
  briefs; relevant decision closure only for fields exposed.
- **Source-domain contracts:** none directly; Economics projection lineage only.
- **Accounting/Reporting contracts:** integrity labels and financial-data access
  policy; no GL authority.
- **Classification:** TYPE A contract work, serialized if shared schemas change.
- **Persistence/migration impact:** none.
- **Shared-contract impact:** consumer boundary only.
- **Parallel safety:** draft analysis may be isolated; shared contract adoption
  waits for its integration checkpoint.
- **Integration checkpoint:** future owner-named Beacon/Luminary contract review.
- **Preview / Production:** neither; no Production impact.
- **Validation boundary:** measured/estimated/allocated/missing semantics,
  confidence/completeness/freshness, evidence citations, permission minimization,
  no consumer mutation or invented facts.
- **Owner checkpoint:** Economics plus Beacon/Luminary product owners approve.
- **READY evidence:** BE.15 approval, consumer ownership briefs, exact fields,
  authorization and retention policy, shared-contract collision analysis.
- **Stop condition:** AI/provider work, Beacon rules, recommendations, UI,
  runtime execution, or an attempt to weaken Economics authority.
- **Successor:** separately planned consumer milestones, never automatic.

## BE.9 readiness map and critical path

BE.9 is **blocked**, not READY. Its critical path is:

```text
ACC.1 accepted completion
  -> ACC.2 accepted financial-ownership/reporting-input contract ----+
                                                                   |
RPT.1 accepted KPI publication/source-of-truth contract             +-> BE.9 readiness review
  -> IC.2 accepted integration evidence, when RPT.1 requires it ----+

accepted source-domain contracts ----------------------------------+
BE.PLAN.1 owner approval and explicit BE.9 Start -------------------+
```

The exact missing evidence is:

1. immutable commit/ref, owner approval, and contract outputs for ACC.1;
2. immutable commit/ref, owner approval, and contract outputs for ACC.2 showing
   ACC.1 was its accepted predecessor;
3. immutable commit/ref, owner approval, and contract outputs for RPT.1;
4. IC.2 completion evidence if RPT.1 declares IC.2 mandatory;
5. accepted, versioned contracts for each source enabled in BE.9;
6. a collision analysis across those refs and the BE.8 normative contract;
7. an explicit owner Start, execution boundary, and validation plan for BE.9.

This repository contains no definitions for ACC.1, ACC.2, RPT.1, or IC.2 at the
recorded starting ref. Their names and dependency relationship are preserved from
the approved scheduler brief; their missing implementation scope is deliberately
not guessed here.

## External Phase 8 owner-review dossier

- **Exact evidence:** commit
  `49261468f443273ffefcf78d200048dccf097e0f`, subject
  `feat(economics): add deterministic allocation and profitability engines`, on
  the historical `business-economics-foundation` lineage; architecture record
  [Business Economics Phase 8](business-economics-phase8-allocation.md).
- **What it implements:** provider-neutral, in-memory deterministic allocation
  policies/engine, profitability engine, comparison and deterministic
  explanations, exact minor-unit reconciliation, evidence lineage, canonical
  ordering, SHA-256 digests, and UUIDv5 identities. It adds no persistence,
  migration, scheduler, API, frontend, AI, Beacon, Luminary, or Production
  behavior.
- **Relation to Phases 5–7:** it builds on Phase 5 immutable profitability
  contracts, Phase 6 deterministic computation principles, and Phase 7
  acquisition contracts. It does not complete source binding or durable runtime
  integration.
- **Difference from roadmap BE.8:** roadmap BE.8 is the normative Version 1.0
  documentation contract committed later at `815954f827134fa21d003f1249f0117b4604454b`.
  External Phase 8 is code/test/architecture foundation work and cannot satisfy
  the roadmap contract merely because the number matches.
- **Possible later reuse:** after owner and Finance review, pure allocation,
  reconciliation, deterministic identity, evidence-ordering, or explanation
  objects may supply evidence for BE.12 or BE.13. Reuse is not acceptance; every
  selected component must conform to BE.8 and then-current source/Accounting/
  Reporting contracts.
- **Integration risks:** parallel model vocabularies with Phase 1–4 persistence;
  duplicate computation authorities; mismatch between external policy types and
  Finance-approved pools; missing runtime/source bindings; stale or conflicting
  source semantics; shared-file collisions; treating deterministic explanations
  as Luminary; and accidental acceptance of tests as financial-policy approval.
- **Persistence/migration impact:** the commit itself has none. Integrating it
  with durable Phase 3/4 allocation and measurement records may expose schema or
  lineage incompatibilities; any migration requires a separately approved
  milestone.
- **Owner decisions required:** accept/reject/defer the package; select individual
  reusable components rather than blanket integration; name the target future
  milestone; require Economics/Finance review; resolve policy semantics; choose
  the single computation/materialization authority; and authorize any shared
  contract or persistence work. No decision is made by this plan.

## BE.8 unresolved decision routing

These identifiers route decisions without changing the normative unresolved list.
“Blocks now” means blocks BE.PLAN.1 or another currently executable planning
task; none does. A decision blocks only the milestone that first uses it.

| ID | Unresolved decision | First milestone requiring resolution | Blocks now? | Deferral rule |
| --- | --- | --- | --- | --- |
| D1 | Payroll/paid-time authority and burden components | BE.9 ownership mapping; final values required by BE.11/BE.12 | No | Keep labor cost missing until authoritative contracts and Finance approval exist. |
| D2 | Inventory costing and material-consumption effective date | BE.9 mapping; enforced by BE.10/BE.11 | No | Purchases remain unassigned and never become Job consumption by inference. |
| D3 | Revenue timing for deposits, partial invoices, refunds, and credits | BE.9 financial contract | No | Preserve separate accrual revenue and cash evidence; do not invent recognition. |
| D4 | Source-specific freshness SLAs | BE.10 fixtures; required operationally by BE.15 | No | Carry freshness as unapproved/unknown and do not label stale evidence current. |
| D5 | Callback/warranty responsibility taxonomy | BE.9 Jobs contract; required for BE.10/BE.11 classification | No | Retain linkage and unknown responsibility; do not allocate blame. |
| D6 | Truck-day definition and fleet ownership | BE.9 source map; required to enable truck policies in BE.12 | No | Disable truck-day allocation until Fleet and Finance approve driver/owner. |
| D7 | Overhead/marketing pool eligibility and allocation drivers | BE.12 | No | No pool is allocable merely because spend exists. |
| D8 | Contribution-margin variable-cost definition | BE.13 | No | Continue BE.8 label “V1 contribution margin (gross basis).” |
| D9 | QuickBooks export grain, acknowledgement evidence, and exception owner | BE.14 | No | An export is not posted or accepted without authoritative acknowledgement. |
| D10 | Finance reporting materiality thresholds, separate from exact reconciliation | BE.14 presentation and BE.15 close review | No | Exact identity/arithmetic tolerances remain zero regardless of materiality. |

## Cross-domain dependency and ownership map

| Domain | Economics dependency | Required contract evidence | Ownership preserved / boundary |
| --- | --- | --- | --- |
| Jobs | stable Job identity, lifecycle, callback/warranty linkage, Company/Branch | versions, effective status/linkage, correction evidence | Jobs owns mutation/completion; Economics consumes scope context. |
| Dispatch | actual appointments, assignments, trips, productive activity context | actual intervals, resource and trip identity, correction lineage | Dispatch owns schedule, assignment, routing. |
| Price Book | historical priced item/version and expected cost/revenue lineage | immutable version/effective date and Estimate linkage | Sales/catalog owns items and prices. |
| Estimates | accepted option/version and conversion lineage | acceptance, version, Job/Price Book links, correction state | Sales owns estimate lifecycle; estimates never become actuals. |
| Inventory | Job consumption, returns, transfers, costing layer | quantity/cost layer, effective time, Job link, reversals | Inventory/Field owns stock and consumption transactions. |
| Purchasing | vendor purchases and unassigned spend | purchase identity, amount, currency, card/vendor, corrections | Procurement/Financial owns purchase lifecycle; purchase is not inferred consumption. |
| Invoicing | issued/posted invoice revenue, adjustments, credits | authoritative status, line/total, basis, effective time, reversals | Financial/Invoicing owns invoice and tax lifecycle. |
| Payments | successful settlement, refunds, reversals | processor/source identity, status, amount, invoice link, corrections | Financial/Payments owns collections; payment does not duplicate revenue. |
| Accounting | classifications, pools, period/close controls, export/reconciliation ownership | ACC.1/ACC.2 accepted contracts and approvals | Accounting/Finance owns accounting policy and official close controls. |
| Reporting | KPI projection/source-of-truth and presentation contract | RPT.1 and conditional IC.2 accepted evidence | Reporting presents authoritative projections; it does not recompute KPIs. |
| QuickBooks | GL/chart/AP/payroll/tax/statements and posting acknowledgement | mappings, accepted posting/acknowledgement, exceptions | QuickBooks remains Version 1.0 GL authority; Economics never edits it. |
| Beacon | later read-only reconciled signal inputs | separately approved consumer contract and permissions | Beacon owns rules/signals; Economics does not implement or trigger them here. |
| Luminary | later cited explanations/recommendations from measured Economics | separately approved consumer contract, authorization, retention | Luminary consumes facts; it cannot alter values, evidence, or confidence. |

Company and Branch identity remain Platform-owned dimensions. Workforce/payroll,
Fleet, Marketing, Customer, and equipment authorities must also provide their
respective contracts before the related inputs or allocation drivers can be
enabled. Business Economics consumes authoritative facts, owns versioned
economic measurements and approved allocation lineage, and never takes ownership
of operational transactions or the general ledger.

## READY assessment and continuous queue behavior

- **BE.PLAN.1:** implementation is complete only when its validation below
  passes; it then stops at `WAITING FOR OWNER REVIEW`, not READY for another
  action.
- **BE.9:** blocked by the critical path above.
- **BE.10–BE.17:** blocked by their immediate predecessor and named evidence.
- **External Phase 8 disposition:** eligible for owner review, but it is not an
  ECO implementation milestone and is not approved or READY.

Therefore **no subsequent Economics implementation milestone can become READY
now** from evidence present at this ref. ECO can prepare bounded review material
only when explicitly started; it may not bypass missing dependencies by relabeling
planning as implementation.

After each approved milestone, ECO follows:

```text
IMPLEMENT
  -> VALIDATE
  -> WAITING FOR OWNER REVIEW
  -> OWNER APPROVAL
  -> separately authorized COMMIT
  -> separately authorized PUSH
  -> scheduler re-evaluates dependency evidence
  -> explicit Start for the NEXT READY MILESTONE
```

Routine implementation, tests, and repair inside an explicitly started milestone
do not require intermediate owner approval. Owner approval of one milestone does
not approve its successor. ECO must not move automatically into a `PLANNED`,
`future`, `dependency-eligible`, or `blocked` milestone. Every Start records the
authoritative ref, isolated workspace, scope, classification, migration boundary,
integration checkpoint, validation, and stop condition.

## Plan validation obligations

BE.PLAN.1 is complete for review only when validation confirms:

1. this is the sole changed file;
2. BE.8 is linked and remains normative/unmodified;
3. every dependency resolves to an earlier queue node or a named external gate;
4. the milestone graph has no cycles and every milestone code is unique;
5. roadmap BE.8 and external Phase 8 remain unambiguously distinct;
6. cross-domain transaction, financial, Reporting, QuickBooks, Beacon, and
   Luminary ownership is consistent with BE.8;
7. exact reconciliation is never weakened by reporting materiality;
8. relative links resolve, Markdown structure is valid, and terminology is
   internally consistent;
9. `git diff --check` and a focused credential/private-key scan pass; and
10. the worktree remains unstaged and no runtime, migration, API, frontend,
    provider, Preview, Production, or external Phase 8 integration change exists.

## References

- [Version 1.0 Business Economics Contract](business-economics-v1-contract.md)
- [Business Economics foundation](business-economics-foundation.md)
- [Phase 5 operational-source contract](business-economics-phase5-contract.md)
- [Phase 6 deterministic computation](business-economics-phase6-computation.md)
- [Phase 7 acquisition boundary](business-economics-phase7-acquisition.md)
- [External Phase 8 allocation foundation](business-economics-phase8-allocation.md)
- [Architecture module ownership](module-map.md)
- [Version 1.0 release plan](../product/release-plan.md)
- [Launch readiness checklist](../product/launch-checklist.md)
- [Architecture roadmap](roadmap.md)
