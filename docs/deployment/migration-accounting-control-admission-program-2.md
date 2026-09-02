# Accounting control admission program 2

This is a successor readiness packet. It preserves QBO G1-G5, the bounded G5
snapshot, the completed HCP master, Full Available History, the Cash-basis
policy, prior control packets, and every existing HOLD/disposition. It does not
authorize posting, source mutation, source freeze, or Production activation.

## Accepted transition authority

The current QBO environment began on 2024-02-19. The Audit Log records 6,909
Import Administration events in the bounded setup window and one QuickBooks
Desktop company import. Historical transactions retain their effective dates
and import provenance.

The 2024-02-19 Accrual Trial Balance contains 55 account rows and balances at
156,960.94 debits and credits. The Cash-basis Balance Sheet balances at
48,309.12 assets and 48,309.12 liabilities plus equity. The figures are not a
variance: Trial Balance debit/credit turnover and a Balance Sheet net position
are different control presentations. Neither transition report contains an
Opening Balance Equity balance.

| Opening component | State | Consequence |
|---|---|---|
| Ledger transition | Accepted | Balanced account state; no fabricated opening journal |
| Historical Cash position | Accepted | Cash-basis transition continuity |
| Operational AR | Aging accepted; ledger tie required | Open items preserved; no ledger admission yet |
| Operational AP | Control required | Empty API Bill families do not prove zero |
| Bank/cash | Account-level control required | Deposits and Payments do not prove balances |
| Credit cards | Account-level control required | Purchase and later settlement remain distinct |
| Undeposited funds | QuickReport required | Clearing is not revenue |
| Other liabilities/equity | Accountant classification required | Aggregate transition balance is controlled; mapping is not |

## Chart of Accounts

The source packet contains 130 accounts. Thirty-eight are mechanically
classified under the existing provider-type rules; 92 retain
`OWNER_ACCOUNTANT_DECISION`. Aggregate Trial Balance and Balance Sheet evidence
cannot safely reduce those 92 because it does not decide account purpose,
control designation, statement grouping, tax/Payroll treatment, or future ACP
posting policy. The Day-1 recommendation remains: preserve the evidenced QBO
structure and stable identities; redesign only after cutover.

## Authority and double-count boundaries

- HCP remains authoritative for operational Job/Scheduling/Estimate evidence.
- QBO is the controlled source for ledger, application, settlement, AR/AP, and
  account history only after the relevant controls reconcile.
- ACP-native Accounting authority begins only after admission.
- Business Economics remains separate accepted earned-work/cost authority.
- Invoice is not cash; Payment is not a second revenue event; Deposit is not
  automatically revenue; card payment is not a second purchase; Transfer is
  not income/expense; Journal lineage may not duplicate its source transaction.

## Preserved unresolved populations

- 296 canceled-Job balance assertions remain HOLD. The transition reports add
  no cross-provider identity capable of admitting them to AR.
- 24 unlinked Estimates remain evidence-only. No Job relationship is inferred.
- Six Employee candidates still require owner confirmation; one zero-assignment
  identity remains recommended for `EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS`.
- Branch `887f413a-70dc-4ab1-98aa-8e84f4e7efd0` remains the owner-confirmable
  live candidate; labels alone do not bind it.

## Readiness

Dependency-safe preparation is complete through the transition controls.
Population accounting and replay authority are unchanged. Accounting admission,
combined rehearsal completion, freeze readiness, and go/no-go remain blocked by
cutoff subledger/account controls and genuine Owner/Finance decisions.

The registered **Accounts Receivable Aging Detail** as of 2026-08-31 contains
162 rows across 115 customers: 96 Invoices, 62 Payments, and 4 Deposits. Invoice
open balances are 566,442.39; Payment and Deposit rows provide negative
applications/credits, producing a reconciled report net of 479,879.48. No row
has a transaction date after cutoff. The difference from the previously
observed current-source balance is preserved as a time/version variance, not
forced to zero.

The single next evidence item is an **Accrual Trial Balance as of 2026-08-31**.
It must tie the accepted aging net to the Accounts Receivable control account.
