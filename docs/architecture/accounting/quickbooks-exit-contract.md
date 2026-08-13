<!-- markdownlint-disable MD013 -->

# QuickBooks Exit and Opening-State Contract

This document records the approved exit strategy and control invariant. The
normative `ACC.DATA.1` artifact catalog, opening-state mapping, archive rules,
and `ACC.MIG.1` machine handoff are frozen in the
[QuickBooks exit data contract](quickbooks-exit-data-contract.md). If the two
documents differ, the detailed data contract controls for data-package content;
the Day-1 control contract continues to control Accounting policy.

## Required source package

`ACC.DATA.1` inventories and fingerprints, but does not extract, the following:

- active COA, account types, and stable source identities;
- cutover trial balance and required GL detail;
- open invoices, customer credits, AR aging, unapplied receipts, and
  undeposited funds;
- open vendor bills, vendor credits, AP aging, and vendor balances;
- bank, cash, credit-card, and loan balances plus outstanding checks, deposits,
  transfers, and reconciling items;
- sales-tax jurisdiction liabilities;
- inventory asset/control balance;
- payroll liabilities and accruals;
- fixed assets, accumulated depreciation, equity, retained earnings, loans,
  prepaids, and accruals;
- customer/vendor source identities and accounting-period configuration; and
- export timestamps, source-company identity, file sizes, SHA-256 checksums, and
  an immutable QuickBooks archive.

Real extraction, import, Preview, Production, or cutover requires a separate
owner-controlled operation. Secrets and credentials never enter the repository.

## Reconciliation invariant

For every required control account:

`QuickBooks closing balance = ACP opening balance`.

AR control equals imported customer open items; AP control equals imported
vendor open items; undeposited funds, bank/cash, tax liabilities, and inventory
control reconcile; opening debits equal credits; the trial balance nets to zero;
the balance sheet balances; and AR/AP aging agrees to its control account.

Every input is accepted, rejected, or explicitly dispositioned exactly once.
Import replay is idempotent. Every source, transformed artifact, rejection,
disposition, report, and approval is retained with a checksum. Any unexplained
variance blocks activation.

## Cutover and rollback contract

The final owner-approved sequence is transaction freeze, final QuickBooks
extraction, immutable checksums, closing control approval, ACP backup, approved
Production release and migrations, idempotent opening-state load, full
reconciliation, financial/security smoke tests, independent Finance approval,
owner activation, and QuickBooks read-only retirement.

Rollback criteria must be approved before activation. Rollback stops new ACP
posting, preserves all ACP and source evidence, identifies the authoritative
ledger for every post-freeze transaction, and requires joint owner and independent
Finance approval. It never deletes posted evidence or silently creates dual books.
