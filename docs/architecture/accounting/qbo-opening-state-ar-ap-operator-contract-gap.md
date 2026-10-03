# QBO opening-state and control-reconciliation API handoff

Date: 2026-10-03
Consumer: Accounting → QuickBooks Cutover
Authority reviewed: `origin/customer-management-v1` at `66fd912d4be1986731190b1d0603be5101d022e6`

The protected server currently provides sealed QBO source custody, account-balance evidence, source invoices and bills, net aged A/R, native-application dispositions, and the governed review queue. Those contracts support source/cutoff review and source-record drill-down. They do not establish opening Accounting authority or an A/R/A/P control tie.

## Missing read contracts

The owning Accounting lane should expose company-scoped, permission-protected projections equivalent to:

- `GET /api/v1/accounting/cutover/source`
  - safe realm/company display identity, acquisition time, accounting cutoff, package/digest/replay status, completeness, and explicit gaps;
- `GET /api/v1/accounting/cutover/opening-trial-balance`
  - account identity/code/name/type, debit, credit, currency, source reference, classification status, total debits, total credits, difference, exceptions, balance state, and approval state;
- `GET /api/v1/accounting/cutover/opening-equity`
  - separately classified retained earnings, owner equity, legitimate opening-balance equity, unexplained difference, source evidence, and review state;
- `GET /api/v1/accounting/cutover/control-reconciliations/ar`
  - cutoff-matched A/R control balance, Customer subledger total, difference, completeness, as-of/provenance, status, exact exception population, and drill-down references;
- `GET /api/v1/accounting/cutover/control-reconciliations/ap`
  - cutoff-matched A/P control balance, Vendor subledger total, difference, completeness, as-of/provenance, status, exact exception population, and drill-down references.

Both control-reconciliation projections need canonical exception dispositions:

- `SOURCE_ONLY`
- `ACP_ONLY`
- `AMOUNT_DIFFERENCE`
- `MISSING_LINK`
- `DUPLICATE`
- `REVIEW_REQUIRED`

Each exception needs a stable identity, source/native references, safe operator labels, amounts and currency where authoritative, source/as-of evidence, the responsible review authority, and a normal UI destination. Pagination and stable ordering are required.

## Mutation boundary

No approval endpoint should be inferred from a balanced browser calculation. Any future prepare/submit/approve lifecycle must derive actors from authenticated server authority, use optimistic versioning, preserve immutable evidence, and reject unresolved exceptions. The UI will not manufacture debit/credit orientation from unsigned account balances, hide an opening-equity plug, or calculate a control tie from unrelated cutoffs.

Until these contracts exist, the Cutover workspace truthfully labels opening, A/R control, and A/P control review as unavailable or incomplete while preserving access to the source evidence that does exist.
