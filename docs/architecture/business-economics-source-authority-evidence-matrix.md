# Business Economics Source Authority Evidence Matrix

Status: BE.EVIDENCE.1 — evidence inventory complete

Classification: TYPE A — Documentation/evidence inventory

## Purpose and authority boundary

This matrix inventories source contracts visible at one frozen repository ref.
It applies the normative [Version 1 Business Economics Contract](business-economics-v1-contract.md),
the [external Phase 8 adoption review](business-economics-phase8-adoption-review.md),
and the [Economics execution plan](business-economics-execution-plan.md). It does
not approve financial policy, implement an adapter, create runtime or persistence
behavior, integrate external Phase 8, or make BE.9 READY.

Business Economics consumes authoritative facts and owns economic measurements;
it does not own operational transactions. QuickBooks remains the Version 1
general-ledger, chart, accounts-payable, payroll-accounting, tax, official-close,
and financial-statement authority. `ABSENT` never means zero. Job attribution is
never inferred from date, Customer, cardholder, employee assignment, proximity,
schedule, Job presence, or capability records.

## Frozen source-ref manifest

| Item | Frozen evidence |
| --- | --- |
| Repository | `ACP-Enterprise` |
| Authoritative ref | `origin/business-economics-foundation` |
| Commit | `bb27bca35d222cf2d4b06e809f2ca87ce028b007` |
| Subject | `docs(economics): resolve phase 8 adoption strategy` |
| Inventory date | 2026-08-11 |
| Economics contract | [Version 1 contract](business-economics-v1-contract.md) |
| Review disposition | [BE.REVIEW.1](business-economics-phase8-adoption-review.md) |
| Queue dependency | [BE.PLAN.1](business-economics-execution-plan.md) |

No claim in this document applies to code or contracts outside that commit.

## Evidence-state definitions and totals

- **AVAILABLE:** the frozen source exposes the authoritative identity, scope,
  version/effective-time semantics, and values needed for the stated bounded use.
- **PARTIAL:** some authoritative fields exist, but one or more required lineage,
  scope, version, correction, policy, or value fields are unavailable.
- **ABSENT:** no authoritative source contract for the economic fact exists.
- **CONFLICTING:** two current authorities claim incompatible ownership or values.
- **NOT APPLICABLE:** the item is a boundary/reference, not an operational fact
  Economics may acquire.

| State | Count |
| --- | ---: |
| AVAILABLE | 2 |
| PARTIAL | 9 |
| ABSENT | 12 |
| CONFLICTING | 0 |
| NOT APPLICABLE | 1 |
| **Total** | **24** |

The superseded Phase 4 equipment binding is a documented historical mismatch,
not a current `CONFLICTING` result, because the owner has explicitly resolved
Version 1 authority in favor of the future Asset/Fleet domain.

## Source ownership matrix

| Source domain | Current authoritative scope | Economics may consume | Evidence path | State |
| --- | --- | --- | --- | --- |
| Jobs | Job identity, lifecycle, Customer/Service Location and appointment linkage | Job scope and lifecycle context | [Jobs model](../../backend/app/jobs/models.py) | AVAILABLE |
| Scheduling | Appointment identity, planned window/duration and lifecycle | Scheduled context; never actual labor or travel | [Scheduling model](../../backend/app/scheduling/models.py) | AVAILABLE |
| Dispatch | Event names only; no authoritative assignment/activity model | Nothing measured yet | [Event types](../../backend/app/events/types.py) | ABSENT |
| Sales / Estimates | Migrated Estimate header and lines | Estimated revenue context only, incomplete without accepted option/version lineage | [Financial models](../../backend/app/financials/models.py) | PARTIAL |
| Price Book | Provider-neutral acquisition contract only; no source table/model | Nothing authoritative yet | [Acquisition contract](../../backend/app/economics/operational_acquisition.py) | ABSENT |
| Inventory | No source implementation | Nothing authoritative yet | [Phase 4 contract-ready binding](../../backend/app/economics/accounting.py) | ABSENT |
| Purchasing | No purchase/vendor transaction source implementation | Nothing authoritative yet | [BE.8 ownership declaration](business-economics-v1-contract.md) | ABSENT |
| Financial / Invoicing | Migrated Invoice headers and lines | Issued operational revenue, subject to missing version/correction policy | [Financial models](../../backend/app/financials/models.py) | PARTIAL |
| Financial / Payments | Migrated Payment records | Cash context, subject to missing version/reversal lineage | [Financial models](../../backend/app/financials/models.py) | PARTIAL |
| Workforce / payroll | Employee and capability identity; no payroll/time/burden facts | Technician identity only; no labor cost | [Employee model](../../backend/app/platform/employees/models.py), [Workforce models](../../backend/app/workforce/models.py) | PARTIAL |
| Asset/Fleet | Owner-designated future authority; no contract/model at frozen ref | Nothing until an authoritative contract exists | [BE.8 ownership declaration](business-economics-v1-contract.md) | ABSENT |
| Marketing | Customer-level free-text source only; no campaign/spend authority | Attribution context only, with incomplete lineage | [Customer model](../../backend/app/customers/models.py) | PARTIAL |
| Customers | Customer and Service Location identity | Attribution dimensions, not revenue or cost | [Customer model](../../backend/app/customers/models.py) | PARTIAL |
| Events | Generic Business Event envelope and event-type vocabulary | Trigger/linkage; monetary facts only when explicitly complete and measured | [Event model](../../backend/app/events/models.py), [Economics adapter](../../backend/app/economics/adapters.py) | PARTIAL |
| Platform | Company and Branch identity/isolation | Tenant and allocation dimensions | [Company model](../../backend/app/platform/company/models.py), [Branch model](../../backend/app/platform/branch/models.py) | PARTIAL |
| Accounting / QuickBooks | QuickBooks owns the Version 1 general ledger; Economics has provider-neutral handoff contracts | Reconciliation reference only | [Accounting contracts](../../backend/app/economics/accounting.py), [BE.8 boundary](business-economics-v1-contract.md) | NOT APPLICABLE |

