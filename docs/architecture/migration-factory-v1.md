# TwelveHats Migration Factory v1

Migration Factory treats each connected provider as a collection of independently
discoverable domains. A successful Accounting acquisition never implies Payroll,
Time, Workforce, or any other domain is complete.

The durable pipeline is `immutable raw evidence -> normalized source record ->
identity/crosswalk -> versioned field authority -> canonical TwelveHats entity`.
Canonical entities retain source lineage; conflicts retain every source candidate and
enter an actionable exception queue. No adapter in this boundary exposes source
create, update, delete, Payroll execution, payment, or filing operations.

Every tenant starts with all 28 domains at `NOT_DISCOVERED`. State can advance through
provider/API/report/file availability, acquisition, normalization, reconciliation and
certification. Provider counts must equal received plus quarantined plus rejected
records before acquisition can close. A malformed record is quarantined while later
pages continue. Page checkpoints, response digests, high-water marks and a unique
terminal page prove pagination and permit retry-safe resume.

Raw source records are append-only and digest-bound to Company, provider, object type,
native ID, source/acquisition timestamps, payload reference, API version, authority,
batch and page. Versioned authority rules decide precedence per domain and field;
there is no global “QBO wins” or “HCP wins” rule.

After the initial snapshot, provider webhooks are hints. A durable per-source cursor
and periodic CDC/backfill comparison close webhook gaps. Tenant-scoped run and page
idempotency keys, isolated queues, bounded provider backoff, quarantines, exception
counts, calls-per-migration and API-cost telemetry allow one migration to fail without
stopping another.

The owner projection contains only: Connect QuickBooks, Connect Housecall Pro,
optional upload when a provider lacks a field, domain progress, actionable exceptions,
approval and cutover. Engineering states remain operational evidence.

## All County current boundary

Repository-enforced Intuit authorization is exactly
`com.intuit.quickbooks.accounting`. It covers the existing Accounting REST catalog,
including generic Employee and TimeActivity objects, but does not establish Payroll
Compensation, Workforce Employee, payslip, tax-election, deduction, sensitive Payroll,
or QuickBooks Time coverage. The 2026-08-28 Payroll answer key remains sealed.

All County must reacquire or supplement employment history, compensation/effective
dates, pay frequency, Payroll time, earnings/pay types, commissions/reimbursements,
W-4/FICA/jurisdictions, deductions/benefits/contributions, historical runs/paychecks,
YTD wage/tax bases, FUTA/SUTA configuration and Payroll liabilities. Provider API is
preferred; supported reports or files are imported when provider access is absent.
