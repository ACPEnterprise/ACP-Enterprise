# All County Finance Policy v1 — owner decision record

Status: **OWNER SELECTED — NOT YET IMPLEMENTED**

Decision-record version: `all-county.finance-policy-decisions.v1`

Owner decision date: 2026-08-27

This record captures Company-specific owner intent for All County's first Business
Economics metric. It is not a universal ACP Enterprise policy, executable policy
configuration, evidence acceptance event, or authorization to calculate economics.

## Commercial product boundary

ACP Enterprise does not currently have a generic Finance/Economics policy authority
that combines all of the following:

- immutable Company identity and optional Branch applicability;
- stable policy-family identity and Company-local version;
- effective-from and optional effective-to dates without overlap;
- draft, approved, superseded and retired lifecycle;
- explicit approver, approval time and canonical decision digest;
- structured alternatives and parameters by policy family;
- referenced authoritative evidence/acceptance contracts;
- append-only audit and Business Event history;
- deterministic effective-date selection and replay;
- historical package binding to the exact policy version used;
- prospective replacement without mutation of prior facts, packages or results; and
- independent configurations for different ACP customers.

Existing posting rules, account mappings, tax policies and payment policy fields are
domain-specific mechanisms. They are useful patterns but are not a generic commercial
Finance/Economics policy authority. `PolicyPrerequisite` in Business Economics records
whether a prerequisite is resolved; it does not own approval, effective dating,
persistence or Company configuration.

Therefore these selections must not be encoded until a separately approved generic
policy architecture exists. That architecture must model policy definition separately
from Company policy versions and from immutable evidence acceptance. It must reject
overlapping active versions, cross-Company references, missing approvals, retrospective
mutation and use outside the effective period.

## Initial metric identity

Display name:

**DIRECT JOB CONTRIBUTION — ACCRUAL BASIS — BEFORE OVERHEAD**

Conceptual definition only:

```text
accepted recognized Job revenue
− approved actual direct Job labor
− approved standard labor burden by worker class
− actual accepted Job-linked material cost
− accepted specifically attributable direct Job costs
= Direct Job Contribution — Accrual Basis — Before Overhead
```

This metric must never be labeled net profit, fully loaded profit, technician
profitability or company profitability. No term in this definition supplies a missing
value or authorizes a calculation today.

## Selected All County policy intent

### `ECO-FIN-012` — Completed Jobs only

Initial measurement eligibility requires authoritative `JobStatus.COMPLETED`. Future
provisional/in-progress policy remains a supported architectural possibility but is
not selected and lacks accepted progress evidence.

Implementation must define effective cutoff, reopened/recompleted Jobs, multi-period
Jobs, cancellations and late evidence. Completion does not by itself recognize
revenue or accept cost.

### `ECO-FIN-001` — Accepted value at Job completion

Recognized Job revenue is intended to be accepted earned Job value at authoritative
completion. Invoice issuance alone is insufficient. QBO remains
`quickbooks_online_source_reported`.

The future Company policy must explicitly cover cancellations, partial work,
multi-visit Jobs, credits, adjustments, reopening/recompletion and later append-only
corrections. The recognized value remains blocked until an accepted revenue-value and
Job-identity contract exists.

### `ECO-FIN-003` — Approved actual Job time

Direct labor requires authoritative actual Job participation/time, approval and
correction evidence. Scheduled duration, elapsed appointment time, estimated time,
standard labor and guessed payroll allocations are prohibited substitutes.

This decision remains evidence-blocked. Missing labor keeps the component incomplete;
it is never zero.

### `ECO-FIN-004` — Approved standard burden by worker class

The initial Job metric may use Company-approved, versioned, effective-dated standard
burden by worker class. No class or rate currently exists. Future policy must define
class identity, rate/unit, effective period, approval, correction and true-up behavior.

This selection is specific to initial Job contribution. It does not define employee or
technician profitability cost.

### `ECO-FIN-005` — Actual accepted inventory-issue cost layers linked to the Job

Direct material requires authoritative Job-consumption linkage plus accepted actual
cost-layer evidence. AMEX/QBO purchase proximity, customer similarity, date proximity,
technician inference and estimated usage are prohibited substitutes.

The evidence contract remains absent. Missing material evidence remains missing.

### `ECO-FIN-006` — Owner-defined other direct-cost combination

Include only when authoritative Job linkage and accepted cost evidence exist:

- subcontractors;
- permits;
- Job-specific equipment or rentals;
- disposal/dump charges; and
- other externally purchased, specifically attributable Job expenses.

Defer general truck/mileage, payment-processing fees and general company overhead.
Each included category needs its own accepted evidence/identity criteria. Category
selection alone does not accept a purchase.

### `ECO-FIN-009` — Exclude unresolved conflicting components

Preserve every assertion, identify the conflict, exclude the unresolved component,
and reject or explicitly limit the affected Job measurement. No silent precedence is
established for ACP, HCP, QBO, Accounting or another source.

A future fact-specific precedence policy requires separate Company approval and
versioning. V1 does not contain one.

