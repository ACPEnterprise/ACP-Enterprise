# QBO opening-state and control-reconciliation API handoff

Date: 2026-10-03  
Consumer: Accounting → QuickBooks Cutover  
Protected authority reviewed: `origin/customer-management-v1` at `e703c7b6210c62c99d2e69c44ecb0c70e09f9bc9`

Evolving Accounting dependency reviewed: `origin/work/qbo-opening-state-ar-ap-control-closure-1` at `6d16e5ce`

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

## Evolving backend candidate assessment

The Accounting candidate at `6d16e5ce` adds deterministic calculation and
persistence for an opening-control package. It correctly models balanced versus
unbalanced Trial Balances, explicit opening-equity review, A/R and A/P control
differences, exact exception dispositions, immutable digests, approval, and
application state. It is useful domain authority and must be preserved.

It is not yet an operator-consumable source projection:

- `POST /api/v1/accounting/opening-controls/preview` requires the caller to
  supply the Trial Balance lines, debit/credit orientation, control balances,
  source and native subledger populations, source digests, and exact cutoff;
- the protected QBO source-evidence API does not expose enough canonical data
  for the browser to construct that request without recreating Accounting and
  source-binding logic;
- there is no company-scoped endpoint to list or retrieve the current opening
  package and its Trial Balance lines, equity classifications, reconciliation
  totals, status, or actor-safe review history;
- the response does not expose the line-level Trial Balance or classified
  equity values needed by the review screen;
- exceptions expose internal source/native identities but not the safe Customer,
  Invoice, Vendor, Bill, payment/application, and open-balance drill-down labels
  required for normal operator review.

The minimal safe successor is therefore a server-owned adapter that resolves a
sealed QBO package and native successors by authenticated Company, then previews
or retrieves its controls without accepting reconstructed accounting evidence
from the browser. A suitable boundary would be:

- `POST /api/v1/accounting/opening-controls/source-packages/{package_id}/preview`
  with only an expected package digest/version; and
- `GET /api/v1/accounting/opening-controls/{package_id}` returning the review
  projection, including Trial Balance lines, equity classifications, A/R and A/P
  totals, exceptions, safe drill-down references, completeness, status, actors,
  and version.

The candidate also uses Alembic revision `vl2n4p6r8t0v`, which is already the
current protected appointment-capacity revision. Enterprise/Accounting must
assign a new successor revision based on the actual protected head. The UI lane
must not rewrite that migration.