## Fact-by-fact evidence matrix

The “identity / version / time” and “scope / links” columns explicitly record
source-version, occurred/effective/observed-time, Company/Branch, and Job/
Technician/Customer linkage availability. Economics-generated SHA-256 evidence
does not make a missing source version or source value authoritative.

| # | Required fact and state | Owner; exact authority | Identity / version / time | Scope / links | Money, basis, state, freshness and sensitivity | Correction, digest, readiness, gap owner and first consumer |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | Job identity/lifecycle — **AVAILABLE** | Jobs; [Job and JobAppointmentLink](../../backend/app/jobs/models.py) | UUID and Job number; `concurrency_version`; created/updated plus lifecycle timestamps | Company, Branch, Customer, Service Location; explicit appointment link | Not monetary; actual lifecycle context; no approved freshness SLA; internal operational data | Updates/events provide versionable context; adapter can digest the source; ready for bounded Job context in BE.10, Jobs owns gaps |
| 2 | Scheduled Appointment context — **AVAILABLE** | Scheduling; [Appointment](../../backend/app/scheduling/models.py) | UUID/number; `concurrency_version`; created/updated, planned window | Company, Branch, Customer, Service Location; Job only through explicit [JobAppointmentLink](../../backend/app/jobs/models.py) | Expected duration is estimated context, never actual labor; no freshness SLA; operational data | Reschedule/cancel fields and events exist; digest can be derived; ready for planned context in BE.10, Scheduling owns gaps |
| 3 | Actual Dispatch/Technician activity and trips — **ABSENT** | Future Dispatch/Field authority; only names in [EventType](../../backend/app/events/types.py) | No authoritative activity identity/version or actual start/end model | No authoritative Job-Technician-trip linkage | No cost/basis; missing, no SLA; employee-sensitive when implemented | Generic events cannot prove activity; no digestable source record; Dispatch/Field owner required by BE.9/BE.10 then BE.11 |
| 4 | Accepted Estimate/option — **PARTIAL** | Sales/Financial migration boundary; [Estimate and lines](../../backend/app/financials/models.py) | UUID/number and created/presented time; no concurrency/source version or approval timestamp | Company, Branch, Job, Customer, Service Location; no selected option | Currency and totals exist; estimated basis; no SLA; commercial data | No correction/supersession lineage or content digest; Sales must add accepted option/version/effective evidence for BE.9/BE.10 |
| 5 | Price Book item/version lineage — **ABSENT** | Future Sales/catalog owner; only a non-authoritative [snapshot contract](../../backend/app/economics/operational_acquisition.py) | No source identity/version/effective record | No authoritative Estimate/option/Job linkage | Expected revenue/labor/material fields are contract-only; missing, no SLA | No source correction/digest; Sales/catalog dependency for BE.9/BE.10 and acquisition in BE.11 |
| 6 | Issued Invoice revenue — **PARTIAL** | Financial/Invoicing; [Invoice and lines](../../backend/app/financials/models.py), [adapter](../../backend/app/economics/adapters.py) | UUID/number, created/issued time; adapter derives status/time string, but source lacks durable version/update | Company, Branch, Job, Customer, Service Location | Currency/totals; accrual candidate for issued/partially-paid/paid; no SLA; financial-sensitive | `void` exists but credit/adjustment/reversal lineage does not; generated digest available; Financial decision/source version required by BE.9 then BE.11 |
| 7 | Successful Payment/cash — **PARTIAL** | Financial/Payments; [Payment](../../backend/app/financials/models.py), [adapter](../../backend/app/economics/adapters.py) | UUID/reference, created/paid time; no durable source version/update | Company, Branch, Invoice, Customer; Job only transitively through Invoice | Currency/amount; cash basis and succeeded/refunded status; no SLA; financial-sensitive | Refund status exists without reversal amount/lineage; generated digest available; Financial/Payments must complete correction/version contract for BE.9/BE.10 |
| 8 | Employee/Technician identity — **PARTIAL** | Platform/Workforce; [Employee](../../backend/app/platform/employees/models.py), [profile](../../backend/app/workforce/models.py) | UUID/employee number, created/updated; capability profile has concurrency version, Employee does not | Company and home Branch; no authoritative Job work interval | Not monetary; actual identity only; no SLA; personal data | Archive/update fields, no immutable supersession/digest contract; Workforce identity prerequisite for BE.9/BE.10 |
| 9 | Paid time — **ABSENT** | Future Workforce/payroll authority; [BE.8 contract](business-economics-v1-contract.md) | No time-entry/pay-period identity, version or effective interval | No Company/Branch/Job/Technician paid-time record | No hours/currency/basis; missing, no SLA; highly wage-sensitive | No corrections/digest; Workforce/payroll dependency for BE.9 then BE.11/BE.12 |
| 10 | Productive Job time — **ABSENT** | Future Field execution/Operations authority; [BE.8 contract](business-economics-v1-contract.md) | No technician work-interval identity/version/effective period | Job lifecycle timestamps do not establish Technician time | No measured duration; missing, no SLA; employee-sensitive | No corrections/digest; Field/Operations contract required by BE.9/BE.10 then BE.11 |
| 11 | Burdened labor rate/components — **ABSENT** | Future Workforce/payroll plus Finance; [BE.8 decision](business-economics-phase8-adoption-review.md) | No rate/component identity/version/effective period | No Employee/Company/Branch linkage | No money/basis; missing, no SLA; restricted compensation data | No correction/digest; Workforce/payroll and Finance owner decision required by BE.9/BE.12 |
| 12 | Material purchase/unassigned purchasing — **ABSENT** | Future Procurement/Financial boundary; [BE.8 contract](business-economics-v1-contract.md) | No vendor/purchase identity/version/time | No Company/Branch/card/vendor or authoritative target linkage | No currency/amount/basis; missing, no SLA; financial-sensitive | No correction/digest; Procurement/Financial dependency for BE.9/BE.10 then BE.11 |
| 13 | Material consumption/return by Job — **ABSENT** | Future Inventory/Field authority; [contract-ready binding](../../backend/app/economics/accounting.py) | No usage/return/transfer identity/version/effective time | No Company/Branch/Job/item linkage | No quantity/costing layer/currency; missing, no SLA | No correction/digest; Inventory costing/effective-date dependency for BE.9/BE.10 then BE.11 |
| 14 | Equipment utilization/cost — **ABSENT** | Future Asset/Fleet authority by owner decision; stale [Phase 4 binding](../../backend/app/economics/accounting.py) is superseded | No asset/utilization/cost identity/version/operating period | No authoritative Company/Branch/Job/Technician/asset linkage | No utilization, rate, currency or basis; missing, no SLA; operational/financial-sensitive | No corrections/digest; Asset/Fleet contract required for BE.9/BE.10, acquired in BE.11 and allocated in BE.12 |
| 15 | Fleet utilization/truck-day/cost — **ABSENT** | Future Asset/Fleet authority; [BE.8 contract](business-economics-v1-contract.md) | No vehicle/activity/truck-day identity/version/period | No authoritative Company/Branch/Job/Technician/vehicle linkage | No duration/trips/cost/currency/basis; missing, no SLA | No correction/digest; Asset/Fleet definition and cost contract required by BE.9/BE.10 then BE.11/BE.12 |
| 16 | Overhead and administrative pools — **ABSENT** | Finance/Accounting source pools; [contract-ready binding](../../backend/app/economics/accounting.py) | No source-pool identity/version/effective period | No Company/Branch eligibility or allocation target contract | No amount/currency/basis; missing, no SLA; financial-sensitive | Economics policies cannot create source pools; Finance decision/dependency first required by BE.12 |
| 17 | Customer/Service Location context — **PARTIAL** | Customers; [Customer and related records](../../backend/app/customers/models.py) | UUID/customer number, created/updated/archive; no explicit concurrency/source version | Company and Service Location; no authoritative Customer Branch | Not monetary; actual identity/context; no SLA; personal data | Lifecycle events exist but no source digest/version contract; Customer/Platform gaps feed BE.9/BE.10 |
| 18 | Marketing source attribution — **PARTIAL** | Customer/Marketing; free-text `marketing_source` in [Customer](../../backend/app/customers/models.py) | Customer identity/updated time; no campaign/source version/effective interval | Company/Customer only; no Branch, Job, campaign or spend linkage | Attribution text only, no spend/currency/basis; no SLA; commercial data | No correction/digest contract; Marketing and Financial spend authority required by BE.9/BE.12 |
| 19 | Callback/warranty linkage and responsibility — **ABSENT** | Future Jobs/Field quality authority; [BE.8 decision routing](business-economics-phase8-adoption-review.md) | No callback/warranty identity/version/effective classification | No original/follow-up Job or responsible-actor linkage | No cost/basis; missing, no SLA; operational data | Job reopen is not callback evidence; taxonomy/correction contract required by BE.9/BE.10 then BE.11 |
| 20 | Business Event envelope/economics payload — **PARTIAL** | Events; [BusinessEvent](../../backend/app/events/models.py), [adapter](../../backend/app/economics/adapters.py) | UUID/correlation, occurred/created; source version supplied externally, not stored | Company/Branch/entity are nullable; User optional | Explicit complete `economics` payload may be measured with currency/basis; no SLA; payload sensitivity varies | Append-only envelope and generated digest; arbitrary payload is not source authority; Events/source owner must close scope/version gaps for BE.10/BE.11 |
| 21 | Company identity — **PARTIAL** | Platform; [Company](../../backend/app/platform/company/models.py) | UUID/code, created/updated/archive; no concurrency/source version | Company is tenant root; Branch/Job links live in owning domains | Not monetary; actual dimension; no SLA; internal data | No immutable correction/digest contract; Platform version contract required by BE.9/BE.10 |
| 22 | Branch identity — **PARTIAL** | Platform; [Branch](../../backend/app/platform/branch/models.py) | UUID/code, created/updated/archive; no concurrency/source version | Explicit Company FK and tenant constraint | Not monetary; actual dimension; no SLA; internal data | No immutable correction/digest contract; Platform version contract required by BE.9/BE.10 |
| 23 | Source-specific freshness policy — **ABSENT** | Each source owner plus Economics/Finance close policy; [BE.8 tolerance](business-economics-v1-contract.md) | No approved SLA identities/versions/effective dates | Must vary by Company/source and affected close gate | Missing policy; never defaulted; operational-control sensitive | No approval/digest evidence; owners/Finance required for BE.10 and operational BE.15 |
| 24 | QuickBooks general-ledger evidence — **NOT APPLICABLE** | QuickBooks/Accounting; [BE.8 boundary](business-economics-v1-contract.md) | Provider-neutral export records exist, but live provider acknowledgement is outside this source inventory | Company/Branch dimensions only under approved mapping | Official accounting basis belongs to QuickBooks; financial-sensitive | Economics cannot infer posting/acceptance; export grain and acknowledgement decisions are BE.14 dependencies, not BE.11 acquisition facts |

