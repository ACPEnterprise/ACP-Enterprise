# Business Economics Phase 5 Architecture Contract

Status: proposed for owner and architecture review; implementation is not authorized

Milestone: Operational Cost Sources and Luminary Profitability Intelligence

## 1. Purpose

This contract defines how ACP Enterprise operational domains supply authoritative,
measured facts to Business Economics and how Luminary turns reconciled economics
into owner-understandable profitability intelligence. It is the implementation
boundary for Phase 5, not an implementation of sources, AI, schedules, rules,
dashboards, migrations, or provider integrations.

Luminary is the Business Economics and Profitability Intelligence layer. It
answers owner business questions from authoritative Economics projections. It
does not own operational facts, calculate an alternative profit result, mutate
the ledger, or present an inference as a measured fact.

## 2. Business problem

Owners can often recognize that a technician, day, or week performed poorly but
cannot determine the loss confidently. Revenue may be known while purchased
materials are not attributable to Jobs, paid time is not separated into productive
and nonproductive time, callbacks are hidden inside ordinary work, and fixed costs
require spreadsheet allocation. A plausible number without evidence is worse than
an explicit unknown because it can drive the wrong operational decision.

Phase 5 must make the path from operational evidence to an owner explanation
complete, attributable, versioned, and honest about what remains unknown.

## 3. Scope

- Define authoritative operational source ownership and ingestion contracts.
- Define measured, estimated, allocated, and missing cost semantics.
- Define profitability equations and allocation invariants.
- Define Technician, Job, Branch, and Company profitability projections.
- Define workforce-efficiency facts without turning efficiency into payroll truth.
- Define close-period, correction, reversal, and reopening compatibility.
- Define the read boundary for Luminary, Beacon, and Mission Control.
- Define acceptance around the Daniel technician example.
- Sequence future implementation and identify blockers and file collisions.

## 4. Out of scope

- Runtime source adapters, tables, migrations, queues, schedulers, or workers.
- AI models, prompts, providers, credentials, recommendations, or evaluations.
- Beacon rules or signals.
- Dashboards or other frontend implementation.
- QuickBooks or other accounting-provider transport.
- Payroll, general-ledger, inventory, fleet, marketing, or price-book ownership.
- Manual Economics overrides or mutation of closed-period history.

## 5. Authority and information flow

```text
Operational owner
  -> versioned source record / Business Event
  -> deterministic Economics adapter
  -> EconomicsIngestionService
  -> EconomicsLedgerService
  -> allocation and measurement
  -> reconciled, versioned profitability projection
  -> bounded read contracts
       -> Luminary explanations and recommendations
       -> Beacon signal inputs
       -> Mission Control integrity presentation
```

Operational owners correct their records. Economics consumes evidence and owns
the fact, allocation, measurement, reconciliation, and projection lineage created
from that evidence. Luminary owns explanation and recommendation records, but
must cite the projection version and evidence lineage it used.

## 6. Source ownership matrix

