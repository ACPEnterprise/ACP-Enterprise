# Accounting and QBO cutover readiness — 2026-11-11

## Authority and safety boundary

- Protected authority inspected: `48f3911f20f8945f0fc183844363999e6d6c9d00`.
- This packet performs no QBO write, Accounting posting, payment, Payroll
  execution, deployment, or protected merge.
- Laptop MASTER / ENTERPRISE.RELEASE owns integration and real-evidence custody.

Candidate evidence inspected at publication:

- `release/laptop1-qbo-banking-cashflow-1` at
  `9959fa516db14560c741cb4c3cf60dcfe52d9de5`;
- `release/laptop1-qbo-cutover-day1-current-1` at
  `7c7f4fd16fd91f0873c61c1949fab0f5a8e91cdd`;
- `release/laptop1-qbo-presprint-1` at
  `d8e2113d6c54eca9907fda1487d00766e5117ccc`;
- `work/qbo-bank-reconciliation-preparer-handoff-closure-4` at
  `acd456ff4a12195f2fdce24760bc66f1e74a47fe`.

## Current operational authority

Protected already contains the canonical native Accounting ledger, Chart of
Accounts, periods and close controls, AR, AP, Payroll Accounting controls,
financial reporting, QBO sealed-evidence projection/application/review, opening
controls, and the Banking operator workflow. Banking preserves import evidence,
deterministic matching, preparer submission, distinct Finance close, immutable
history, and cash-flow reconciliation without provider writeback.

The four requested candidate lines were evaluated selectively:

- `release/laptop1-qbo-presprint-1`,
  `release/laptop1-qbo-banking-cashflow-1`, and
  `release/laptop1-qbo-cutover-day1-current-1` contain an older in-memory
  presprint validator and planning packets. Their behavior is superseded by the
  protected durable Banking, opening-control, and close-control authorities.
- `work/qbo-bank-reconciliation-preparer-handoff-closure-4` supplied the
  preparer/reviewer handoff that is already protected.
- `release/laptop1-qbo-banking-operator-current-1` was not incorporated; its
  unique delta is Scheduling/Dispatch.

No stale or parallel Accounting authority should be cherry-picked from these
branches.

## Real source evidence already established

Repository-controlled acceptance evidence records:

- historical reporting policy: Cash;
- source ledger activity beginning 2022-01-01, with ordinary non-transfer
  activity beginning 2022-01-03;
- a balanced 2024-02-19 Accrual Trial Balance and balanced Cash Balance Sheet,
  with no Opening Balance Equity balance;
- corrected Cash Trial Balance and Cash Balance Sheet controls;
- corrected Accrual General Ledger for January 2022 through August 2026;
- accepted Cash P&L for 2022-01-01 through 2026-08-31;
- 2026-08-31 A/R Aging Detail of 479,879.48;
- 2026-08-31 Trial Balance A/R, Open Invoices, and Customer Balance Detail of
  479,029.48;
- one explicit 850.00 A/R source-version conflict;
- empty A/P Aging, Unpaid Bills, and Vendor Balance Detail as a candidate that
  still requires accountant confirmation of complete report scope;
- a sealed QBO clean-majority application contract that quarantines conflicts
  while continuing deterministic records.

These are source-backed controls, not proof that the values have been admitted
as native ACP opening Accounting authority. The restricted real QBO evidence
volume is not mounted in this worker environment, so no real application was
attempted and no counts were re-invented.

## Exact remaining cutover inputs

1. Release must mount and verify the latest complete, digest-valid Production
   QBO evidence manifest for the exact All County realm.
2. Accountant must approve the exact Chart-of-Accounts mapping, including the
   previously recorded 92 Finance-decision classifications.
3. Accountant must select the accepted source version for the 850.00 A/R
   conflict or require transaction-audit evidence.
4. Accountant must confirm that the empty A/P reports cover the complete source
   scope; missing AP evidence may not become zero.
5. Accountant must approve every bank and credit-card opening balance against
   external statements and reconciling items.
6. Accountant must classify Undeposited Funds/funds in transit and inventory as
   evidenced opening values or not applicable.
7. Payroll authority must provide the opening Payroll liabilities/YTD control,
   covered periods, due dates, and GL controls; unavailable provider history
   remains unavailable.
8. Accountant must approve tax and other-liability opening controls.
9. Owner/accountant must approve retained/current earnings and opening-equity
   treatment without an inferred opening journal.
10. Finance must approve the common cutoff, Cash-policy continuity and any
    exception, then accept the P&L, Balance Sheet, Trial Balance, AR/AP ties,
    cash-flow tie, and period-close separation.

## Smallest safe operational path

1. Release verifies the protected SHA/schema and restricted QBO evidence mount.
2. An authorized Accounting reconciler runs the existing QBO preflight and
   safe-majority application in Beta; exact records apply/bind, true conflicts
   enter the durable review queue.
3. Resolve only the named COA, A/R, A/P, bank/card, Payroll/tax, equity, and
   clearing decisions using owner/accountant authority.
4. Build and review the opening-control projection. Do not apply it until the
   balanced trial balance and all control ties are accepted.
5. Reconcile each bank/card statement through Prepare, Submit for Review, and a
   distinct Finance Close.
6. Re-run P&L, Balance Sheet, Trial Balance, AR/AP aging, and cash flow for one
   common cutoff and basis; require every variance to be zero or explicitly
   accepted as a governed exception.
7. Close the first native period only after accountant acceptance. QBO remains
   source evidence until the separate owner cutover authorization.

This path requires no additional Accounting model or migration. The next
productive action is controlled real-evidence execution and review, not another
parallel reconciliation subsystem.

The exact hold-safe commands, mutation boundaries, and Owner, Accountant, and
Payroll decision packets are published in
`accounting-real-evidence-execution-runbook-2026-11-11.md`.