## Correction and versioning matrix

| Domain | Version evidence | Correction/reversal evidence | Result |
| --- | --- | --- | --- |
| Jobs | `concurrency_version`, updated/lifecycle timestamps in [Job](../../backend/app/jobs/models.py) | lifecycle Business Events and explicit reopen; no general immutable source supersession | AVAILABLE for bounded context; correction contract remains PARTIAL |
| Scheduling | `concurrency_version`, reschedule count/timestamps in [Appointment](../../backend/app/scheduling/models.py) | reschedule/cancel state and events; planned context only | AVAILABLE for scheduled context, not actual activity |
| Estimates | no concurrency/update/version in [Estimate](../../backend/app/financials/models.py) | status only; no accepted-option correction lineage | PARTIAL |
| Invoices | no concurrency/update/version in [Invoice](../../backend/app/financials/models.py) | `void` status only; no credit/adjustment/reversal records | PARTIAL |
| Payments | no concurrency/update/version in [Payment](../../backend/app/financials/models.py) | `refunded` status only; no reversal identity/amount lineage | PARTIAL |
| Customers | updated/archive timestamps in [Customer](../../backend/app/customers/models.py), no explicit version | lifecycle events, no immutable supersession record | PARTIAL |
| Employees/Workforce | Employee updated/archive timestamps; capability records have concurrency versions in [Workforce](../../backend/app/workforce/models.py) | no paid-time, work-interval, or payroll correction lineage | PARTIAL identity; labor economics ABSENT |
| Business Events | append-only UUID/correlation and occurred/created timestamps in [BusinessEvent](../../backend/app/events/models.py) | no stored event version; correction meaning belongs to source payload/owner | PARTIAL |
| Company/Branch | updated/archive timestamps in [Company](../../backend/app/platform/company/models.py) and [Branch](../../backend/app/platform/branch/models.py) | no explicit source version or immutable supersession | PARTIAL |
| Price Book, Inventory, Purchasing, Asset/Fleet, overhead pools | no authoritative source contract | none | ABSENT |

