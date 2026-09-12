# Customer Office Workflow 1

## Authority and integration order

- Protected base after current-authority reconciliation: `d52d117801d72d04e81afac157671c97a941efa0`
- This increment is independent of Migration admission decisions.
- Integrate `work/customer-office-ux-reliability-1` (`5a662b93cdc89f17dac6285a53db254788de0994`) first or reconcile its source-readiness presentation with this branch. Do not amend that qualified candidate.

## Office navigation contract

Customer detail remains the context root. It links to:

- `/jobs?create=1&customerId={customerId}&locationId={locationId}` to create work with authoritative Customer and Location context;
- `/jobs?customerId={customerId}` for the complete paginated native Job population for that Customer;
- `/jobs/{jobId}` to inspect current or historical work and use the existing Job-owned scheduling panel;
- `/appointments/{appointmentId}` for accepted Appointment detail;
- `/scheduling` for Laptop1-A's Scheduling workspace without duplicating its implementation;
- `/estimates?id={estimateId}` for the linked Estimate;
- `/invoices/{invoiceId}` for Invoice detail;
- `/invoices?customerId={customerId}` for Customer-scoped Invoice/AR work, with a return path to Customer detail.

The Customer workspace uses customer-scoped Job, Appointment, Estimate, Invoice-workspace, and balance contracts. It does not infer relationships or calculate financial truth.

## Post-Migration authenticated Preview acceptance

Enterprise/OM2-C should run these cases after both Customer increments are integrated, deployed, and the accepted Migration admission packet is available. Use sanctioned authentication and approved non-Production records. Record the deployed SHA, Company/Branch, authoritative IDs, Migration packet identity/digest, source as-of date, native totals, and observed outcome.

1. One-Location Customer: open detail; verify Contact and Location identity; create-Job link carries both IDs; cancel before mutation if the dataset is not an approved synthetic fixture.
2. Multiple-Location Customer: verify every admitted Location is distinct; start Create Job from each Location and confirm the correct preselection.
3. Current-Job Customer: verify current work is separated from completed/cancelled history; open an unscheduled Job and confirm the existing scheduling control has the same Customer and Location.
4. No-current-Job Customer: confirm the explicit native-empty state and that historical work, if present, remains separately visible.
5. Historical-Job Customer: compare the displayed count to the customer-filtered paginated Jobs route; verify completed/cancelled Job navigation.
6. Scheduled Customer: open Appointment detail, then Scheduling, and return to the same Customer without manual search.
7. Commercial history: open each linked Estimate and verify Customer identity/revision; open each Invoice and verify Customer/Job lineage.
8. AR evidence: compare Customer detail balance, applied payment, unapplied receipt, invoice count, currency, and as-of date with the authoritative Customer balance endpoint. Do not equate provider receipt, cash settlement, or revenue.
9. Incomplete historical financial evidence: verify the warning remains visible and no native amount is labeled as complete source history.
10. Missing optional contact fields: verify stable explanatory text and no blank control or fabricated address/phone/email.
11. Partial related-domain response: fail one accepted deterministic API fixture at a time; verify Customer identity remains usable and missing relationships/amounts are not shown as none or zero.
12. Source truth: reconcile roster counts, held/deferred/conflict evidence, stale state, and as-of date to the accepted Migration packet. Held/source-only identities must not be selectable as native Customers.
13. Backend unavailable: verify safe errors, retry where supported, no raw exception/provider details, and no stale action masquerading as success.
14. Phone width: traverse Customer → Location → Job → Appointment/Scheduling → Estimate → Invoice/AR and back. Verify controls remain touch-operable with no blocking horizontal overflow.

No source mutation, real Customer communication, payment execution, Accounting posting, or Production operation is part of this checklist.

## Ownership notes

- Migration owns source identity, admission, conflicts, held records, and source completeness.
- Scheduling owns calendar and appointment scheduling behavior.
- Job owns lifecycle and the schedule-existing-Job command surface.
- Invoice/AR owns balance and payment-application evidence.
- Customer owns only Customer, Contact, Location, and Customer-scoped navigation composition here.
