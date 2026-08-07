# Version 1.0 Business Economics Contract

Status: proposed at BE.8 for economics/finance owner review

Classification: TYPE B — Serialized Integration at IC.1

## Purpose and boundary

This contract defines the Version 1.0 economic language, KPI formulas, source
ownership, attribution inputs, QuickBooks boundary, and reconciliation tolerances
used by ACP Enterprise. It is a documentation contract only.

Roadmap milestone BE.8 is not the separately completed Business Economics
external Phase 8 deterministic allocation/profitability engine. This milestone
does not implement or claim runtime calculation, persistence, migrations, APIs,
frontend behavior, scheduling, accounting transport, or provider integration.

Version 1.0 replaces Housecall Pro for operations while QuickBooks remains the
accounting system of record. ACP Enterprise may present operational economics and
prepare a reconciled accounting handoff; it does not become the general ledger,
accounts-payable, payroll, tax, or financial-statement authority in Version 1.0.

## Normative terminology

- **Source fact:** a versioned value owned by an operational or financial domain.
- **Measured:** directly supported by authoritative source evidence.
- **Estimated:** a planning value, such as an accepted Estimate or Price Book
  assumption, never presented as actual.
- **Allocated:** a measured or estimated pool distributed through an approved,
  versioned policy and driver.
- **Missing:** required evidence is unavailable; missing never means zero.
- **Operational revenue:** issued/posted invoice value under the approved accrual
  basis, net of authoritative adjustments and reversals.
- **Cash received:** successful payment value. It is settlement evidence and does
  not duplicate operational revenue.
- **Direct cost:** cost reliably attributable to one Job or other approved scope.
- **Unassigned cost:** measured cost without reliable target attribution.
- **Gross profit:** revenue less direct labor, direct materials, equipment, and
  truck costs.
- **Net profit:** gross profit less approved allocated overhead.
- **Contribution margin:** Version 1.0 uses gross profit until Finance approves a
  distinct variable-cost classification. It must be labeled accordingly.
- **Confidence:** deterministic evidence-quality assessment, separate from
  completeness and freshness.
- **Completeness:** required economic categories represented; missing fields are
  listed explicitly.
- **Freshness:** age of authoritative evidence relative to the KPI cutoff.
- **Reconciled:** all required identities and amounts agree within the tolerance
  assigned below, with every exception classified.

## Source and financial ownership map

| Fact or rule | Version 1.0 authority | Economics use | Not owned by Economics |
| --- | --- | --- | --- |
| Customer and Service Location identity | Customer domain | Attribution dimensions | Profile, contacts, addresses, lifecycle |
| Job identity, status, type, and linkage | Jobs / Operations | Profitability scope and lifecycle context | Job mutation and completion |
| Appointment and dispatch execution | Scheduling / Dispatch | Call, assigned-resource, duration, and trip context when actual | Schedule, assignment, routing |
| Price Book item/version | Sales | Estimate baseline and expected cost/revenue lineage | Pricing and catalog mutation |
| Accepted Estimate and option | Sales | Estimated basis and actual-versus-estimated baseline | Approval and conversion lifecycle |
| Invoice, adjustment, refund reference | Financial | Accrual operational revenue | Invoice lifecycle and tax calculation |
| Payment and reversal | Financial | Cash/reconciliation context | Collection, refund, processor state |
| Paid time and burden components | Future Workforce/payroll authority | Labor cost only when authoritative | Payroll and individual compensation |
| Productive Job time | Field execution / Operations | Direct labor and efficiency driver | Technician activity mutation |
| Material purchase | Procurement/Financial boundary | Measured spend; unassigned until attribution | Vendor transaction lifecycle |
| Material consumption and return | Inventory / Field execution | Direct Job material cost | Stock and costing-layer mutation |
| Equipment and fleet activity | Future asset/fleet owner | Direct or allocated cost driver | Asset and vehicle lifecycle |
| Marketing source and spend | Customer/Marketing plus Financial spend | Attribution dimension or approved pool | Campaign and lead ownership |
| Branch and Company identity | Platform | Tenant and allocation dimensions | Organization administration |
| Allocation policy and run | Business Economics, Finance-approved | Allocated cost and lineage | Source-pool creation |
| Profitability measurement | Business Economics | Authoritative operational economics | General-ledger balance or financial statement |
| KPI presentation | Analytics | Read-only projection of approved definitions | Source or calculation ownership |
| General ledger, chart, AP, payroll, tax | QuickBooks in Version 1.0 | Reconciliation reference only | All accounting authority |

