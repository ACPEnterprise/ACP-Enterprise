# Historical read — OM2D / Product B handoff

## Stable contracts

Product consumers use `twelvehats-historical-read/v1` and
`twelvehats-accounting-report-read/v1`. Provider payloads, pagination, OAuth,
vault paths, and source-specific schemas remain behind Migration Factory.

Every returned historical record contains:

- domain and event timestamp;
- canonical ID when an exact binding exists;
- Customer and parent references;
- `NATIVE`, `SOURCE_BACKED`, `PROVISIONAL`, `DISCREPANCY`, or `QUARANTINED`
  authority;
- display-safe fields;
- provider, source object ID, acquisition/source timestamps, evidence digest,
  and transformation version;
- an explicit `aggregation_safe` flag.

Every response contains per-domain coverage. Missing or unavailable source data is
never represented as a zero count. Results are deterministically newest-first and
cursor-paged with a maximum requested page size of 500.

## Consumer API shapes

MASTER/Product B may expose the following routes without changing the contract:

- `GET /api/v1/customers/{customer_id}/history`
- `GET /api/v1/history/jobs`
- `GET /api/v1/history/estimates`
- `GET /api/v1/history/invoices`
- `GET /api/v1/history/payments`
- `GET /api/v1/accounting/source-reports`
- `GET /api/v1/accounting/source-reports/period`

Historical routes require `start_date`, `end_date`, Company authority, selected
domains, optional cursor, and bounded limit. Customer history must join only exact
canonical/source crosswalks. It may display unbound quarantined evidence only in an
authorized exception view, never under a guessed Customer.

## Domain requirements

Unified Customer history combines exact Customer, Location, Job, Appointment,
Estimate, Invoice, Payment, and Refund records while preserving each record's
authority. A source payment imported from QuickBooks remains non-aggregating until
QBO reconciliation resolves it. Refunds lacking provider IDs remain displayable
source evidence but cannot become authoritative financial actions.

Jobs retain exact Customer and Location parents plus provider identity/status and
source timestamps. Estimates retain options, line snapshots, status, amounts,
Customer/Location/Job relationships, and history-only or promotion disposition.
Invoices retain Job/Customer lineage, status, amounts, payments, and refunds.
Payments retain Invoice parent, native provider ID, overlap classification, and
aggregation safety.

Accounting reports expose registered immutable QBO report evidence with exact
kind, period/as-of, basis, raw and registration digests, source authority, and
limitations. A General Ledger period projection is not relabeled as a provider P&L
or as native TwelveHats accounting.

## Current retained-evidence boundary

HCP Customers (5,253), Employees (7), Jobs (5,801), Estimates (1,307), and
Invoices (5,756) have live acquisition qualification. Payment evidence contains
4,308 assertions; 152 API-only and 131 control-only comparison assertions remain
unresolved for cross-source application treatment. Refund evidence contains 28
assertions, of which 16 lack a native refund ID. Appointment evidence contains
3,219 returned records and 920 explicit HTTP 400 relationship failures. Attachment
history is unavailable from retained acquisition.

The HCP continuous-delta completeness and Estimate promotion planners now provide
exact per-source-ID dispositions for a future freeze packet; they do not mutate
canonical records.

QBO report projections are engineering-ready over sealed registered controls, but
this workspace has no configured protected QBO runtime/evidence root. Consequently
no additional Accounting API domain is promoted to live certification here.

## Data Master admission rule

Data Master may consume the contracts immediately. It must not advertise complete
history for a domain until coverage is `COMPLETE`, and it must preserve the
unresolved counts and explanations above. Provider evidence never overwrites
native transaction history or removes discrepancy provenance.
