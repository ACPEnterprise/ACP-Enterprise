<!-- markdownlint-disable MD013 -->

# ADR 0005: Adopt ACP Internal Accounting as the Operational System of Record

- **Status:** Accepted
- **Date:** 2026-08-13
- **Decision owners:** Owner and Finance governance
- **Supersedes:** [ADR 0001](0001-platform-vision.md) only where it retains
  QuickBooks as the operational accounting system of record

## Context

ADR 0001 deliberately deferred internal accounting while ACP replaced Housecall
Pro. The owner has now approved a separate, control-gated objective: ACP internal
Accounting becomes the operational accounting system of record, targeting
2026-08-21. The date never overrides balancing, reconciliation, security,
independent Finance approval, Preview, Production, rollback, or cutover gates.

## Decision

After an independently accepted cutover, ACP owns the general ledger, accounts
receivable, accounts payable, invoices, payment/refund accounting, customers,
vendors, inventory financial control balance, tax liabilities, bank/cash
accounting and reconciliation, summarized payroll accounting, and financial
reporting. QuickBooks receives no new routine entries and becomes an immutable,
read-only historical archive. Emergency reopening requires explicit incident
authority.

External payment, payroll, banking, and tax-filing providers may execute their
specialized services. They do not own ACP's accounting records. Day 1 uses
validated opening balances, required open items, and a checksummed QuickBooks
archive; it does not recreate all historical transactions.

The [Day-1 control contract](../accounting/day-1-control-contract.md),
[implementation packets](../accounting/implementation-packets.md), and
[QuickBooks exit contract](../accounting/quickbooks-exit-contract.md) are
normative for this decision.

## Governance

- `FINANCE_PREPARER` prepares mappings and reconciliation evidence. The owner
  holds this role for the cutover program.
- `INDEPENDENT_FINANCE_APPROVER` verifies the completed financial package. The
  owner's external accountant/CPA holds this role and needs no repository,
  Codex, Preview, Mission Control, or development access.
- The same identity cannot satisfy both roles at the final financial gate.
- The owner remains the distinct final business and cutover authority.
- Accounting rollback after activation requires joint owner and independent
  Finance approval and never erases posted evidence.

## Consequences

The QuickBooks-handoff interpretation of `ACC.1` and `ACC.2` is superseded. New
accounting runtime, migrations, import tooling, rehearsal, Preview, Production,
and cutover work remain separately authorized milestones. No milestone state or
calendar deadline constitutes deployment or cutover authority.

Advanced bank feeds, native payroll, automated tax filing, full historical
migration, advanced perpetual costing, fixed-asset automation, budgeting,
consolidation, and advanced profitability may follow after cutover.
