# Migration cutover owner decision packet

This packet contains only decisions that cannot be inferred from sealed source
evidence. It does not authorize source access, freeze, Production activation,
Accounting posting, or mutation of HCP or QBO.

## HCP final employee crosswalk

- **Question:** do all technician identities in the final delta retain an
  approved ACP Employee mapping?
- **Current evidence:** seven sealed HCP Employee identities exist. Six accepted
  candidates carry 1,825 relevant historical Job assignments. Rehearsal
  mappings remain immutable evidence, not automatic live mappings.
- **Options:** confirm an existing mapping; authorize a candidate through the
  Employee domain; hold affected assignments.
- **Recommended default:** none. A name-only match is not authoritative.
- **Risk:** unresolved identities block their assignments and related open work.
- **Unlocks:** employee-scoped final-delta reconciliation.

## HCP Branch crosswalk

- **Question:** does the approved rehearsal mapping for the HCP `Plumbing`
  Business Unit and the missing-unit pattern bind the intended live Branch?
- **Current evidence:** the rehearsal mapping is sealed. The final target Branch
  must be explicitly authorized; 277 of 278 previously selected open Jobs had
  no Business Unit evidence.
- **Options:** confirm the live target Branch; hold unmapped open work.
- **Recommended default:** none. Labels are not identities.
- **Risk:** an inferred mapping can persist work into the wrong Branch.
- **Unlocks:** Branch-scoped Jobs, Appointments, Estimates, and assignments.

## Canceled Jobs with balance assertions

- **Question:** after real HCP/QBO reconciliation, how should the 296 canceled
  Jobs with nonzero source balance assertions be treated?
- **Current evidence:** source records and financial assertions are preserved on
  HOLD and were not promoted to ACP AR or operational work.
- **Options:** retain HOLD; admit only after accounting reconciliation; explicit
  exception.
- **Recommended default:** retain HOLD.
- **Risk:** premature admission creates disputed economic or operational truth.
- **Unlocks:** final Job and financial-evidence dispositions.

## Unlinked Estimates

- **Question:** should retained unlinked Estimate evidence remain evidence-only,
  receive an authoritative Job link, or become an explicit exception?
- **Current evidence:** 24 accepted unlinked Estimate evidence rows remain
  preserved without duplication or an invented Job relationship.
- **Options:** retain evidence-only; link using authoritative evidence; explicit
  exception.
- **Recommended default:** retain evidence-only until a source relationship is
  proven.
- **Risk:** a guessed link corrupts Job and profitability lineage.
- **Unlocks:** final Estimate disposition.

## Historical and cross-source authority

The owner must separately approve the acquisition window and opening evidence,
Chart of Accounts mapping, Customer/Invoice/Payment overlap, AR/AP, bank/cash,
Payroll and tax liability authority, genuine HCP/QBO conflicts, source freeze,
final go/no-go, and Production activation. Each approval binds its policy
version and immutable evidence digest.

## Exact future cutover sequence

1. Authorize real provider access; stop if realm, Company, or scope differs.
2. Seal pre-cutover HCP and QBO manifests; stop on incomplete acquisition.
3. Reconcile dispositions and opening state; stop on any unexplained delta.
4. Bind the decisions above and the historical window.
5. Owner authorizes source freeze; persist timestamp, actor, and source evidence.
6. Acquire final HCP and QBO deltas; any late source change invalidates the
   delta and returns the run to reconciliation.
7. Reconcile baseline plus delta and issue the deterministic go/no-go packet.
8. Owner gives go/no-go. A no-go preserves checkpoints and source evidence.
9. A separately authorized Production activation may execute; this document
   does not grant it.
10. Verify completion and deterministic replay. Keep source systems read-only
    until the separately approved retirement boundary.