| Fact or context | Authoritative owner | Required contract | Economics treatment | Blocker |
| --- | --- | --- | --- | --- |
| Job identity, lifecycle, branch, assigned technician | Operations / Jobs | Stable Job ID, lifecycle version, branch, assignment periods | Read-only context | Assignment history must represent reassignment over time |
| Appointment and service-call execution | Scheduling / Operations | Actual start/end, status, Job, assigned employee, event version | Productive-time and call context only when actual | Actual execution timestamps need an approved owner |
| Invoice revenue, adjustments, refunds | Financial | Posted/issued amount, currency, Job, effective date, classification, version | Measured revenue; reversals append | Revenue-recognition policy must be approved |
| Payment reference | Financial | Payment and invoice IDs, amount, status, effective date, version | Cash context; never duplicate accrual Job revenue | Refund and chargeback semantics must be final |
| Estimate and option lineage | Sales | Estimate, selected option, version, price-book item versions, Job/invoice links | Commercial lineage; not actual revenue | Estimate-to-invoice lineage is not yet authoritative |
| Price Book | Sales | Item/version, category, price, standard labor/material assumptions | Estimate baseline only | Standard-cost governance must be assigned |
| Paid labor time | Workforce / Payroll boundary | Employee, paid interval/hours, earning type, burden version, effective period | Measured time; cost measured only with authoritative rate | Payroll source and sensitive-data boundary unresolved |
| Productive labor time | Operations / Field Service | Employee, Job, actual interval/hours, activity type | Measured productive time | Overlap and travel classification policy required |
| Burdened labor cost | Workforce / Accounting policy | Base pay plus employer burden components, effective version | Measured when sourced; otherwise explicitly estimated | Burden components and access policy unresolved |
| Material purchase | Financial / Procurement | Vendor, transaction/line, quantity, amount, branch, purchaser, date, version | Measured purchase; unassigned until consumption evidence exists | Procurement source owner not implemented |
| Material consumption | Inventory / Field Service | Item, quantity, unit-cost layer, Job, employee/truck, occurrence, version | Measured Job material cost | Inventory consumption and costing method unresolved |
| Equipment utilization | Equipment / Operations | Asset, Job, actual duration/usage, rate-policy version | Allocated or measured equipment cost as declared | Asset register and rate authority unresolved |
| Fleet and truck activity | Fleet / Dispatch | Truck, branch, employee, service/trip/day usage, cost evidence | Truck-day or measured trip cost | Fleet source and truck-day definition unresolved |
| Supply-house trip | Dispatch / Field Service | Employee, truck, timestamps, destination/category, related Job if known | Operational loss/efficiency evidence; cost only from measured time/fleet facts | Detection and attribution contract unresolved |
| Callback or warranty work | Operations | Related original Job, reason, responsibility class, actual activity, version | Separate cost attribution; revenue remains explicit | Callback taxonomy and ownership decision required |
| Fixed overhead | Accounting / Company administration | Cost pool, amount, branch/company, effective period, policy eligibility | Versioned allocation, never fabricated | Account-to-pool mapping and allocation policy unresolved |
| Marketing spend and attribution | Marketing / Financial | Campaign, spend, branch, effective period, source version, attributable lead/Job when known | Direct or policy allocation; unknown attribution remains visible | Campaign and lead lineage unresolved |
| Branch and Company structure | Platform | Stable IDs, effective ownership dates, status | Allocation dimensions and tenant boundary | Effective-dated organization history required |
| Business Event | Producing domain / Events | Company, event ID/type/version, occurred time, source identity and digest | Evidence linkage and recalculation trigger | Producer contracts must be versioned |

Economics must not create placeholder operational tables to eliminate a blocker.
A source stays `contract_ready`, incomplete, or unknown until its authoritative
owner supplies the required evidence.

## 7. Required operational contracts

Every source envelope must provide `company_id`, authoritative owner, source
system, record type and ID, source version, SHA-256 evidence digest, occurred and
effective times, branch when applicable, linked Business Event, correction
lineage, currency for money, and a declared measurement state. Reusing a source
identity/version with different content is rejected.

### Labor and workforce

- Paid time and productive time are distinct facts. Neither may be derived from
  the other.
- Paid-time categories include productive, travel, supply-house, callback,
  warranty, training, meeting, administrative, leave, and unclassified.
- Productive time requires a Job and actual interval. Paid but unclassified time
  remains visible and reduces completeness.
- Burdened labor uses an effective-dated rate version with base wages, payroll
  taxes, benefits, insurance, and other approved employer burden components.
- Restricted wage evidence may be represented by a cost result and digest; read
  projections must not expose private pay rates without separate authorization.
- Workforce efficiency is productive paid time divided by eligible paid time.
  It is not profitability and must be shown with its classification completeness.

### Revenue, estimates, and Price Book

- Actual Job revenue comes from the approved accounting basis for issued/posted
  invoices, net of authoritative adjustments and reversals.
- Payments are settlement evidence and do not duplicate accrual revenue.
- Estimates and Price Book versions retain expected revenue and standard-cost
  lineage. They support actual-versus-estimated comparison but never replace an
  actual invoice or measured cost.
- A comparison must use the exact accepted estimate option and Price Book version
  effective when priced, not the current catalog.

### Materials and purchasing

- A purchase proves spend, not Job consumption.
- Job material cost requires consumption or another approved direct-attribution
  record with a versioned costing method.
- Purchased material without reliable Job attribution enters an unassigned
  purchasing pool by branch and effective period. It is not silently spread
  across Jobs.
