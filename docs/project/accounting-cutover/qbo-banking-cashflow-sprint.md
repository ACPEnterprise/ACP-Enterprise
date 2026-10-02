# Banking and cash-flow closure sprint

Protected authority at preparation: `290ad8119951412237df640f6003ecc3f3d08ada`.

This bounded preparation adds read-only, provider-neutral controls in
`app.qbo_source.presprint_reconciliation`. It does not import a bank feed,
post a journal, close a real statement, move money, or persist a balance.

| Target | Engineering state | Real source | Operator ready | Physical acceptance | Parity |
| --- | --- | --- | --- | --- | --- |
| Bank ingestion and deterministic matching | ENGINEERING_COMPLETE for evidence/match seam | UNAVAILABLE | NO | NO | YELLOW |
| Bank reconciliation and statement close | ENGINEERING_COMPLETE for zero-difference/review controls | UNAVAILABLE | NO | NO | YELLOW |
| Cash-flow reporting | ENGINEERING_COMPLETE for classified tie-out seam | UNAVAILABLE | NO | NO | YELLOW |

## Qualified control behavior

- Bank identities are company-scoped and retain institution, source system,
  provider transaction ID, source version, digest, and as-of evidence.
- Pending transactions, ambiguous candidates, and non-source-linked candidates
  remain `REVIEW_REQUIRED` or `UNMATCHED`; no fuzzy auto-match exists.
- Reconciliation requires posted cleared evidence, a zero difference, and no
  unresolved items before an immutable close snapshot can be created.
- Cash flow keeps operating, investing, and financing movements separate,
  rejects post-cutoff evidence, preserves classification review, and requires
  beginning cash plus net change to equal ending cash.

## Required next evidence

1. A sanctioned read-only bank connection or dated statement/CSV/OFX package
   with institution/account identity and source digests.
2. Accountant-approved matching, transfer, fee, owner-movement, and
   undeposited-funds policy.
3. Accountant-approved cash-flow classification and cutoff/basis policy.
4. A normal operator surface for import, matching review, reconciliation close,
   reopen, and cash-flow drill-down before operator-ready can be claimed.

No row is GREEN until All County evidence and operator/accountant proof are
attached.
