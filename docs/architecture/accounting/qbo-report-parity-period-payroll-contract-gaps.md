# Accountant close projection handoff

Date: 2026-10-03

Protected authority: `e703c7b6210c62c99d2e69c44ecb0c70e09f9bc9`

The operator workspace consumes current ACP financial statements, QBO source
report custody, governed QBO application exceptions, Accounting period status,
and Payroll review surfaces. It does not compute parity or close readiness in
the browser.

## Financial-report parity

Provide a Company/Branch-scoped comparison projection for Trial Balance, Income
Statement, Balance Sheet, General Ledger, A/R Aging, A/P Aging, Cash Flow, and
Job Costing. Each result must bind the same report definition, accounting basis,
currency, period/cutoff, and evidence versions before returning:

- ACP total and evidence reference;
- QBO/source total and evidence reference where admitted;
- difference, or `null` with an explicit reason;
- source as-of and acquisition time;
- completeness and reconciliation state;
- line/account drill-down references to journal, posting, business transaction,
  and source evidence.

The browser must not parse provider report rows or subtract totals with different
cutoffs.

## Unified accountant review queue

Provide a read-only union projection over accepted domain queues. It should
preserve the owning domain, stable exception identity, operator-safe subject,
status, responsible role, period/cutoff, evidence as-of, normal destination,
and version. Initial families are opening/equity, A/R, A/P, Payroll liabilities,
Banking/Cash Flow, Inventory/Job Cost, and period-close blockers.

Only source-owned transitions may change `OPEN`, `READY_FOR_REVIEW`, `RESOLVED`,
or `APPROVED`. The aggregator must not manufacture a shared lifecycle.

## Period close

The existing Accounting period lifecycle can begin and close a period, and the
server enforces a balanced Trial Balance, distinct Finance approver, and an
evidence digest. Before presenting close controls, add a projection such as:

`GET /api/v1/accounting/periods/{period_id}/close-readiness`

It must return unresolved blockers, required reconciliation families, accepted
evidence digests and versions, report-review state, requester/reviewer-safe
display identities, and `can_begin_close` / `can_close` decisions. The close
command should accept only the current version and the server-issued readiness
identity/digest. The browser must not accept or reconstruct an evidence digest,
assert `controls_reconciled`, or supply an internal approver identity.

## Payroll accounting review

Payroll currently exposes register/liability totals, opening/YTD readiness,
bridge certification, and release/settlement evidence. Add a read-only Payroll
Accounting reconciliation projection that binds:

- Payroll run/register version and digest;
- employee withholding, deduction, employer liability, and net-pay totals;
- settlement/remittance state;
- opening/YTD evidence completeness;
- canonical Accounting journal/posting references where they exist;
- register-to-posting differences and exact exceptions;
- cutoff, currency, completeness, and responsible reviewer.

No Payroll calculation, settlement, or Accounting posting should be initiated
from the comparison workspace.
