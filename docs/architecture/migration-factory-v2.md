# Migration Factory V2 qualification

## Boundary

The core accepts only a validated `ProviderKey`, immutable evidence, normalized
records, crosswalks, versioned field authority, reconciliation, and certification.
Provider names, authentication, resource catalogs, and payload semantics live in
registered adapters. Adapters deliberately expose discovery, full reads, and delta
reads; there is no source-write method.

The normalized staging catalog covers company, customer, location, workforce,
jobs/dispatch, commercial documents, inventory, accounting, time, payroll,
benefits, tax configuration, and payroll YTD state. A normalized record always
points to immutable raw evidence and a transformation version. Multiple adapters
may contribute fields to one canonical identity; a versioned field authority rule
selects a value and conflicts preserve both candidates.

## QuickBooks access matrix (official documentation checked 2026-11-18)

| Migration need | Publicly documented resource | Scope | Access boundary | Fallback |
|---|---|---|---|---|
| Accounting | QBO Accounting REST API | `com.intuit.quickbooks.accounting` | Current All County grant | provider reports/files |
| Compensation/pay types | `Payroll_EmployeeCompensation` GraphQL | `payroll.compensation.read` | Silver+ Premium API; production keys; no sandbox | payroll configuration export |
| Employee/employment history | `WorkerManagement_Employee` GraphQL | `qb.employee.read` | approved partners; Silver+ prerequisite; production only | employee/configuration export |
| Benefits/deductions | Payroll employer/employee benefits GraphQL | `qb.payroll.benefits` | approved partners; production only | deductions/contributions export |
| Payroll runs/pay slips | Workforce payslip resources | A public exact least-privilege scope was not confirmed | approved-partner documentation required | Payroll Details/paycheck export |
| Tax/withholding elections | sensitive Workforce employee resources | resource-specific restricted scope; tax identifier example is `qb.employee.taxidentifier.read` | additional legal agreement and manual onboarding; do not request tax identifier unless indispensable | employee withholding configuration/signed W-4 |
| Complete YTD bases/taxes | no complete public API contract confirmed | none claimed | partner confirmation required | prior-period Payroll Details and Tax/Wage Summary ending before target payroll |
| Time | Accounting `TimeActivity`; compensation IDs from Payroll Compensation | accounting plus `payroll.compensation.read` when pay type is required | Silver+ for compensation; Workforce coverage is not implied by Accounting | QuickBooks Time/report export |

Intuit recommends incremental consent: adding scopes requires a new authorization
flow and new tokens. V2 retains grant history by tenant/provider and stores only a
token reference, company digest, scopes, and authorization digest in the Migration
Factory database. Token material remains encrypted/secret-managed. The deployment
allowlist defaults to Accounting, so no restricted scope is enabled by this change.

Minimum owner action: in the Intuit Developer Workspace, upgrade/request Silver,
complete the app assessment, then request approved-partner access only for
`qb.employee.read` and `qb.payroll.benefits`, plus
`payroll.compensation.read`. Ask Intuit to identify the current least-privilege
read scopes for payslip history, withholding elections, and complete YTD state
before enabling them. After Intuit approves each scope, add it to the deployment
allowlist and have All County reauthorize incrementally. Until then use automated
read-only exports. Do not request tax-identifier access merely for migration.

## ServiceTitan adapter prerequisites

- Register a ServiceTitan app, add target tenant IDs, and select only read scopes.
- Obtain an app key plus environment-specific client ID/secret after the tenant
  admin grants API Application Access; use OAuth 2 client credentials.
- Qualify each CRM, settings, JPM, dispatch, sales, pricebook, accounting, and
  inventory resource against integration and then a consented production tenant.
- Confirm historical depth, pagination totals, rate limits, and webhook availability.
  Current official guidance says new subscriptions to existing webhooks are
  restricted while V2 webhooks are being developed, so polling/backfill drift
  detection remains mandatory.

## Jobber adapter prerequisites

- Create a Developer Center app and configure least-privilege read scopes.
- Implement OAuth 2 authorization code flow with state and PKCE S256, secure token
  rotation, dated GraphQL version headers, cursor pagination, and `APP_DISCONNECT`.
- Use a dedicated test account and certify clients, properties, users, jobs, visits,
  quotes, invoices, payments, products/services, and time sheets independently.
- Jobber approval is required to connect a custom integration to more than five
  paying accounts; marketplace publication additionally requires App Review.

Provider certification is domain-specific. OAuth success alone never marks a
provider or a migration certified.

## All County safety result

All County remains Accounting-only for QBO. The sealed 2026-08-28 payroll answer
key was not accessed. Existing immutable HCP, QBO, and owner-file evidence can be
registered through their adapters when count and digest completeness is proven.
No source writes are present in the adapter contract and none were performed.
