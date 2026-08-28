# ECO.FINANCE.DECISION.PACKET.1 — Business Economics Finance policy decisions

Status: **OWNER/FINANCE DECISION REQUIRED — NO POLICY SELECTED**

Contract version: `eco.finance.decision.packet.v1`

Evidence baseline: `d63c6f28e926a84cd6322414a5f1591087df69d9`

## What this packet does

ACP can now preserve evidence, classify readiness and conflicts, seal a replayable
measurement package, and reject a package that is not fit for calculation. It cannot
legitimately calculate contribution or profitability until Finance and the owner make
the decisions below. This packet explains the choices; it makes none of them.

Every future decision must be versioned, effective-dated, attributable to its
approver, and retained with historical packages. A later policy change must create a
new version. It must not rewrite a prior measurement package or source assertion.

## Authority inventory

| Authority class | What exists now | What it can establish | What it cannot establish without a decision or new accepted contract |
|---|---|---|---|
| Native ACP operational facts | Accepted Job identity, Branch, lifecycle status, exact `job_type_code`, and inventory operational records | Explicit Job context and explicit service category where populated | Revenue recognition, paid labor cost, material cost consumed by a Job, or Finance acceptance |
| ACP Accounting posting facts | Immutable accepted `PostingFact`, posting receipts/rules, native GL lines and reconciled report manifests | That an accepted event posted under a versioned rule; ledger/report provenance | That a posting component is earned revenue or an economic cost attributable to a Job |
| ACP financial reporting | Trial Balance, Balance Sheet, Income Statement and General Ledger contracts with scope, basis, cutoff, checksum and quality | Ledger totals and report-quality evidence for Company/Branch/period | Job contribution, allocation policy, or operational attribution |
| Public Migration contracts | Provider-neutral migrated Job/Estimate/Invoice/Payment identities and deterministic reconciliation surfaces | Public identity/provenance after Migration accepts a record | Raw-source authority, Finance acceptance, or missing Job/payment/material links |
| HCP public/source evidence | Provider-neutral public assertions may retain HCP authority, confidence and digests | What HCP/public Migration reported | Accepted economic truth unless a later public acceptance contract explicitly says so |
| QBO source evidence | `quickbooks_online_source_reported`, immutable envelopes, relationships and digests | Exactly what QBO reported | Enterprise-accepted accounting truth or source precedence |

Traceability: `PostingFact` in `backend/app/accounting/posting/contracts.py`;
`ReportManifest`, `ReportQuality`, and `GeneralLedgerRow` in
`backend/app/financial_reporting/contracts.py`; `JobDetail` in
`backend/app/jobs/query_types.py`; `PublicOperationalEvidence` and QBO adapters in
`backend/app/business_economics/source_adapters.py` and
`measurement_adapters.py`; measurement, package, and admission contracts in
`measurement_contract.py`, `measurement_package.py`, and
`measurement_admission.py`.

## Decision summary

| ID | Decision | First job contribution | Service-line contribution | Gross margin | Operating profitability | Cash/settlement economics | May defer? |
|---|---|---:|---:|---:|---:|---:|---|
| `ECO-FIN-001` | Revenue recognition | Yes | Yes | Yes | Yes | Depends | No for any revenue-based result |
| `ECO-FIN-002` | Payment/settlement acceptance | Depends | Depends | No for accrual view | Depends | Yes | Yes unless first result is cash-based |
| `ECO-FIN-003` | Direct labor measurement | Yes when labor is in scope | Yes | Yes | Yes | No | No for labor-inclusive result |
| `ECO-FIN-004` | Labor burden | Must explicitly include or exclude | Same | Depends on definition | Yes if labor burden is operating cost | No | May defer only with an explicitly unburdened metric |
| `ECO-FIN-005` | Direct material costing | Yes when materials exist | Yes | Yes | Yes | No | No for material-bearing Jobs |
| `ECO-FIN-006` | Other attributable direct costs | Must define inclusion | Yes | Depends on definition | Yes | Depends | May defer only by explicitly excluding named classes |
| `ECO-FIN-007` | Overhead pools | No for direct contribution | No for direct contribution | Usually no | Yes | No | Yes until overhead-loaded profitability |
| `ECO-FIN-008` | Overhead allocation | No for direct contribution | No for direct contribution | Usually no | Yes | No | Yes until overhead-loaded profitability |
| `ECO-FIN-009` | Reconciliation/source precedence | Yes when assertions disagree | Yes | Yes | Yes | Yes | No when relevant conflict exists |
| `ECO-FIN-010` | Monetary materiality | No if every variance remains explicit | No | No | No | No | Yes; never converts missing to zero |
| `ECO-FIN-011` | Accounting reconciliation admission quality | Yes for ledger-derived inputs | Yes | Yes | Yes | Depends | No when Accounting evidence participates |
| `ECO-FIN-012` | Job lifecycle/cutoff eligibility | Yes | Yes | Yes | Yes | Depends | No for period or Job cohort results |