Economics’ own reversal/supersession machinery does not cure missing source
correction evidence; it can only preserve corrections supplied by the owner.

## Company and Branch isolation assessment

- Jobs and Appointments carry required Company and Branch fields and database
  scope constraints in [Jobs](../../backend/app/jobs/models.py) and
  [Scheduling](../../backend/app/scheduling/models.py).
- Estimates, Invoices, and Payments carry Company/Branch/parent constraints in
  [Financial models](../../backend/app/financials/models.py), but remain PARTIAL
  for source version and correction lineage.
- Customer identity is Company-scoped, but a Customer has no authoritative Branch;
  Branch attribution must come from a source-effective Job, Appointment, Invoice,
  or another approved link, never today’s employee or Customer location.
- Employee `home_branch_id` is identity context, not evidence that work occurred
  in that Branch. Workforce branch eligibility is permission/capability, not
  measured labor.
- Business Event Company/Branch fields are nullable. An event without complete
  scope cannot create a scoped measured Economics fact.
- Every absent source must eventually provide Company and effective Branch where
  its fact is Branch-scoped. Cross-Company acquisition or allocation is forbidden.

## Sensitive payroll and wage-data boundary

Employee identity and capability records do not contain authoritative paid time,
wages, burden rates, benefits, payroll tax, or compensation. Those economic facts
are `ABSENT`. Future Workforce/payroll evidence must expose the minimum derived
cost contract needed by Economics, with explicit Company, effective period,
source version, correction lineage, and restricted authorization. Raw individual
compensation must not flow to Reporting, Mission Control, Beacon, or Luminary
merely because Economics may calculate a permitted aggregate. Evidence digests
and identifiers must not embed secret or compensation values.