- A policy may allocate an unassigned pool only when explicitly approved. The
  projection remains `allocated`, identifies the policy, and retains the
  pre-allocation unassigned amount.
- Returns, credits, transfers, and corrected assignments append lineage and
  trigger only affected period/scope recalculation.

### Equipment, fleet, trips, callbacks, and warranty

- Equipment cost is measured from an authoritative charge or allocated from a
  versioned rate and actual utilization. Owning an asset is not evidence that a
  Job used it.
- Fleet costs distinguish direct trip costs, truck-day allocation, and fixed fleet
  pools. A Job cannot receive both the same direct cost and its pooled duplicate.
- A supply-house trip is a measured operational activity when timestamps and
  actor/truck evidence exist. Its labor and fleet effects use those underlying
  facts; a guessed trip cost is prohibited.
- Callback and warranty work reference the originating Job when known. Their
  revenue, labor, material, equipment, and truck components remain explicit so an
  owner can see the original margin and subsequent cost of quality separately.

## 8. Cost-allocation policies

All policies are immutable, effective-dated, versioned, company-scoped, balanced
to the cent, evidence-backed, and replay-idempotent. Allocation lines retain the
pool, source period, target, driver quantity, numerator/denominator, residual,
policy/version, run/version, and explanation.

| Pool | Permitted drivers | Required safeguards |
| --- | --- | --- |
| Burdened labor | Actual paid hours by category; direct Job productive hours | No double count between direct labor and nonproductive pool |
| Unassigned purchasing | Approved Job revenue, direct material usage, or remain unassigned | Default is unassigned; owner must approve any spread policy |
| Equipment | Actual usage hours/cycles or direct charge | Zero/unknown utilization prevents allocation |
| Fleet | Actual trip, truck-day, Job duration, or branch pool | Direct charges excluded from the same pooled basis |
| Fixed overhead | Revenue, productive labor hours, Job duration, Branch, or Company | Cost-pool eligibility and excluded accounts versioned |
| Marketing | Direct campaign/lead/Job lineage; otherwise Branch/Company policy | Organic and unattributed spend remain distinguishable |
| Branch | Facts assigned by effective Branch; shared pools use approved driver | Cross-branch allocation is explicit, never inferred from current employee branch |
| Company | Company-only residual or approved Branch allocation | Allocations cannot cross Company boundaries |

Truck-day means one truck available to or used by an employee/crew for a defined
business day under a company policy. Partial days, shared trucks, unavailable
trucks, and overnight Jobs require explicit policy; there is no universal default.

## 9. Confidence, completeness, freshness, and lineage

Each component and aggregate carries four separate qualities:

- **State:** `known_measured`, `known_allocated`, `estimated`, or `missing`.
- **Confidence:** 0–100 assessment derived deterministically from input states and
  evidence quality; it is not a probability invented by Luminary.
- **Completeness:** required components present divided by required components,
  with both missing count and missing value categories exposed.
- **Freshness:** latest authoritative effective/observed time compared with the
  scope-specific service-level threshold.

Measured facts begin at 100 confidence only when source identity, version,
digest, effective period, Company, and required linkage validate. Allocated facts
cannot exceed the confidence of their pool, driver, and policy evidence. Estimated
facts remain labeled estimated even at high confidence. Missing inputs have no
amount and zero component confidence; they never become zero dollars.

Aggregate confidence cannot exceed its least-confident material component. A
policy may define materiality thresholds, but must retain every component state.
Completeness and confidence must not be averaged into one score. Every answer
cites projection, measurement, allocation, fact, evidence, policy, and engine
versions sufficient to reproduce it.

## 10. Profitability equations and invariants

For one scope and one effective period, in integer minor currency units:

```text
Actual Revenue = issued revenue - adjustments - reversals
Direct Cost = direct labor + direct materials + direct equipment + direct truck
Gross Profit = Actual Revenue - Direct Cost
Allocated Cost = allocated labor + materials + equipment + truck
                 + fixed overhead + marketing + branch/company allocations
Net Profit = Gross Profit - Allocated Cost
Gross Margin % = Gross Profit / Actual Revenue
Net Margin % = Net Profit / Actual Revenue
Workforce Efficiency = productive paid time / eligible paid time
COGS % = approved COGS components / Actual Revenue
```