“Depends” means the requirement follows from the metric definition selected in another
decision. It does not imply a default.

## `ECO-FIN-001` — Revenue recognition

**Question:** What event and evidence make revenue eligible as earned value for Job
economics, and on what effective date?

**Why required:** `MeasurementComponent.REVENUE_EARNED_VALUE` requires a legitimate
value and `finance_accepted_revenue_basis`. QBO invoices remain source-reported;
posting and financial reports do not themselves determine Job-level earned value.

**Available:** ACP Job lifecycle; migrated/public invoice identities; QBO invoice and
credit-memo assertions; accepted postings and GL/report provenance. **Missing:** an
approved recognition event, treatment of deposits/credits/cancellations/change work,
Job attribution acceptance, and effective-date rules.

| Alternative | Consequence/tradeoff |
|---|---|
| Invoice-issued basis | Reproducible and close to billing; may count work before it is earned and depends on accepted invoice-to-Job identity. |
| Job-completion basis | Ties earned value to operational completion; requires rules for partial work, multi-visit Jobs, cancellations and post-completion adjustments. |
| Milestone/progress basis | Represents partially earned work; requires accepted milestones or progress evidence that does not currently exist as a Finance contract. |
| Cash-received basis | Simple settlement view; measures cash realization rather than earned operational contribution and requires `ECO-FIN-002`. |

Reversible only prospectively through a new effective-dated version; historical
packages remain reproducible. Unlocks revenue input, job/service-line contribution,
gross margin and operating profitability. Cannot remain deferred for a revenue-based
calculation.

## `ECO-FIN-002` — Payment acceptance and settlement authority

**Question:** Which payment evidence proves cash settlement, and when is a payment
accepted and applied to an invoice or Job?

**Why required:** `SETTLEMENT` cannot infer application. Known stale QBO AR makes
invoice balance an unsafe substitute for accepted payment evidence.

**Available:** migrated/public Payment identities, QBO Payment source assertions and
links where reported, Accounting postings/deposits, and GL provenance. **Missing:** an
accepted cross-source payment/application contract, unapplied-payment policy, refund/
chargeback treatment, and conflict resolution.

| Alternative | Consequence/tradeoff |
|---|---|
| Accepted Accounting cash posting | Strong ledger provenance; still needs authoritative invoice/Job application. |
| Accepted operational payment application | Strong Job/invoice linkage; needs reconciliation to deposited/posted cash. |
| Dual-evidence requirement | Highest reconciliation confidence; more records remain partial until both sources tie. |
| Source-specific accepted assertion | Faster availability; requires `ECO-FIN-009` and explicit acceptance criteria for that source. |

Required for cash/settlement economics and any cash-based contribution definition.
Safely deferrable for a strictly accrual/earned-value contribution result if settlement
is clearly excluded.

## `ECO-FIN-003` — Direct labor measurement

**Question:** Which time is attributable productive Job labor, and which unit/value is
accepted for measurement?

**Why required:** Current field/appointment evidence establishes assignments and work
state, not accepted paid time or labor cost. Missing time cannot be zero.

**Available:** Job/appointment/technician operational identities and field evidence.
**Missing:** accepted clock/time intervals, correction/approval workflow, employee/
contractor cost evidence, paid-versus-productive distinction, and authoritative
Job-to-time linkage suitable for Economics.

| Alternative | Consequence/tradeoff |
|---|---|
| Approved actual Job time | Most measured operational basis; requires reliable clocking, approvals and corrections. |
| Appointment duration | Available operational proxy; scheduled or elapsed duration may not equal productive labor and must be labeled as such. |
| Payroll-paid hours allocated by accepted Job time | Aligns total paid labor; requires payroll evidence and an allocation policy. |
| Standard labor units | Stable for comparison; normative rather than actual and requires an approved standard catalog. |