Equipment capability/proficiency in [Workforce models](../../backend/app/workforce/models.py)
only states what an employee is qualified to use. It is never an equipment asset,
assignment, utilization interval, truck-day, or cost record.

## Asset/Fleet decision and stale Phase 4 binding

The owner designates the future Asset/Fleet domain as authoritative for vehicle
and equipment identity, assignment, utilization, operating periods, availability,
operating/maintenance facts, and asset/fleet cost evidence. Workforce remains
bounded to employee identity, capability, proficiency, qualification, labor facts,
and its own availability evidence.

The Phase 4 binding `("equipment", "workforce", ..., "equipment_utilization")`
in [SourceBindingService](../../backend/app/economics/accounting.py) is
architecturally stale and superseded for Version 1 source-authority decisions.
BE.EVIDENCE.1 preserves it as historical implementation and does not rewrite or
delete it. Current equipment utilization, fleet utilization, truck-day evidence,
and equipment/fleet cost evidence are `ABSENT` until an authoritative Asset/Fleet
contract exists. No value may be inferred from skill, qualification, schedule,
assignment, proximity, Job presence, or generic overhead.

The first Economics ownership mapping is BE.9; evidence conformance is BE.10,
acquisition is BE.11, and any approved equipment/truck allocation first executes
in BE.12. A future Asset/Fleet milestone must define immutable asset/activity
identity, Company/effective Branch, Job/Technician links where authoritative,
version/effective period, corrections, costs/currency/basis, freshness, and
evidence digest inputs before these facts can become `AVAILABLE`.

