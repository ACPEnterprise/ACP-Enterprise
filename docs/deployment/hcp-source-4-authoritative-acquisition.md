# HCP.SOURCE.4 authoritative acquisition

HCP.SOURCE.4 executed a bounded, read-only acquisition on 2026-08-27. Raw
provider payloads, controls, native identities, and crosswalk evidence are in
the protected Migration evidence area; none are stored in Git. The history
cutoff is an analytical and reconciliation policy, not an extraction filter.

## Sealed scope

The protected collection contains 5,253 Customers, 7 Employees, 5,801 Jobs,
1,307 Estimates, and 5,756 Invoices. Every top-level collection has complete
page checksums and unique native identities. The existing sealed controls and
their original lineage remain unchanged. Forty-three customer identities
referenced by source objects but omitted by the Customer list endpoint were
all recovered by exact native-ID detail requests.

Pre-2023 objects remain `LEGACY_HISTORICAL_ARCHIVE`. Missing pre-2023 payment
controls remain `historical_pre_plumbing_control_gap`; they do not block
acquisition or migration unless an object carries into a current balance or
open relationship. Objects from 2023 through cutover are primary analytical
history. Current/open objects remain Day-1 disposition scope.

## Job and estimate crosswalks

The Job control contains 4,816 distinct exported Job numbers. All match an API
Job native identity and all have at least one non-number corroborator: amount,
address, created date, or scheduled date. The 985 API-only Jobs are 799
`pro canceled` and 186 `user canceled`: 65 legacy, 621 analytical-history, and
299 Day-1-significant. Of the Day-1 group, 296 report a nonzero outstanding
balance. This is complete acquisition with explicit control omission, not
proof that the source records are wrong. Those 299 require owner/accounting
disposition before cutover.

The Estimate control matches 1,306 API Estimate numbers. Of these, 1,304 have
non-number corroboration; two remain number-only `PARTIAL`. One API Estimate
created after the control export is `CONTROL_EXPORT_MISSING`. Native Job and
Estimate IDs remain authoritative and exported numbers remain corroborating
source assertions; neither is rewritten.

## Payments and other relationships

Invoices contain 4,308 payment assertions with native payment IDs and 28
refund assertions, 12 with native refund IDs. For 2023+, the API contains
2,337 payments and controls contain 2,316 rows. Date-plus-amount multiset
comparison matches 2,185; 1,862 are unique on that evidence key. There are 152
API-only and 131 control-only assertions under that comparison. Private control
Job/Customer IDs do not equal public API native IDs, and invoice-number linkage
is incomplete. Payment acquisition is therefore complete as source evidence,
while payment-application and unapplied-amount reconciliation stays `PARTIAL`
or `ABSENT`; no applications are invented.

Appointments were probed through the supported per-Job GET relationship for
all 3,950 Jobs classified as 2023+ analytical or Day-1 state. It returned 3,219
appointment records across 3,030 Jobs; 920 Jobs returned HTTP 400 and remain
explicitly `PARTIAL`. Primary schedule fields remain in every Job payload, so
the endpoint limitation does not erase source scheduling evidence. Job notes
are source-faithful but lack
author/timestamp provenance where the API omits it. Attachment coverage remains
partial and content retrieval is deferred to records selected by
HCP.OPEN-WORK.1. Business Units remain source evidence and are not automatically
equated to ACP Branches. Employee native identities and assignments are ready
for an owner-approved Enterprise Employee crosswalk.

## Readiness boundary

Source acquisition is complete. The following are cutover/import dispositions,
not acquisition defects: the 299 Day-1-significant canceled/control-omitted
Jobs (296 with balances), employee mappings, required open-work attachments,
Business Unit-to-Branch decisions, payment assertions affecting current
balances, and the final HCP.OPEN-WORK.1 freeze.

The next bounded milestone is **HCP.MIGRATION.1 — owner-authorized
non-production transformation, reconciliation, and Day-1 disposition
rehearsal**. It must consume sealed source envelopes without mutating them.
Enterprise operational persistence, Preview mutation, and Production mutation
remain outside HCP.SOURCE.4 authority.