Required for labor-inclusive job, service-line, gross-margin, and operating results.
Deferrable only for a result explicitly excluding labor, which must not be described as
complete contribution.

## `ECO-FIN-004` — Labor burden methodology

**Question:** Which employer labor costs supplement direct wage cost, and how are they
applied?

**Available:** no accepted burden policy; future Accounting/payroll evidence may
support pools. **Missing:** approved included costs, rates or actual-cost method,
effective periods, employee classes, treatment of overtime/nonproductive time, and
true-up rules.

| Alternative | Consequence/tradeoff |
|---|---|
| Actual employer cost by worker/period | Highest specificity; payroll/privacy access and timing complexity. |
| Versioned burden rate by worker class | Reproducible and operational; requires periodic approval and variance review. |
| Single company burden rate | Simple; obscures worker/class differences. |
| Exclude burden from “direct contribution” | Permits an explicitly unburdened result; cannot be represented as fully loaded labor economics. |

Needed for burdened labor, many gross-margin definitions, and operating profitability.
May be deferred for a clearly labeled unburdened direct-contribution metric.

## `ECO-FIN-005` — Direct material costing

**Question:** Which issued/consumed materials belong to a Job and at what accepted
cost?

**Available:** inventory movements, reservations/issues, optional unit cost and
valuation-method fields; QBO procurement source assertions. **Missing:** accepted
Job-material economic linkage, returns/waste treatment, authoritative valuation policy,
and reconciliation between procurement, inventory and Accounting.

| Alternative | Consequence/tradeoff |
|---|---|
| Actual accepted issue-layer cost | High fidelity; requires authoritative cost layers and Job issues. |
| Moving weighted average | Stable and operational; changes with receipts and needs versioned replay rules. |
| Standard cost with variance | Predictable comparisons; requires approved standards and separate variance handling. |
| Specific identification | Precise for unique items; operationally expensive for ordinary stock. |

Required for any material-bearing Job/service line and gross/operating result. A Job
with no evidence of material consumption remains unknown, not zero.

## `ECO-FIN-006` — Other attributable direct costs

**Question:** Which non-labor/non-material costs may be directly attributed to a Job,
and what evidence establishes that attribution?

**Available:** source-reported purchases, Accounting postings, and some operational
identities. **Missing:** accepted categories and links for subcontractors, permits,
rental equipment, disposal, mileage/truck, fees and similar costs.

| Alternative | Consequence/tradeoff |
|---|---|
| Enumerated directly attributable categories | Auditable; new categories require policy updates. |
| Evidence-by-evidence Finance approval | Conservative; operationally slower. |
| Exclude all until accepted category contracts exist | Avoids fabricated attribution; understates direct cost and must be labeled incomplete. |

The included/excluded list must be explicit. It can be expanded prospectively by
version. Required for a complete direct-contribution definition; individual categories
may remain deferred with visible limitations.

## `ECO-FIN-007` — Overhead pool definitions

**Question:** Which accepted Accounting costs belong to each overhead pool, for what
period and organizational scope?

**Available:** accepted GL/report classifications and Company/Branch scope. **Missing:**
approved pool membership, exclusions, shared-company treatment, owner compensation,
one-time items, and period/version rules.

| Alternative | Consequence/tradeoff |
|---|---|
| One company overhead pool | Simple; weak causal visibility. |
| Branch pools plus company-shared pool | Better branch economics; needs shared-cost rules. |
| Functional pools (dispatch, fleet, facilities, administration) | More explainable drivers; higher governance effort. |
| No overhead in direct contribution | Preserves a direct metric; does not produce operating profitability. |

Deferrable for job/service-line direct contribution and some gross-margin views.
Required before overhead-loaded or company operating profitability.

## `ECO-FIN-008` — Overhead allocation methodology

**Question:** How is each approved overhead pool allocated, if at all, to Jobs,
service lines, Branches or periods?

**Available:** potential operational drivers such as Job count, labor time and revenue,
subject to their own readiness. **Missing:** approved driver per pool, denominator,
capacity/idle treatment, rounding, true-up and effective-date rules.