Direct writes across these ownership boundaries are prohibited. Corrections occur
in the owning source and flow through versioned evidence; Economics never edits an
operational record to make a KPI reconcile.

## Version 1.0 KPI catalog

All money uses integer minor units in a single currency and one Company, scope,
accounting basis, and effective period. A denominator of zero or a missing input
produces `unknown`, not zero or infinity.

| KPI | Formula / definition | Required sources | Presentation rule |
| --- | --- | --- | --- |
| Issued revenue | Issued invoices − adjustments − reversals | Financial invoice lineage | Accrual; payments excluded |
| Cash received | Successful payments − payment reversals/refunds | Financial payment lineage | Separate from revenue |
| Direct labor cost | Job-attributed paid time × authoritative burdened rate | Workforce/payroll + Job time | Missing if either input lacks authority |
| Direct material cost | Job consumption at approved costing layer − Job returns | Inventory/Field evidence | Purchases alone are not consumption |
| Equipment cost | Direct charge or approved rate × actual utilization | Equipment owner | Rate and utilization version required |
| Truck cost | Direct trip cost or approved truck-day allocation | Fleet/Dispatch | Driver and policy displayed |
| Allocated overhead | Sum of approved Branch, Company, and administrative allocations | Finance pools + Economics policies | Never silently spread unassigned cost |
| Gross profit | Revenue − labor − materials − equipment − truck | Complete direct components | Unknown when a required component is missing |
| Gross margin % | Gross profit ÷ revenue × 100 | Gross profit and revenue | Unknown for zero/missing revenue |
| Net profit | Gross profit − allocated overhead | Gross profit and approved allocations | Operational estimate, not QuickBooks net income |
| Net margin % | Net profit ÷ revenue × 100 | Net profit and revenue | Same labeling and cutoff as net profit |
| Contribution margin | Same as gross profit in Version 1.0 | Direct components | Label “V1 contribution margin (gross basis)” |
| Allocated cost | Sum of allocation lines applied to the scope | Balanced allocation runs | Policy/run lineage required |
| Fully burdened cost | Direct costs + allocated cost | Direct facts + allocations | Missing if any required material input is missing |
| Paid-time efficiency | Productive eligible paid time ÷ eligible paid time | Workforce + actual activity | Classification completeness displayed |
| Average revenue per completed Job | Issued revenue for completed Jobs ÷ completed Job count | Financial + Jobs | Same period/cutoff on numerator and denominator |
| Estimate variance | Actual component − accepted estimated component | Sales lineage + actual facts | Component-by-component; versions displayed |
| Callback cost | Direct and allocated costs of linked callback/warranty work | Jobs/Field evidence | Original margin and later quality cost both visible |
| Unassigned purchasing | Purchases not linked to consumption or approved target | Procurement/Financial | Visible exception; not Job COGS |
| Evidence completeness | Present required categories ÷ required categories | Economics lineage | Percentage plus missing categories |
| Reconciliation exception count | Unresolved classified exceptions at cutoff | Financial/Economics reconciliation | Count never replaces amount variance |

Customer count, appointment count, completion rate, conversion, and dispatch
metrics remain operational KPIs. They may contextualize profitability but do not
become revenue, cost, or profit without the financial facts required above.

## Attribution and profitability inputs

Every profitability input carries Company, Branch when applicable, stable source
identity, source version, SHA-256 evidence digest, occurred and effective times,
currency for money, accounting basis, correction lineage, and linked Job,
Technician, Customer, Estimate, Price Book item, Invoice, Payment, asset, or
campaign identifiers where authoritative.

Attribution rules:

1. Job attribution requires direct source linkage; current assignment, Customer,
   cardholder, or date proximity is insufficient.
2. Technician attribution uses effective assignment/work intervals and supports
   shared work. It is not employee-owned accounting.
3. Branch attribution uses the source-effective Branch, not today’s employee or
   Customer Branch.
4. Company boundaries never permit allocation or rollup across tenants.
5. Purchased materials remain unassigned until consumption, return, transfer, or
   an explicitly approved allocation supplies evidence.
6. Estimate comparison uses the accepted option and Price Book versions effective
   when priced; current catalog values cannot restate history.
7. Paid time and productive time are independent facts. Neither is inferred from
   the other.
8. Cash payments, deposits, and processor settlement do not create a second copy
   of accrual revenue.
9. Corrections append reversals or superseding versions. Closed periods require
   controlled reopening under the existing Economics close contract.

## QuickBooks boundary

