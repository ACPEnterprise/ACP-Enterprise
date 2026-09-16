# Customer history real-world acceptance

## Authority and scope

- Protected base: `90af57abf5f4e2dbda75ed2680d4d420eb60410c`
- Candidate: `work/customer-history-realworld-acceptance-1`
- SOURCE.4 Customer UPDATE evidence remains outside this acceptance. No successor binding or Migration classification is created or changed here.
- Customer history means records admitted to native ACP domain authority. Source-only history that has not been admitted is `SOURCE_HISTORY_NOT_ADMITTED`, not an empty or zero result.

## Operator contract

The Customer roster supports paginated Company-scoped search across Customer name/number, Contact name/email/normalized phone, and Service Location address/city/postal code. Customer detail labels the record as a native ACP Customer and labels `customer.source` only as a marketing source, not Migration provenance.

The detail workspace exposes admitted Contacts, Service Locations, current and historical Jobs, bounded Appointments, Estimates, open and historical Invoices, customer-scoped Payment receipts, AR evidence classifications, and the Customer event timeline. Every bounded section states its page/time limit. Missing sections and unavailable source evidence are not presented as none or zero.

Historical Job navigation carries a validated same-origin Customer return path. External or malformed return targets are ignored.

## Authenticated Preview close test

Run with an existing supported owner/office Preview session. Do not place credentials or session tokens in commands, output, screenshots, or this packet.

1. Open Customers and record the displayed population/readiness metadata and as-of state.
2. Search a known admitted Customer by name without using a UUID; confirm the correct Company-scoped result.
3. Repeat with a normalized phone fragment and a Service Location address fragment.
4. Open the Customer and confirm the `Native ACP Customer` label, marketing-source clarification, archive/duplicate indicators, Contacts, and all admitted Locations.
5. Confirm current and historical Job counts and section boundaries. Open one historical Job, then use `Back to Customer`; confirm the same Customer context returns.
6. Confirm Appointments and their stated one-year-before/after boundary. Open one Appointment and return.
7. Confirm Estimates and Invoices link to their authoritative detail surfaces.
8. Confirm Payment receipts belong to this Customer and distinguish captured, applied, and unapplied amounts. Open one receipt and return.
9. Confirm AR classification and as-of evidence distinguish current native evidence from historical, stale, partial, conflicting, or unavailable source evidence.
10. Confirm the activity timeline paginates and does not imply it contains unadmitted source history.
11. Exercise a Customer with multiple Locations and a Customer with incomplete admitted history. Confirm missing history is described as incomplete/unavailable, never as zero.
12. Temporarily exercise an API failure through the accepted test mechanism and confirm safe partial/error messaging and recovery without raw backend errors.

## Current gate

Laptop1-B had no supported authenticated Preview session during qualification. Preview health was reachable, while the Customer API correctly returned unauthenticated. Therefore fixture-backed product behavior is qualified, but the named real admitted Customer close test remains pending authenticated Preview execution. Any source-only history absent after that run is classified `SOURCE_HISTORY_NOT_ADMITTED` and requires separate Migration admission evidence.
