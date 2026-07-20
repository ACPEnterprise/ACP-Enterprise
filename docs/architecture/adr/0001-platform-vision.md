# ADR 0001: Replace Housecall Pro Before QuickBooks

- **Status:** Accepted
- **Date:** 2026-07-17
- **Decision owners:** Product and Engineering leadership

## Context

All County Plumbing & Leak depends on Housecall Pro for core home-service operations and on QuickBooks for accounting. Attempting to replace both systems in one release would combine operational workflow migration with accounting-system migration, significantly increasing scope, regulatory and financial risk, reconciliation complexity, training burden, and cutover risk.

ACP Enterprise needs a clear first mission against which architecture and product decisions can be evaluated. The organization obtains value sooner by controlling the daily customer and job lifecycle while continuing to use a mature accounting system during the operational transition.

## Decision

ACP Enterprise version 1.0 will replace Housecall Pro for All County Plumbing & Leak before ACP Enterprise attempts to replace QuickBooks.

Version 1.0 will own the operational workflow from customer intake through scheduling, dispatch, field execution, estimates, operational invoicing, and payment capture. It will integrate with or export to QuickBooks as necessary while QuickBooks remains the accounting system of record.

Full accounting capabilities—including the general ledger, accounts payable, bank reconciliation, financial close, and formal financial statements—are deferred to a separately planned release. Multi-company SaaS capabilities are later still.

## Consequences

### Positive

- The first release has a specific user, company, competitor, and measurable cutover outcome.
- Product and engineering can focus on operational reliability and adoption.
- Accounting risk is isolated from the Housecall Pro migration.
- Operational data and workflows can mature before they feed an internally owned ledger.
- The business receives value earlier and can validate the platform through daily use.

### Negative and required mitigations

- ACP Enterprise must maintain a reliable integration or reconciliation boundary with QuickBooks.
- Some financial data may temporarily exist in both systems, requiring explicit ownership and reconciliation rules.
- Users may continue switching systems for accounting workflows after version 1.0.
- Operational invoice/payment design must support future accounting depth without pretending that version 1.0 is a complete accounting system.

### Scope implication

A feature belongs in version 1.0 only if it is required to replace a Housecall Pro workflow, operate safely, support the cutover, or preserve the QuickBooks boundary. QuickBooks replacement and generalized SaaS administration require explicit roadmap approval.

## Alternatives considered

### Replace Housecall Pro and QuickBooks simultaneously

Rejected because it creates an excessively broad critical path and couples operational cutover to financial correctness. A defect could interrupt both customer service and accounting.

### Replace QuickBooks first

Rejected because accounting replacement does not address the immediate operational-system goal and requires mature source transactions that ACP Enterprise does not yet own.

### Build a generic multi-company SaaS product first

Rejected because generalized configuration, billing, and tenant administration would delay validation of the core workflows. The first company provides a concrete operating model from which reusable capabilities can be extracted.

### Continue extending existing products through integrations only

Rejected as the primary strategy because it leaves critical workflow, data ownership, and product evolution constrained by external platforms. Integrations remain a transition tool, not the destination.
