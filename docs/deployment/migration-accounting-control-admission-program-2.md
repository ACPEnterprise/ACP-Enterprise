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

## August 31 cutoff packet reconciliation

The complete owner packet is registered immutably under
`qbo-cutoff-control-packet-2026-08-31-v1`. The Accrual Trial Balance, Open
Invoices, and Customer Balance Detail agree at 479,029.48. They differ from the
previously accepted A/R Aging Detail net of 479,879.48 by -850.00. The variance
is preserved as an exception; AR is not admitted by forcing either control to
the other.

A/P Aging Detail, Unpaid Bills, and Vendor Balance Detail contain no numeric
items. Together with no nonzero A/P control observed in the Accrual Trial
Balance, this supports a zero-A/P candidate, subject to accountant confirmation
that the reports used the intended scope and filters.

Workbook-embedded metadata also proves that three requested files were exported
in the wrong basis: `Trial Balance cash` and `Balance Sheet` say Accrual, while
`General Ledger` says Cash. Their original registrations remain immutable, but
the successor packet marks each `REJECTED_BASIS_MISMATCH`. The Cash Profit &
Loss is accepted. No legitimate Cash/Accrual difference is treated as an error.

## Legacy control gap register

| Control | Historical state | Cutover treatment |
|---|---|---|
| Undeposited funds | `LEGACY_CONTROL_NOT_MAINTAINED` | Reconstruct only settlement-linked items proven by evidence; otherwise obtain an accountant opening control and `START_NATIVE_AT_CUTOVER` |
| Company credit cards | `LEGACY_CONTROL_NOT_MAINTAINED` | Obtain an accepted balance per admitted card; preserve Purchase, liability, settlement, and bank outflow as separate facts; `START_NATIVE_AT_CUTOVER` |
| Inventory valuation | `LEGACY_CONTROL_NOT_MAINTAINED` | Do not derive value from Items or Purchases; require physical quantity plus accepted cost basis, or classify not applicable; `START_NATIVE_AT_CUTOVER` |

Native ACP must maintain funds-in-transit lifecycle, card statement/liability
reconciliation, and prospective inventory quantity/cost/custody movements from
the accepted cutover boundary. Historical absence is evidence, never permission
to fabricate balances.

The consolidated next evidence packet is limited to corrected exports of the
Cash Trial Balance, Cash Balance Sheet, and Accrual General Ledger. No repeat of
the already accepted controls is required.