| Alternative | Consequence/tradeoff |
|---|---|
| Revenue-proportional | Simple; can make high-price Jobs absorb costs unrelated to resource use. |
| Direct-labor-hour driver | Operationally intuitive for labor-driven pools; blocked by labor readiness. |
| Job-count driver | Simple; treats unlike Jobs alike. |
| Pool-specific causal drivers | Most explainable; most policy and evidence maintenance. |
| Keep overhead unallocated at Company/Branch | Fully auditable totals; no overhead-loaded Job profitability. |

Required only after pool definitions and only for loaded profitability. Policy changes
must create new versions; never rewrite prior packages.

## `ECO-FIN-009` — Reconciliation and source precedence

**Question:** When accepted or source-reported assertions disagree, what evidence may
resolve the conflict, and who authorizes the accepted assertion?

**Available:** Economics preserves all assertions and emits `CONFLICTING`; Accounting
reports expose quality and provenance; source packages retain digests. **Missing:** an
approved precedence/acceptance matrix and exception authorization workflow.

| Alternative | Consequence/tradeoff |
|---|---|
| Require explicit Finance resolution per conflict | Strong audit trail; slows admission. |
| Versioned precedence by fact type | Deterministic at scale; must be justified separately for revenue, settlement, cost and identity. |
| Require two-source reconciliation | High confidence; may leave legitimate single-source facts unusable. |
| Preserve conflict and exclude the component | Safest without policy; blocks or limits measurement. |

No general source winner is implied. Required whenever relevant assertions conflict;
otherwise it may remain dormant. Corrections must be append-only accepted evidence.

## `ECO-FIN-010` — Monetary materiality thresholds

**Question:** May a variance be considered immaterial for review/presentation, and if
so at what scope and threshold?

**Available:** exact digests, report variance, blockers and reconciliation exceptions.
**Missing:** approved thresholds, scope, escalation and aggregation rules.

| Alternative | Consequence/tradeoff |
|---|---|
| Zero tolerance | Maximum exactness; greater review volume. |
| Absolute amount by scope | Easy to apply; scale-insensitive. |
| Percentage plus absolute floor | Scales better; more policy complexity. |
| Threshold for presentation only | Preserves exact calculation/reconciliation while reducing display noise. |

Safely deferrable: exact exceptions remain explicit. A threshold must never convert
missing evidence to zero or resolve a source conflict.

## `ECO-FIN-011` — Accounting reconciliation admission quality

**Question:** What Accounting report-quality state is required before ledger-derived
evidence may enter Economics?

**Available:** `ReportQuality` completeness, freshness, reconciliation, integrity,
review and variance; report manifests/checksums; posting receipts. **Missing:** the
Finance-approved minimum combination for economic admission and handling of reopened
periods or later corrections.

| Alternative | Consequence/tradeoff |
|---|---|
| Require complete/current/reconciled/integrity-passed/reviewed | Strongest gate; delays timely measurement. |
| Permit unreviewed but otherwise reconciled evidence | Faster provisional measurement; results require explicit provisional status. |
| Permit stale evidence within an approved age | Operational continuity; increases change/replay frequency. |
| Require closed-period evidence only | Stable history; unavailable for current operations. |

Required whenever Accounting-derived amounts participate. May be deferred for purely
operational readiness analysis, not for accepted financial measurement.

## `ECO-FIN-012` — Job lifecycle and cutoff eligibility

**Question:** Which Job states and dates make a Job eligible for a period measurement?

**Available:** accepted Job status and lifecycle timestamps; Accounting effective
dates and period/cutoff evidence. **Missing:** treatment of drafts, in-progress,
paused, cancelled, reopened and multi-period Jobs; late evidence and cutoff rules.

| Alternative | Consequence/tradeoff |
|---|---|
| Completed Jobs only | Stable cohorts; delays visibility and requires completion semantics. |
| In-progress provisional measurement | Timely; needs progress/revenue/cost rules and later restatement. |
| Event-effective period attribution | Reproducible by component date; one Job spans periods. |
| Job-close cohort attribution | Simple Job result; period statements and operational timing may differ. |

Required for the first Job result and every period/service-line rollup. Versioned
cutoff changes must not rewrite historical packages.

## Dependency map

