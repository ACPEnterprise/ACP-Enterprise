# Enterprise operational data-quality acceptance packet

## Authority and boundary

This package is a read-only, Company-scoped evidence projection. It neither repairs nor
merges records, resolves Migration HOLDs/crosswalks, chooses policy, schedules work,
changes custody, posts Accounting, adjusts Inventory, applies Payments, or sends a
communication. `COMPANY_AUDIT_READ` is required. Branch scope is returned explicitly;
source-domain correction remains permission-gated by that domain.

The versioned catalog defines evidence, explanation, severity, launch impact, repair
owner, and a stable SHA-256 contract digest. Issue digests bind rule version, Company,
safe record identity, and observed evidence class. Inspection emits no Business Event.

## Operational matrix

| Domain | State | Active evidence / exact gate |
|---|---|---|
| Customers | READY_WITH_EXCEPTIONS | display identity and duplicate-candidate probes; survivorship remains owner review |
| Contacts | READY_WITH_EXCEPTIONS | usable destination probe; preference selection remains Customer authority |
| Locations | READY_WITH_EXCEPTIONS | operational address and Customer scope; source address gaps remain source required |
| Jobs | READY_WITH_EXCEPTIONS | tenant, Branch, Customer, Location integrity probe |
| Appointments / Dispatch | READY_WITH_EXCEPTIONS | Job/Appointment scope probe; workforce eligibility remains source-domain evidence |
| Employees / Workforce | DEPENDENCY_BLOCKED | catalog contract is ready; Employee identity disposition and optional enrichment remain owning-lane work |
| Estimates | DEPENDENCY_BLOCKED | stale-revision rule contract ready; authoritative presentation projection integration required |
| Invoices / Payments / AR | DEPENDENCY_BLOCKED | linkage/settlement contracts ready; payment settlement ambiguity remains Payments reconciliation |
| Purchasing / AP | DEPENDENCY_BLOCKED | exception contract ready; Vendor and matching semantics remain Purchasing/AP authority |
| Inventory | DEPENDENCY_BLOCKED | orphan/movement contract ready; quantity correction remains Inventory authority |
| Service Agreements | DEPENDENCY_BLOCKED | enrollment/version/coverage contract ready; policy gates remain explicit |
| Assets / Fleet / Custody | READY_WITH_EXCEPTIONS | Asset tenant relationship probe; identity disposition and Fleet policy remain Assets authority |
| Communications | DEPENDENCY_BLOCKED | destination contract ready; legal preference/suppression evidence remains Communications authority |
| Timekeeping | DEPENDENCY_BLOCKED | structural rule contract ready; punch correction remains Timekeeping authority |
| Migration identities | SOURCE_REQUIRED | only safe HOLD/crosswalk projections may be consumed; raw QBO/HCP prohibited |
| Cross-domain references | READY_WITH_EXCEPTIONS | active bounded probes fail closed; additional domain adapters are integration work |
| New-work operability | READY_WITH_EXCEPTIONS | clean new work is independent of `HISTORICAL_ONLY` exceptions |
| Historical preservation | READY | historical issues are preserved and separately classified, never auto-corrected |

## Deterministic rehearsals

1. Clean Company: create valid Customer, Location, Job and Appointment evidence in an
   isolated database; `/summary` returns no issue for active probes.
2. Messy Company: add duplicate normalized Customer identity, destination-less Contact,
   incomplete Location, mismatched Job scope, mismatched Appointment, and foreign Asset
   relationship; verify rule, state, repair owner, and stable digest.
3. Historical-only: admit a safe unresolved Migration projection; verify it is
   `HISTORICAL_ONLY` and does not increment `blocks_new_operation`.
4. New work: create clean Customer → Location → Job → Appointment → Estimate → Invoice;
   verify no historical Migration completion is required.
5. Authorization: request catalog/summary without `COMPANY_AUDIT_READ`, in another
   Company, and outside authorized Branch scope; verify no protected identity leaks.
6. Recovery: interrupt scan, archive/correct a record, rerun, and verify stable results
   for unchanged evidence and a new digest/result after correction.

## Preview acceptance

- Sign in as a synthetic Company auditor and open **Management → Data Quality**.
- Confirm summary cards, textual status, horizontally bounded table, refresh behavior,
  empty state, loading state, forbidden state, and safe error copy at desktop, tablet,
  and practical phone width.
- Confirm source records cannot be mutated from the page.
- Confirm a second synthetic Company cannot see the first Company's issue counts or IDs.
- Confirm no raw Migration row, contact destination, VIN/serial, Payment instrument,
  Payroll data, secret, or document content appears.

## Owner review and source gates

Owner review is limited to Customer survivorship/duplicate disposition and any source
authority conflict without an established winner. Source gates are protected Migration
identity/HOLD projections, domain-owned stale commercial projections, Payment
reconciliation evidence, Employee identity disposition, and policy-dependent Workforce,
Fleet, warranty, and Agreement readiness. None is silently converted into invalid fact.

No schema migration is required: the feature reads existing authoritative constraints
and projections. Production and Preview deployment remain Enterprise-owned.
