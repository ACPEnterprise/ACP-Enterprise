# Native Accounting cutover decision packet — 2026-11-13

Status: `NO-GO FOR ACCOUNTING AUTHORITY CUTOVER`

This is one consolidated evidence and decision packet. It does not write QBO,
post native Accounting, execute Payroll, move money, or change accounting
authority.

## Proposed common cutoff

Proposed cutoff: **2026-08-31**, with Cash-policy continuity. The cutoff is a
proposal until Finance and the accountant approve it. All Trial Balance,
Balance Sheet, P&L, AR/AP aging, cash-flow, bank/card, and payroll-control
outputs must use the same approved cutoff and basis.

## Evidence-backed work already complete

- Existing native Accounting models, close controls, AR/AP, Payroll controls,
  opening controls, and QBO evidence application/review workflow are present.
- Historical reporting policy is Cash.
- Source activity begins 2022-01-01; ordinary non-transfer activity begins
  2022-01-03.
- The 2024-02-19 Accrual Trial Balance and Cash Balance Sheet are balanced and
  have no Opening Balance Equity balance.
- Corrected Cash Trial Balance and Cash Balance Sheet controls are balanced;
  corrected Cash TB debits and credits are both `1,283,400.24`.
- Corrected Accrual GL covers January 2022 through August 2026.
- Accepted Cash P&L covers 2022-01-01 through 2026-08-31.
- 2026-08-31 AR Aging is `479,879.48`.
- 2026-08-31 Trial Balance AR/Open Invoices/Customer Balance is `479,029.48`.
- Corrected Cash Balance Sheet assets are `308,935.58`, liabilities are
  `464,078.66`, equity is `-155,143.08`, with zero equation delta.

## Evidence still required or not mounted

The latest complete, digest-valid Production QBO evidence for the exact All
County realm is not mounted in this worker. The existing connection packet is
`OWNER_CONFIGURATION_REQUIRED` and explicitly has
`real_extraction_authorized=false`. No current QBO evidence may be inferred
from the repository controls above.

## Consolidated human decisions

| Decision owner | Decision required | Current state |
|---|---|---|
| Owner/accountant | Approve the proposed 2026-08-31 common cutoff and Cash basis | Pending |
| Accountant | Approve the Chart of Accounts mapping and all 92 Finance classifications | Pending |
| Accountant | Select the accepted source version for the `$850.00` AR discrepancy, or request transaction evidence | Pending; exact unresolved amount `$850.00` |
| Accountant | Confirm empty AP Aging/Unpaid Bills/Vendor Balance reports cover complete source scope | Pending; empty is not treated as zero yet |
| Owner/accountant | Approve bank opening balances and every reconciling item from statements | Evidence not mounted |
| Owner/accountant | Classify Undeposited Funds/funds in transit and inventory | Pending |
| Payroll authority | Supply payroll YTD, liability balances, covered periods, due dates, and GL controls | Pending |
| Accountant | Approve tax and other-liability opening controls | Pending |
| Owner/accountant | Approve retained/current earnings and opening-equity treatment | Pending; no inferred opening journal |
| Finance | Accept the opening control receipt and first native period-close package | Blocked by the above |

## Required evidence-backed outputs after mounting

1. Digest-valid QBO manifest and exact realm/Company binding.
2. Finance review queue with the `$850.00` conflict and all other exceptions.
3. Opening Trial Balance, Balance Sheet, P&L, AR Aging, AP Aging, Cash Flow,
   bank reconciliations, credit-card reconciliations, and payroll liability
   tie-out on the same cutoff.
4. Opening-control receipt proving debits equal credits, AR/AP subledgers tie
   to GL, bank/card balances reconcile, payroll liabilities tie, and no
   unexplained opening balance remains.
5. First native period-close acceptance with separated preparer/reviewer and
   Finance close authority.

## Cutover decision

Accounting engineering/preparation is ready to continue, but Accounting
authority cutover is **NO-GO** until the sealed QBO evidence is mounted and the
single decision set above is resolved. The exact next action is owner/accountant
delivery of the digest-valid All County QBO evidence mount plus the decisions
in this packet; no additional Accounting subsystem should be built first.