Division results are unknown when revenue or eligible paid time is zero or
missing. Estimated profitability uses accepted estimate/Price Book lineage and
estimated inputs; it is never labeled actual. Actual-versus-estimated variance is
computed component by component from two independently labeled measurements.

Invariants:

1. One source value cannot be represented twice in a measurement or allocation.
2. Currency, Company, scope, accounting basis, and effective period cannot mix.
3. Missing is not zero; purchased is not consumed; paid is not productive.
4. Gross and net profit become unknown when a required material component is
   unknown, while known subtotals remain displayable as partial facts.
5. Allocation lines sum exactly to their source pool; residual is zero.
6. Job results roll up to Technician, Branch, and Company only through the same
   versioned facts and allocations.
7. Technician profitability attributes work; it is not an employee-owned ledger
   and must handle shared Jobs and reassignment explicitly.
8. Historical results are appended and superseded, never overwritten.
9. Closed-period projections change only through controlled reopening.
10. Luminary cannot alter a number, fill a missing input, or raise its confidence.

## 11. Profitability projections

- **Job:** actual and estimated revenue/cost components, margin, callbacks,
  warranty, evidence lineage, and missing/unassigned amounts.
- **Technician:** attributed Jobs, shared-work weights, revenue, paid/productive
  time, direct and allocated costs, efficiency, callbacks, and unassigned work.
- **Branch:** Job totals plus Branch pools, shared resources, unassigned purchases,
  marketing, fixed overhead, stale/missing scopes, and close state.
- **Company:** Branch rollup plus Company-only pools and cross-Branch allocations.

Day and week are effective-period views over those projections, not separate
financial authorities. Every view names its basis, cutoff, freshness, close state,
and version.

## 12. Daniel acceptance scenario

Given one weekly Technician view for Daniel with:

- $5,135 measured weekly revenue;
- 8 measured service calls;
- $2,925 measured AMEX purchases;
- 19 measured supply-house trips;
- one full paid labor day with no revenue;
- a COGS target not exceeding 20%;
- parts not reliably attributable to Jobs;
- burdened labor and fixed overhead requiring manual work today;
- an owner who believes the week lost money but cannot quantify it confidently;

the contract is accepted only when the future system produces this behavior:

1. It reports revenue and call count as measured, with evidence and cutoff.
2. It reports AMEX spend as measured purchasing, not automatically as Job COGS.
3. It exposes $2,925 as unassigned purchasing until consumption or an approved
   allocation policy exists. The raw spend-to-revenue ratio is 56.96%, but is not
   mislabeled COGS because attribution and inventory disposition are unknown.
4. It reports 19 supply-house trips and the no-revenue paid day as measured
   operational facts when their time/activity evidence exists.
5. It includes burdened labor and fixed overhead only when authoritative inputs
   or approved allocation policies exist; otherwise each is explicitly missing.
6. It does not state a definitive weekly loss while material, labor-burden, or
   overhead inputs are missing. It may state the known partial result and a
   bounded conditional result when every assumption is named.
7. It compares actual known COGS components with the 20% target without treating
   unassigned purchases as consumed parts.
8. Luminary explains the likely drivers—unassigned purchasing, trip frequency,
   paid nonproductive time, and missing burden/overhead—and recommends evidence-
   gathering or operational actions before claiming a precise profit amount.
9. Every sentence distinguishes measured, allocated, estimated, and missing facts
   and links to the versioned evidence supporting it.

An acceptable owner explanation is: “Daniel produced $5,135 from eight calls.
$2,925 of AMEX purchasing is verified but not reliably assigned to Jobs, so it is
not yet valid Job COGS. Nineteen supply-house trips and one paid no-revenue day
indicate material productivity drag. Burdened labor and fixed overhead are still
missing, so the exact weekly profit is unknown. Assign purchase lines, complete
paid-time classification, and approve the overhead policy before close.”

## 13. Owner questions Luminary must answer

- Did this Job, employee, day, week, Branch, or Company make money, and how much?
- Which parts of that answer are measured, allocated, estimated, or missing?
- Why did actual margin differ from the accepted estimate?
- Which Jobs, callbacks, warranty visits, trips, or paid-time categories drove loss?
- How much purchasing remains unassigned, and which records need attention?
- Are material costs above target, or is attribution too incomplete to know?
- What are productive-time and paid-time efficiency, with what completeness?
- Which allocation policy materially changed the result?
- What evidence changed since the prior version or close?
- Is the result fresh, reconciled, and compatible with the period’s close state?
- What action can the owner take, who owns it, and what fact would prove completion?

