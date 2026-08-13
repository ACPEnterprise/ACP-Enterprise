<!-- markdownlint-disable MD013 -->

# Internal Accounting Day-1 Control Contract

## Authority and effective boundary

This contract implements [ADR 0005](../adr/0005-internal-accounting-system-of-record.md).
The target QuickBooks operational close is 2026-08-20. ACP's target effective
instant is 2026-08-21 00:00 `America/New_York`, only after every required gate
passes. Until activation, existing source authority remains unchanged.

At activation ACP is authoritative for GL, AR, AP, invoices, payment/refund
accounting, customers, vendors, inventory financial control, tax liabilities,
bank/cash accounting and reconciliation, summarized payroll accounting, and
financial reporting.

## Approved policy baseline

- Match the current QuickBooks book basis exactly; never change basis during
  migration.
- Adopt the active QuickBooks chart of accounts and preserve stable source
  account identities. Do not redesign it during cutover.
- Establish opening balances plus required open items and retain an immutable
  historical archive. Full historical-detail migration is excluded.
- Include vendors, open bills, credits, balances, AP aging, and controlled
  disbursement recording.
- Retain the current payment processor. ACP owns application, refunds, failures,
  deposits, clearing, undeposited funds, and settlement reconciliation.
- Retain the payroll provider. ACP owns summary journals and payroll
  liability/accrual balances.
- Preserve current tax rules. ACP owns calculated liabilities and accounting;
  filing/remittance may remain external.
- Use an opening inventory asset/control balance and controlled periodic
  valuation adjustments. Advanced perpetual costing is deferred unless a later
  accepted architecture proves it mandatory.
- Permit statement, CSV, and controlled manual bank reconciliation. Automated
  feeds are deferred.

## Required capabilities and invariants

Day 1 requires an active COA; balanced double-entry GL; immutable posted
journals; controlled reversal; periods and posting controls; AR and AP
subledgers and aging; invoice, tax, credit, void, adjustment, payment, refund,
failure, deposit, clearing, and undeposited-funds accounting; bank/cash
reconciliation; tax liabilities; inventory-control and payroll-summary journals;
idempotent event posting; trial balance, balance sheet, income statement, GL
detail, AR aging, and AP aging; Company/Branch isolation; Finance separation of
duties; audit and close controls; backup/rollback; and deterministic opening-state
import and reconciliation.

Every posted journal has stable source identity, effective date, period,
currency, balanced debit and credit totals, immutable lines, actor/evidence, and
reversal linkage. Posted evidence is never edited or deleted. Corrections use a
reversal and replacement where policy permits. Closed periods reject posting
unless an explicitly authorized reopen is independently evidenced.

Cross-domain modules publish facts or call an Accounting-owned application
contract. They never write Accounting tables. Accounting owns account mapping,
posting rules, journals, periods, subledger/control reconciliation, and financial
statements. Consumer projections cannot become financial authority.

## Finance separation of duties

`FINANCE_PREPARER` may prepare mappings, imports, reconciliation workpapers, and
the cutover package but cannot provide independent final approval.
`INDEPENDENT_FINANCE_APPROVER` may accept or reject the immutable rehearsal and
cutover package but cannot prepare it or mutate source/runtime records. Final
approval requires different identities plus separate owner authorization.

## Gates

Implementation requires focused accounting invariants, idempotency, concurrency,
authorization, tenant isolation, audit, statement, migration, downgrade/re-upgrade,
and one-head validation. Preview requires separate authorization, backup/restore,
production-shaped rehearsal, and zero unexplained control variance. Production
deployment and cutover each require separate owner authority. Any unexplained
variance, unbalanced journal, ambiguous source authority, missing Finance
approval, or unsafe rollback blocks activation.

## Deferred after cutover

Full historical-detail migration, automated bank feeds, native payroll and tax
filing/remittance, advanced perpetual costing, fixed-asset automation, budgets,
forecasting, custom statements, multi-company consolidation, and advanced
profitability are not Day-1 dependencies.