QuickBooks owns the Version 1.0 general ledger, chart of accounts, journal-posting
acceptance, accounts payable, payroll accounting, tax accounting, financial
statements, and official period balances. ACP Enterprise owns operational source
records and the provider-neutral export/reconciliation evidence it creates.

ACP Enterprise may:

- map operational classifications to approved QuickBooks accounts/dimensions;
- export balanced, checksum-protected journal or transaction contracts;
- record acknowledgements, rejections, corrections, and replay identities;
- compare represented source amounts with accepted QuickBooks amounts; and
- prevent operational close readiness while material exceptions remain.

ACP Enterprise may not silently correct QuickBooks, claim QuickBooks acknowledgement
without evidence, treat an export as posted before acknowledgement, replace the
general ledger, or present operational net profit as official accounting net
income. Credentials, transport, posting automation, and cutover are outside BE.8.

## Reconciliation contract and tolerances

Reconciliation is performed by Company, currency, accounting basis, effective
period, source type, and immutable source identity. Identity/count checks are
exact. Duplicate payment, invoice, export, or source identity tolerance is zero.

| Check | Version 1.0 tolerance | Result when exceeded |
| --- | --- | --- |
| Journal debit versus credit | 0 minor units | Reject export |
| Allocation pool versus lines | 0 minor units | Reject allocation |
| Source identity represented | Exact one-to-one after explicit reversal/supersession | Block reconciliation |
| Invoice/payment duplicate identity | 0 duplicates | Block reconciliation |
| Currency, Company, or basis mismatch | 0 | Reject input/export |
| Evidence digest conflict | 0 | Reject input and investigate source |
| Known per-record money variance | 0 minor units | Classify exception |
| Aggregate rounding variance | 0 minor units; remainder must be deterministically assigned | Reject result |
| Missing required evidence | No numeric tolerance | Mark incomplete; do not infer |
| Evidence freshness | Per-source approved SLA; no default invented by BE.8 | Mark stale and block affected close gate |
| QuickBooks accepted amount variance | 0 minor units for matched identities | Keep unresolved until corrected/acknowledged |

Finance may later approve a reporting materiality threshold for owner attention,
but materiality cannot change ledger, allocation, identity, or arithmetic
tolerances. Every exception retains owner, reason, amount, source identities,
status, and resolution evidence.

## KPI confidence and publication

Each financial KPI publishes basis, scope, period/cutoff, currency, component
states, confidence, completeness, freshness, integrity status, projection version,
and evidence lineage. Analytics may format these values but cannot recompute them.
Mission Control may show readiness and exception ownership but is not a financial
dashboard or source editor.

Unknown, stale, incomplete, estimated, or allocated values remain visibly labeled.
No KPI may use a green/healthy presentation when its integrity status is failed or
its required inputs are missing.

## Contract evidence and review gate

This document, the source ownership table, KPI catalog, attribution rules,
QuickBooks boundary, and tolerance table are the BE.8 contract evidence. Review
must include Economics and Finance. At IC.1, serialized integration must confirm
that concurrent Platform or phone work has not changed source ownership,
terminology, permissions, or shared documentation.

BE.8 may move only to owner review after link, terminology, Economics contract
test, and no-migration/no-runtime validation. Implementation requires a later
explicit milestone and may not be inferred from approval of this contract.

## Unresolved owner decisions

- Authoritative payroll/paid-time source and burden components.
- Inventory costing layer and material-consumption effective date.
- Revenue recognition timing for deposits, partial invoices, refunds, and credits.
- Approved source-specific freshness SLAs.
- Callback/warranty responsibility taxonomy.
- Truck-day definition and fleet cost ownership.
- Fixed, Branch, Company, administrative, and marketing pool eligibility/drivers.
- Whether a distinct variable-cost definition will supersede the Version 1.0
  contribution-margin gross basis.
- QuickBooks export grain, acknowledgement evidence, and exception owner.
- Finance-approved reporting materiality thresholds, separate from exact
  reconciliation tolerances.

## References

- [Business Economics foundation](business-economics-foundation.md)
- [Phase 5 operational-source contract](business-economics-phase5-contract.md)
- [Phase 6 deterministic computation](business-economics-phase6-computation.md)
- [Phase 7 acquisition boundary](business-economics-phase7-acquisition.md)
- [External Phase 8 engine](business-economics-phase8-allocation.md)
- [Architecture module ownership](module-map.md)
- [Version 1.0 release plan](../product/release-plan.md)
- [Launch readiness checklist](../product/launch-checklist.md)
- [Architecture roadmap](roadmap.md)