## Gaps grouped by responsible owner

| Responsible owner | Blocking or partial evidence | Required next contract evidence |
| --- | --- | --- |
| Workforce/payroll + Finance | Employee source version, paid time, burdened rates/components | protected time/rate identities, effective versions, corrections and least-privilege access |
| Field execution / Dispatch | actual Technician work intervals, dispatch activity, trips | actual activity identities/times, Job/Technician linkage, corrections and SLA |
| Sales / Price Book | accepted Estimate option and historical Price Book lineage | immutable option/item versions, effective pricing and expected component lineage |
| Inventory / Field | consumption, return, transfer and costing effective date | item/quantity/cost-layer identity, Job linkage, corrections and source SLA |
| Procurement / Financial | purchases and unassigned purchasing | vendor/purchase identity, Company/Branch, amount/currency, correction lineage |
| Asset/Fleet | equipment/vehicle identity, utilization, truck-days and cost | owner-approved asset/activity/cost contract described above |
| Financial / Invoicing / Payments | durable versions, credits/adjustments/refunds/reversals and recognition timing | immutable status/version and correction records plus Finance recognition matrix |
| Jobs / Field quality | callback/warranty linkage and responsibility | original/follow-up Job relationship, taxonomy, effective correction evidence |
| Marketing + Financial | campaign/source version and spend | campaign identity, effective attribution, spend/pool evidence and correction rules |
| Platform / Customers | explicit Company/Branch/Customer source versions | version/effective semantics and safe Branch attribution contract |
| Every source owner + Finance | freshness SLAs | approved source-specific SLA version, cutoff, outage/grace and close impact |
| Finance / Accounting / QuickBooks | overhead pools, export grain, acknowledgement, exceptions, materiality | pool identities/policies for BE.12 and accounting decisions for BE.14/BE.15 |

## BE.9 readiness contribution

This inventory provides a frozen evidence baseline and names source owners, but
BE.9 remains **BLOCKED**. It does not satisfy the required ACC.1 → ACC.2 chain,
RPT.1 and conditional IC.2, accepted source contracts, owner decisions, or
collision analysis. Specifically, labor, Price Book, Inventory, Purchasing,
Asset/Fleet, callbacks, overhead, freshness, and complete financial correction
contracts remain absent or partial. The stale Phase 4 equipment binding must be
reconciled in an explicitly approved future contract/implementation milestone;
this document does not authorize that change.

## BE.10 conformance inputs

BE.10 can use this matrix to build fixtures for:

1. Jobs and scheduled Appointment context with version replay and scope isolation;
2. partial Estimate/Invoice/Payment/Customer/Event records that must remain
   incomplete rather than inferred;
3. missing paid/productive time, Price Book, purchasing, consumption, Asset/Fleet,
   overhead, callback, and SLA inputs;
4. Company/Branch mismatch, nullable event scope, duplicate identity, stale,
   conflicting digest, correction and actual-versus-estimated cases; and
5. the explicit rule that Workforce equipment capability cannot satisfy an
   Asset/Fleet utilization requirement.

BE.10 must not convert a provider-neutral Economics snapshot type into source
authority when the owning domain has no corresponding source contract.

## BE.11 acquisition prerequisites

Before an adapter may be bound for a source, the owner must supply stable identity,
version, Company/effective Branch, effective and observation timing, required
scope links, value/currency/basis when monetary, actual/estimated semantics,
correction lineage, approved freshness behavior, and canonical digest inputs.
Source access must be read-only and Company/Branch authorized. Missing values
remain explicit; conflicting identities fail closed; replay of identical evidence
is deterministic.

At the frozen ref, only bounded Job and scheduled Appointment context meet the
matrix’s `AVAILABLE` definition. Existing Invoice and Payment adapters demonstrate
translation mechanics but their source contracts remain `PARTIAL`; they are not
evidence that every Version 1 revenue/cash correction case is acquisition-ready.
No adapter may be activated for an `ABSENT` fact.

## Non-authorization statement

This evidence inventory does not approve financial policy, allocation drivers,
source bindings, runtime work, persistence, migrations, APIs, frontend behavior,
provider transport, Preview, Production, external Phase 8 integration, or any
successor milestone. It does not begin BE.9, BE.10, BE.11, BE.12, or BE.13.
