# Customer history product operations complete 2

## Authority

- Starting protected authority: `bae55401586e48e4b606604c3aac1eeef4832a27`
- Prior Customer history candidate: `0efbf607de87e84df22a5c0c3aca8c643901912e`, semantically carried into this candidate
- SOURCE.4 Customer UPDATE audit: `BLOCKED_EVIDENCE_TRANSFER`

Migration remains authoritative for acquisition, identity, classification, and admission. This product consumes only records already admitted into native Customer, Location, Job, Scheduling, Estimate, Invoice, and Payment authority plus the accepted Customer-scoped financial evidence classification contract.

## Operator behavior

Customer search remains paginated and Company-scoped across Customer name/number, Contact name/email/normalized phone, and Service Location address/city/postal code. Multiple exact results remain separate records. Archived state is explicit; no search result is merged heuristically.

The default roster remains current-only. An explicit Current/Archived/All control allows an authorized operator to find an archived Customer, inspect its immutable history, and reach the existing Restore action. Archived records are never silently mixed into the default result.

Customer detail now supplies:

- bounded counts for Locations, open Jobs, historical Jobs, Appointments, Estimates, Invoices, and Payment receipts;
- the latest admitted Job;
- a deterministic newest-first 50-item service timeline across authorized native domain projections;
- per-Location admitted Job and Appointment counts plus latest service evidence;
- explicit authority labels on every combined-history entry;
- a completeness panel that distinguishes complete native Customer identity from partial/bounded related-domain projections, classified source-backed financial evidence, unadmitted history, and unavailable contracts;
- explicit navigation from Customer to Location-filtered Jobs, Job, Appointment, Estimate, Invoice, Payment, and back to Customer.

The cross-domain timeline never transforms source evidence into native truth. Refund amounts are shown only on authoritative Payment receipts; no refund timestamp is invented when the receipt contract does not expose one.

## Boundedness and ordering

- Current Jobs: newest 25.
- Historical Jobs: newest 25.
- Appointments: at most 100 within one year before and after today.
- Estimates: authoritative Customer list contract.
- Invoices: at most 100.
- Payments: at most 100 newest receipts.
- Combined timeline: newest 50 of the already bounded projections, ordered by authoritative timestamp then stable domain identity.

The UI labels these limits and never describes them as the complete Migration population.

## Five-journey post-admission acceptance

Use supported authenticated Preview access after Enterprise integration and Migration admission. Select records by operator-visible name, phone, or address—never internal UUID or fuzzy identity inference.

| Journey | Required admitted evidence | Assertions |
| --- | --- | --- |
| 1. Complete historical Customer | Customer, Location, Job, Appointment, Estimate, Invoice, Payment | Search succeeds by name/phone/address; all links preserve the same Customer; amounts and statuses reconcile; every item names its authority. |
| 2. Multiple Locations | Customer with at least two Locations and historical work at each | Location cards remain separate; each Job belongs to the exact Location; latest-service evidence and counts do not cross locations. |
| 3. Open plus historical work | At least one current Job and one completed/cancelled Job | Open work is visually separate and actionable; historical work remains read-only history; Scheduling/Dispatch navigation uses the authoritative Job. |
| 4. Source-backed partial history | Native Customer with classified partial/stale/source evidence | Native and source-backed evidence remain distinct; unavailable history is not zero; exact as-of/classification language is visible. |
| 5. Missing commercial stage | Customer whose admitted chain omits Estimate, Invoice, or Payment | Missing stage is described as unavailable/partial, not zero, paid, or complete; remaining admitted navigation continues to work. |

For each journey record deployed SHA, Company/Branch, operator-visible search input, displayed source/as-of state, opened Customer/Location/Job/Appointment/Estimate/Invoice/Payment identities, return-navigation result, and any absent source stage. Do not mutate the Customer or source systems during acceptance.

## Exact upstream gaps

- The sealed SOURCE.4 Customer successor custody archive is not present on Laptop1-B, so its exact 20-record audit remains blocked.
- Migration must publish admitted real Customer/Location/Job/Appointment/Estimate/Invoice/Payment relationships before the five journeys can be executed truthfully.
- Customer-wide attachment completeness has no authoritative read contract.
- Job detail does not expose certified source-technician lineage, Jobsite Hours, commercial document/payment linkage, or attachment completeness through one accepted Job-history projection. Existing domain surfaces remain authoritative and were not duplicated here.
- The Customer-owned `CUSTOMER.LIA_CONTEXT.v1` contract is already bounded, permission-aware, and deterministic. It supplies Customer/Location/Job and Estimate/Invoice state evidence. Payment totals and history-completeness classifications are not yet part of that contract and remain a bounded successor contract gap rather than being inferred in this lane.

## Safety

No Migration classification, source/native binding, Preview data, QBO/HCP data, Accounting entry, Payment, communication, or Production system is mutated by this candidate.
