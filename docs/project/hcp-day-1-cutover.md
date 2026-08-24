<!-- markdownlint-disable MD013 -->

# Housecall Pro Day-1 Operational Cutover

## Authority and outcome

`HCP.CUTOVER.1` targets no new normal operational entry in Housecall Pro after a separately approved August 21, 2026 cutover. This document does not authorize Preview, Production, import, freeze, or cutover. Optional parity is excluded.

## Runtime-evidenced readiness matrix

| Capability | Class | Evidence and exact remaining gap |
| --- | --- | --- |
| Lead/customer/contact/service location | A — Day-1 ready | Customer APIs/UI, intake, contacts, locations, duplicate controls, Company/Branch authorization, and tests exist |
| Scheduling/cancel/reschedule | C → B in this packet | Backend lifecycle/API and appointment detail existed; `HCP.SCHEDULING.UI.1` adds the missing office calendar/list entry point; acceptance remains required |
| Dispatch/technician assignment | B | `DISP.2` runtime, workspace, permissions, events, and tests exist; requires integrated acceptance with TECH runtime |
| Technician mobile shell | B | `TECH.1` is owner-controlled on OM1; authoritative scheduler boundary exists, but no accepted technician runtime is present at this audit SHA |
| Field execution/notes/evidence/completion | D, runtime-ready except TECH.1 | `TECH.FIELD.CONTRACT.1` and `TECH.FIELD.READY.1` freeze the journey and packet; OPS.1, DISP.2, EST.4, and INVOICE.1-3.ACCEL are authoritative, leaving accepted/integrated TECH.1 as the sole initial-runtime dependency |
| Jobs and appointment relationship | A | Jobs APIs/UI, create-from-appointment, lifecycle, cancellation/reopen, authorization, and tests exist |
| Price Book | A | Price Book runtime/API/UI, activation, permissions, and tests exist |
| Estimates/customer approval | A | Estimate creation, immutable revisions, options/discounts/tax, presentation/approval, conversion, UI, and tests exist |
| Invoices/AR | A — Day-1 runtime authoritative | `INVOICE.1-3.ACCEL` is integrated at `43018e2`; `5f66495` preserves grandfathered invoice identities |
| Payments | D, contract ready | `PAY.CONTRACT.1` and its execution packet are authoritative, but no Payments runtime exists; it does not block initial TECH.FIELD.1 runtime and does block final payment-handoff acceptance |
| Communications/invoice delivery | B/C | Communications outbox/provider boundary exists; invoice/payment templates and end-to-end delivery depend on accepted Invoice/Payment facts |
| Accounting handoff | B | Accounting Core is authoritative at `ee87e57`; Invoice, Payment, posting, reporting, and cutover gates remain |
| Operational migration/cutover | B/C | Customer, location, job, appointment, estimate, invoice/payment source identities, history/artifact, dry-run, idempotency, and readiness foundations exist; real HCP source evidence, rehearsal, open-work reconciliation, and owner cutover authority do not |

## Minimum cutover data

Must exist in ACP: active customers and contacts; active service locations; open/in-progress jobs; future and in-flight appointments; dispatch/technician identity and assignment links; accepted estimates needed for open work; unpaid/open invoices and relevant receipt/application facts; notes, forms, and attachments required to perform or prove open work. Every imported entity retains stable source identity, Company/Branch scope, checksum/evidence, disposition, and relationship reconciliation.

Historical closed jobs, completed appointments, nonessential notes, old estimates, paid invoices, historical payments, and non-operational attachments may remain in an immutable HCP archive unless Finance or legal retention makes a specific item necessary.

Current migration V1 supports core operational identities plus history/artifacts, but technician/employee source mapping and the exact open-work selection/export contract require explicit acceptance. Attachments marked required for open work cannot be deferred. No scope expands silently.

## Freeze and transition

1. Complete Preview rehearsal and reconcile all open operational identities.
2. Announce a final HCP entry freeze no later than the owner-approved August 20 close window; emergency exceptions require a recorded disposition.
3. Take the final HCP export, record filters/timestamps/file sizes/SHA-256 checksums, and preserve it immutably.
4. Reconcile customers, locations, open jobs, appointments, assignments, estimates, open invoices, payments, required notes, and required artifacts exactly once.
5. Prevent duplicates with stable HCP source identity plus canonical source digest; exact replay is a no-op and changed replay fails closed.
6. Resolve in-flight appointments/jobs explicitly: complete in HCP before freeze, move to ACP with full state/evidence, or hold with owner disposition. No item is active in both systems.
7. Activate ACP only after operational smoke tests, Accounting authority, permissions, rollback, and owner go/no-go pass.
8. Make HCP read-only/archive. Roll back only for a critical integrity or operational failure under the approved runbook; preserve all ACP evidence and prevent unexplained dual entry.

## Laptop 1-A queue

1. `HCP.SCHEDULING.UI.1` — office daily schedule visibility; this packet.
2. `HCP.OPEN-WORK.1` — freeze the HCP open-work export/selection and relationship reconciliation contract; documentation/sanitized fixtures only, no import.
3. `HCP.REHEARSAL.1` — non-Production, separately authorized full-loop/open-work rehearsal after TECH, Invoice, Payment, and migration inputs are accepted.
4. `HCP.GO.1` — immutable operational go/no-go package after rehearsal; no Production authority.

## August 21 go/no-go

GO requires a physical mobile and office smoke test proving Customer → Schedule → Dispatch → Technician → Job → Estimate/approval → performed work/completion → Invoice → Payment → Accounting handoff; correct Company/Branch and role-negative tests; no duplicate or missing open work; all required HCP inputs checksummed and dispositioned once; zero unresolved relationship/control variance; tested rollback and support contacts; healthy Preview rehearsal; accepted Accounting gates; and separate owner Production/cutover authority.

Any unavailable required workflow, failed permission/tenant test, unresolved open-work item, unaccepted migration/financial control, missing rollback evidence, or need for dual normal entry is NO-GO. Feature parity is not a criterion.
