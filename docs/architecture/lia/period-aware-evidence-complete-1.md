# LIA Period-Aware Evidence Complete 1

## Contract

`LiaTemporalContext` binds `start_date`, `end_date`, `as_of`, Company timezone,
and a user-facing period label. It can bind a second comparison period and a
bounded immediately prior period for explicit follow-ups such as “What about June?”
then “Compare them.” Evidence references carry the applied dates, label, timezone,
and Accounting basis where relevant. Periods form part of deterministic evidence
digests.

Changing the period clears the previous evidence digest. The new period is queried
again under current authorization; evidence from the prior period is not silently
reused.

## Authority matrix

| Domain | Supported period authority | Explicit limitation |
| --- | --- | --- |
| Scheduling | Appointment arrival-window overlap in Company timezone | Absence does not prove technician availability; undated Needs Scheduling cannot be placed in a date |
| Dispatch | Assignment-window overlap | No reconstruction of historical “active at that instant” state |
| Customer | None in the minimum-necessary current projection | Customer history needs a source-owned dated projection |
| Job | None in the generic current-state projection | Completion/event history needs a source-owned dated contract |
| Estimate | Creation timestamp | No historical expiration-transition or conversion inference |
| Invoice | Invoice issue date | Current open/paid status is not a historical month-end status |
| Payment | Receipt capture timestamp | Capture is not settlement, collected income, or revenue |
| Financial Reports | Existing native income-statement engine for exact dates | Requested basis must equal the admitted Accounting basis; LIA never builds a replacement report |
| Payroll | Exact authoritative PayPeriod identity and read-only operations projection | No inference of past readiness from current readiness; values remain protected |
| Timekeeping | Accepted revision work date | Accepted work is not automatically paid Payroll time |
| Economics | Exact admitted result period | No LIA recomputation and no interpolation between periods |
| Luminary | Exact persisted briefing period | No substitute briefing from another period |
| Beacon | Persisted evaluation dispositions over an explicit Company/Branch-scoped period | Evaluation history explains recorded new/changed/resolved/expired outcomes; it does not reconstruct an unrecorded timeline or replace current lifecycle state |
| Migration | Master-run execution overlap and source timestamps | Run time does not prove source freshness beyond admitted evidence |

## Financial semantics

LIA delegates native income statements to `FinancialReportingService`. Report
manifest basis, currency, checksum, integrity, and period are preserved. A cash
request against an accrual-only reporting context fails with a natural basis-mismatch
explanation. Invoice issue dates, current balances, receipt capture, revenue, income,
and accounts receivable remain distinct.

## Safety

- No current-state response is filtered client-side and relabeled historical.
- Unsupported historical state returns `PARTIAL`/`INCOMPLETE` with the owning gap.
- Comparison executes two independently bounded authoritative retrievals.
- Company, Branch, entity, and permission predicates remain server-side.
- No report, Payroll, Economics, Scheduling, or Dispatch mutation exists here.
- No external provider or Production operation is used.

## Deterministic acceptance

The suite contains 200 text/voice temporal variants covering explicit dates,
months, ranges, weekdays, relative periods, corrections, comparisons, Scheduling,
Dispatch, Customer/Job history, Estimates, Invoices, Payroll, Timekeeping,
Financial Reports, Economics, Beacon, Migration, unsupported history, and
authorization. Focused tests also prove period changes do not reuse stale digests,
comparison periods are retrieved separately, and unsupported state fails before
current evidence retrieval.