Luminary responses lead with the answer, quantify known components, name missing
components, explain causal evidence without overstating causation, and recommend
bounded actions. Raw KPI dumps do not satisfy this contract.

## 14. Luminary explanation and recommendation contract

An explanation input contains only an immutable Economics projection plus its
confidence, completeness, freshness, integrity status, comparison baseline, and
lineage manifest. Output must contain scope/period/version, plain-language answer,
measured findings, allocated findings, estimates, missing facts, material drivers,
comparison, recommended actions with responsible owner, evidence citations, and
an explicit limitation statement.

Recommendations may request classification, attribution, correction, policy
approval, operational follow-up, or investigation. They cannot write operational
records, approve allocations, reopen/close a period, post accounting entries, or
assert that an action occurred. Deterministic Economics calculations remain the
authority even if a future language model helps phrase the explanation.

## 15. Beacon integration boundary

Beacon may consume versioned, reconciled Economics signal inputs: scope and
period, projection version, actual/estimated state, profitability components,
confidence, completeness, freshness, integrity status, target variance, stale or
missing categories, and evidence digest. Beacon does not consume raw wage data,
invent thresholds, calculate alternative profit, or mutate Economics.

Phase 5 defines this input shape only. Signal definitions, thresholds, lifecycle,
notifications, and Beacon rules require a separate approved milestone.

## 16. Mission Control presentation boundary

Mission Control may project implementation and operational readiness: source-
binding status, blockers, ingestion freshness, pending/failed processing, close
readiness, reconciliation failures, and owner actions. It must not become a profit
dashboard, source-record editor, allocation editor, or alternate Economics API.

Mission Control displays authoritative status and links to the owning workflow.
It does not start a provider transport, close a period, or execute a Luminary
recommendation merely because a card is viewed or approved.

## 17. Close periods, corrections, and reopening

Open and closing periods accept new authoritative facts under existing Phase 4
controls. Closed periods are immutable. Late evidence, reversals, source
corrections, effective-date adjustments, attribution changes, or allocation-policy
changes affecting a closed period create a reopening request with responsible
owner and reason. Approval transitions the period to reopened, appends corrected
facts/allocations/measurements/projections, reruns affected reconciliation and
audit packaging, and closes through the normal readiness gate. Luminary and
Beacon must identify superseded answers and never silently continue presenting an
old version as current.

## 18. Security and events

Company isolation is mandatory at every source, fact, policy, projection, and
consumer boundary. Branch access is additive and cannot bypass Company checks.
Private compensation components require a narrower permission than aggregate
Economics read access. Explanation citations expose identifiers and digests, not
restricted source payloads.

Future source owners publish versioned Business Events after their transaction
commits through the platform event/outbox contract. Consumers are idempotent by
source identity/version/digest, tolerate at-least-once delivery, reject cross-
Company linkage, retain ordering metadata, and record failures. Exact event names
and payload schemas are blockers to implementation and are not invented here.

## 19. Phase 5 implementation sequence

Each step requires its own approved implementation scope and migrations review:

1. Resolve source ownership, privacy, accounting-basis, costing, callback, trip,
   and allocation-policy decisions.
2. Approve versioned operational contracts and Business Event schemas.
3. Implement authoritative labor/paid-time and Job/estimate/Price Book lineage.
4. Implement purchase and Job-consumption sources with an unassigned-pool view.
5. Implement equipment, fleet, trip, callback, warranty, marketing, and overhead
   sources only after their owners exist.
6. Extend deterministic Economics allocation and measurement projections for
   Technician and actual-versus-estimated views.
7. Prove close/reopening, reconciliation, idempotency, tenant isolation, and the
   Daniel scenario on populated migrations.
8. Publish read-only consumer contracts for Luminary, Beacon, and Mission Control.
9. Implement deterministic Luminary explanation records before considering any
   AI phrasing provider.
10. Review and authorize Beacon rules, UI, scheduling, and provider work only in
    separate milestones.

## 20. Explicit dependency blockers