### `ECO-FIN-011` — Complete/current/reconciled/integrity-passed Accounting evidence

Ledger-derived evidence may participate when completeness, freshness, reconciliation
and integrity pass. Finance review may remain pending, but every dependent package and
result must be deterministically labeled `UNREVIEWED / PROVISIONAL`.

Later Finance review must generate a replayed reviewed package/result without changing
source facts or the earlier provisional package. This requires generic policy and
result-label contracts that do not yet exist.

## Explicitly deferred policy families

- `ECO-FIN-002` payment/settlement acceptance: excluded from the initial accrual metric.
- `ECO-FIN-007` overhead pools: excluded from the initial before-overhead metric.
- `ECO-FIN-008` overhead allocation: excluded from the initial before-overhead metric.
- `ECO-FIN-010` monetary materiality: deferred while exact exceptions and variances
  remain visible; missing never becomes zero.

Deferral is versioned policy intent, not deletion of the policy family. Another Company
or a later All County version may select different supported policies.

## Required generic Finance/Economics policy architecture

Before Company-specific encoding, a product milestone must define at least:

1. `FinancePolicyDefinition`: stable product policy-family and supported alternative/
   parameter schema without customer values.
2. `CompanyFinancePolicyVersion`: Company, optional Branch scope, policy family,
   version, effective interval, selected alternative, canonical parameters, status and
   predecessor.
3. `FinancePolicyApproval`: approver Company Membership, approval timestamp, decision
   digest and immutable audit evidence.
4. `FinanceEvidenceAcceptanceRule`: explicit authority/evidence requirements; separate
   from source facts and unable to mutate them.
5. `FinancePolicyResolution`: deterministic effective-date lookup with ambiguity and
   missing-policy failure.
6. `FinancePolicySnapshot`: immutable set of resolved policy-version identities bound
   into a measurement package.
7. Append-only supersession/correction: new versions only; no historical rewrite.
8. Company/Branch authorization, isolation, overlap, replay and negative tests.

All County v1 would then be represented as eight approved Company policy versions and
four explicit Company deferrals, each with its own effective interval and evidence
dependencies. Rate tables and evidence acceptance would be separate versioned records,
not embedded constants. Future customers could select other alternatives without code
changes or cross-Company effects.

## Remaining authoritative evidence blockers

Owner policy intent resolves the *choice* but not these evidence gates:

- accepted earned Job value at completion and correction treatment;
- authoritative approved actual Job time and participation;
- worker classes and approved burden rates;
- accepted Job inventory issues and actual cost layers;
- accepted Job linkage and cost for each other-direct-cost category;
- report-quality-to-Economics acceptance and provisional/reviewed labeling contract;
- reconciled public HCP economic handoffs where relevant;
- Intuit Production credentials, real QBO acquisition and later acceptance/reconciliation;
- generic Company Finance policy approval/resolution/snapshot infrastructure.

Until required evidence exists, measurement stays `PARTIAL`, `ABSENT`, `UNKNOWN` or
`CONFLICTING`; admission remains fail-closed.

## `BANK.ECO.001` readiness

Resolved by owner intent:

- the eight policy alternatives for the initial metric;
- four explicit deferrals;
- the metric name and before-overhead/accrual boundary;
- v1 conflict behavior; and
- required Accounting quality with provisional review labeling.

Still blocked by generic infrastructure:

- no Company Finance policy definition/version/approval/resolution authority;
- no immutable policy snapshot bound to measurement packages; and
- no generic provisional/reviewed result-label policy.

Still blocked by evidence:

- revenue, actual labor, burden-rate, Job-material and other-direct-cost contracts;
- HCP/QBO acquisition/acceptance and relevant reconciliation; and
- fact-specific correction and acceptance workflows.

`BANK.ECO.001` therefore remains blocked. It must not begin automatically from this
decision record.

## Future requirement — Technician Economic Attribution & Fully Loaded Employee Cost

This is a distinct future Economics model, not an extension of standard Job burden.
It must eventually answer questions such as technician profitability by week/period,
profit percentage, contribution per paid hour, service-line performance and vehicle
cost impact.

The future model must support authoritative, effective-dated evidence for:

- actual compensation, payroll taxes, benefits, workers compensation and employment
  costs;
- actual Job participation/time and primary/assisting relationships;
- non-duplicative allocation of Job revenue/contribution across multiple workers;
- assigned vehicle identity and effective assignment dates;
- fuel, insurance, maintenance/repairs, depreciation/lease/economic vehicle cost;
- significant assigned tools/equipment/assets and attributable equipment costs;
- other technician-specific operating costs; and
- a separately approved future overhead allocation.

Job Economics owns the economics of one Job and may use standard worker-class burden
for its v1 cost model. Technician Economics owns employee/technician-period attribution
and fully loaded employee cost. It consumes immutable Job results and participation
evidence but must not duplicate Job revenue when multiple workers participate. The
revenue/contribution attribution rule is a future Company-scoped policy decision.

Vehicle costs are deferred from initial Job direct costs so they remain available to
this future technician model. No technician calculation, attribution policy or asset
allocation is authorized by this record.
