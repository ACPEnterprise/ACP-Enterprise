# OM2-A QuickBooks A/R and A/P historical readback

`OM2-A-ACCOUNTING-ARAP-READBACK-04` adds a read-only projection for source-backed
QuickBooks accounts-receivable and accounts-payable open items. It retains source
transaction and counterparty identifiers, evidence digests, dates, amounts, and
known reconciliation exceptions. Calculated open-item totals are compared with
the supplied source totals; discrepancies remain visible and are never silently
corrected or converted into native accounting balances.

The projection accepts only an existing read-only QuickBooks source registration.
It grants no mutation authority, does not admit records as native transactions,
and performs no OAuth, posting, banking, payment, or external-system operation.

Qualification uses sanitized synthetic records. Protected QuickBooks custody was
not available during implementation, so this evidence is isolated qualification,
not live All County acceptance or proof of reconciliation against the protected
company file. A sealed, tenant-bound QBO manifest and its verified source totals
remain required for protected acceptance.