- Authoritative paid-time/payroll source and compensation privacy permission.
- Actual appointment/work-activity and employee-assignment history.
- Accepted estimate, invoice, and Price Book version lineage.
- Procurement source ownership and material purchase-line contract.
- Inventory consumption, transfer, return, and unit-cost method.
- Callback/warranty taxonomy and original-Job responsibility semantics.
- Fleet/asset registers, utilization evidence, and supply-house trip definition.
- Fixed-overhead pools, account mappings, materiality, and approved drivers.
- Marketing campaign/spend/lead/Job lineage and allocation policy.
- Revenue-recognition and COGS component policy.
- Effective-dated Branch/Company organization history.
- Event names, versions, outbox ownership, and replay policy for each producer.
- Luminary authorization, explanation retention, and recommendation-approval policy.

Implementation must not replace these decisions with defaults.

## 21. Unresolved owner decisions

Before runtime work begins, the owner must approve or delegate authority for:

1. Accrual revenue recognition, refund/chargeback treatment, and the components
   included in the company COGS target.
2. The authoritative payroll/paid-time source, permitted burden components, and
   who may view individual compensation versus aggregate labor cost.
3. Whether unassigned purchasing must remain unallocated through close or may use
   a named fallback policy, including the approved driver and materiality limit.
4. The inventory costing method and when purchase, receipt, transfer, consumption,
   return, and vendor credit become financially effective.
5. Productive, travel, supply-house, callback, warranty, and unclassified paid-
   time definitions, including overlapping activity precedence.
6. Callback/warranty responsibility attribution and whether owner-facing results
   restate the original Job, show later cost of quality separately, or both.
7. Truck-day definition and allocation treatment for partial days, shared trucks,
   unavailable vehicles, and overnight Jobs.
8. Fixed-overhead, marketing, Branch, and Company pool eligibility, drivers,
   materiality thresholds, and approval owners.
9. Estimate/Price Book baseline selection when an estimate is revised after Job
   start or an invoice departs from the accepted option.
10. Luminary explanation retention, permissions, recommendation ownership, and
    whether deterministic templates must precede any AI-assisted phrasing.

Silence is not approval. Until decided, the corresponding value remains missing,
unassigned, or contract-blocked.

## 22. Migration and shared-file collision analysis

This contract adds no migration. Future persistence changes will likely extend
the existing linear Economics migration head and collide with any concurrent
work that edits `backend/app/economics/models.py`, `schemas.py`, `router.py`,
`accounting.py`, `processing.py`, or the Economics architecture document. Source
work may also collide with Jobs, Scheduling, Financial, Platform permissions,
Business Events, and their migrations.

Controls for future work:

- Assign one migration owner and reserve the next revision only at implementation.
- Reconcile concurrent migration heads; never guess or rewrite an applied revision.
- Keep operational models in their owning modules and use adapters/contracts.
- Coordinate shared permission and event-schema edits before parallel branches.
- Preserve Phase 4 tables and append compatible versions rather than repurposing
  columns or changing historical semantics.
- Run fresh, populated, downgrade/re-upgrade, drift, tenant-isolation, close, and
  reconciliation validation before accepting implementation.

## 23. Acceptance criteria

- Every requested source has one owner and an explicit evidence contract or named
  blocker.
- Purchased materials cannot be mislabeled as consumed Job materials.
- Paid time cannot be mislabeled as productive time.
- Actual and estimated profitability are independently labeled and reproducible.
- Every allocation balances and exposes its policy, driver, and residual.
- Missing values propagate honestly and are not converted to zero or guesses.
- Technician, Job, Branch, and Company views reconcile to the same fact lineage.
- Closed-period corrections require controlled reopening and produce new versions.
- Luminary answers the listed owner questions with citations and limitations.
- The Daniel scenario produces the required partial, honest conclusion without a
  fabricated loss amount.
- Beacon and Mission Control remain bounded consumers, not calculation authorities.
- No implementation begins until blockers and owner decisions are approved.

## 24. Future extension points

Provider transports, deterministic recommendation policies, AI-assisted phrasing,
Beacon signal definitions, dashboards, and advanced cost forecasting may consume
these contracts later. None may bypass Economics authority, evidence lineage,
close controls, permission boundaries, or explicit uncertainty.