```text
ECO-FIN-012 Job/cutoff eligibility
  → JOB_CONTEXT eligibility
  → sealed package scope/cohort
  → admission scope passes

ECO-FIN-001 revenue recognition + ECO-FIN-011 Accounting quality
  → REVENUE_EARNED_VALUE accepted input
  → revenue blocker removed
  → package may become MEASURABLE
  → admission may pass

ECO-FIN-003 direct labor + (ECO-FIN-004 burden if included)
  → DIRECT_LABOR / LABOR_BURDEN inputs
  → labor blockers removed
  → labor-inclusive contribution becomes possible

ECO-FIN-005 material costing
  → DIRECT_MATERIAL / MATERIAL_COSTING inputs
  → material blockers removed
  → material-bearing Job contribution becomes possible

ECO-FIN-006 other direct cost inclusion
  → OTHER_DIRECT_COST input or explicit versioned exclusion
  → direct-cost scope becomes complete and explainable

ECO-FIN-009 source reconciliation
  → conflicting relevant component resolved by new accepted evidence
  → package no longer CONFLICTING
  → admission may pass

ECO-FIN-002 settlement acceptance
  → SETTLEMENT accepted input
  → cash blocker removed
  → cash/settlement economics becomes possible

ECO-FIN-007 pools + ECO-FIN-008 allocation
  → OVERHEAD_ALLOCATION prerequisite resolved
  → loaded package admitted
  → overhead-loaded / operating profitability becomes possible
```

The admission contract still requires every packaged input to be accepted and its
authority explicitly permitted. A Finance decision creates policy authority; it does
not by itself manufacture missing source evidence.

## Minimum policy set for the first legitimate Job contribution

Before any first calculation, the owner/Finance must define the metric precisely.
For a direct, accrual-style Job contribution that includes labor and materials but no
allocated overhead, the minimum decisions are:

1. `ECO-FIN-012` — eligible Job states and cutoff.
2. `ECO-FIN-001` — accepted earned-value event and date.
3. `ECO-FIN-003` — accepted direct Job labor evidence.
4. `ECO-FIN-004` — either an approved burden method **or an explicit decision that the
   first metric is unburdened**.
5. `ECO-FIN-005` — accepted Job material linkage and costing for material-bearing Jobs.
6. `ECO-FIN-006` — explicit included/excluded direct-cost categories.
7. `ECO-FIN-009` — conflict resolution authority whenever relevant conflicts exist.
8. `ECO-FIN-011` — Accounting evidence quality required for any ledger-derived input.

This list does not select accrual-style direct contribution; it shows the minimum if
that is the metric Finance chooses. If Finance chooses a cash-based metric,
`ECO-FIN-002` is also mandatory. A Job lacking required evidence remains not
measurable even after every policy decision is made.

## Policies that may remain deferred

- `ECO-FIN-002` may wait if the approved first metric excludes settlement and is not
  described as cash contribution.
- `ECO-FIN-007` and `ECO-FIN-008` may wait until overhead-loaded Job/service-line or
  company operating profitability.
- `ECO-FIN-010` may wait indefinitely while exact exceptions remain visible.
- Service-line rollups may wait until explicit service classification coverage and
  aggregation scope are accepted; no description-text classification is permitted.
- Profitability/margin targets, rankings, advanced leakage intelligence, pricing and
  forecasting may wait until measured historical economics is accepted.

## External evidence gates

- Intuit Production credentials and owner-authorized real QBO acquisition.
- Accepted HCP economic handoffs produced through public Migration boundaries.
- Completion of relevant Migration reconciliation and exception disposition.
- Accepted labor, material, payment and other-cost contracts that do not yet exist.

These gates remain `UNKNOWN`/`PARTIAL` as appropriate. This packet contains no
substitute facts.

## Owner/Finance response requested

For each decision ID, record the selected alternative or an explicitly authored
alternative, effective date, Company/Branch scope, approver, policy version, evidence
required for acceptance, correction/replay treatment, and whether the decision is
approved now or deferred. Approval must be explicit; silence means unresolved.

Until that response is accepted and implemented as versioned policy evidence:

- `BANK.ECO.001` remains `BLOCKED_FINANCE_DECISION`.
- measurement packages retain unresolved prerequisites;
- calculation admission remains fail-closed; and
- no contribution or profitability calculation is authorized.
