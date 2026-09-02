# PRICEBOOK.ALLCOUNTY.ACTIVATION.READINESS.1 integration packet

## Protected integration

- Source branch: `work/pricebook-allcounty-activation-readiness-1`
- Starting Price Book authority: `40fbbe2e8d3babe708d33dfecec58599d0f12f56`
- Protected authority at branch creation: `fd2af4057a8dc1ba14777e3c052dd6ed39656404`
- Protected authority at final pre-integration refresh: `5ee0dd237ed052864c951950c1836b23f4a063b3`
- Candidate configuration: `all-county-build-1.configuration.json`
- Activation audit: `all-county-activation-readiness-1.json`
- Activation audit SHA-256: `fc9c3673a4e4ca796f73fd0a12cce23ca73e3bce8a7236863368872c13a07c72`
- Migration: `n0p8q16g3t9u` after `m9n7q05f2s8t`

### Materials source provenance gate

BUILD.1 byte authority remains the unchanged owner original:

`~/Desktop/ACPL docs/pricebook_materials_template.numbers`

SHA-256:
`487afcbbce7584471c691507616c2f87464ee2959105b1b03bfe41eee03e92a9`

The `c9707e…` artifact was mechanically located at
`~/Downloads/pricebook_materials_template (1).numbers`; its full SHA-256 is
`c9707e9abfc40a46be2ab0d234d7149857b5e7d9605a6aa747e152bb094c0712`.
It is a distinct Numbers package (288,743 bytes versus 287,208), not the BUILD.1
byte authority. Both contain 45 archive entries. The package metadata,
view/calculation state, and one table header-storage object differ, but the
repository importer produces exactly the same one-sheet, one-table, 362-row,
19-column, 361-candidate projection from both. Canonical JSON serialization of
each complete import projection has SHA-256
`ba85c914a2f4b55720016300da64769219627a5362fc0cb9cef7faf3ad5faa2c`.
This makes the Downloads artifact a semantically equivalent download/working
representation, not a changed owner source and not a BUILD.1 successor.

Enterprise must qualify BUILD.1 with the canonical Desktop path and require the
full `487afc…` digest. Do not substitute `c9707e…` and do not change registered
history. To reproduce: run `shasum -a 256` on both paths, then invoke
`vendor_material_candidates` from `scripts/pricebook_allcounty_build.py` on each,
serialize both results with sorted JSON keys and compact separators, and require
both the equality result and normalized digest above. The machine-readable
record is `all-county-material-source-provenance-1.json`. If a future owner file
produces a third byte digest or a different normalized projection, register a
successor source/version; never rewrite BUILD.1.

Enterprise should integrate the completed Build 1 branch before this successor.
This branch must not be integrated as competing configuration or used to bypass
the owner/accountant decisions below.

## Mechanical result

The audit accounts for all 218 candidates independently. All have the minimum
commercial fields needed for browse, Estimate selection, customer presentation,
and immutable snapshot composition. None is active. Complete material/labor cost
is not a commercial prerequisite under the current contracts.

- 218 commercially ready before cost completion.
- 179 require grouped owner price/content approval and a reusable tax-class
  decision, with no other source conflict.
- 39 Water Heater candidates additionally require confirmation that workbook
  prices remain authoritative over conflicting illustrative script figures.
- 194 incomplete material mappings block Inventory/planned-cost/Economics
  completeness, but do not block candidate customer prices or Estimate snapshots.
- 208 prices are workbook-formula derived; 10 are explicit workbook overrides.
- 361 vendor candidates remain provider-neutral: 359 lack authoritative vendor
  identity; the two rows for source part `828627` remain one deterministic
  possible-match group without name-only overwrite.

After the grouped minimum approvals, all 218 are candidates for explicit
activation. This is not an activation authorization.

## Product changes

Two tenant-scoped durable records support owner review and future successor
proposals. Review batches bind configuration version, selector, exact service
set, exclusions, digest, idempotency identity, decision, actor, audit, and
Business Event. Adjustment proposals bind source Price Book version, optional
Economics/model versions, recommendation identity, exact service set,
transformation, before/after impacts, limitations, exclusions, effective date,
digest, actor, audit, and Business Event.

Both workflows require Manage authority. Neither invokes Activate authority or
mutates a Price Book version. Stale versions/digests and contradictory replay
fail closed. The owner UI separates customer use, tax decisions, and internal
cost readiness; it saves and approves the currently filtered group without
exposing an activation shortcut.

## Integration checks

1. Confirm Build 1 is an ancestor of the integration target.
2. Apply the single new Alembic head and run zero-to-head/current=head/drift.
3. Run Price Book plus Estimates, Service Agreements, Inventory, Economics,
   authorization, audit/events, frontend, and mutation-registry qualification.
4. Inspect the owner and accountant packets; do not assign tax treatment during
   integration.
5. Verify the real candidate configuration remains `NOT_ACTIVATED` and Preview
   receives no deployment from this branch without Enterprise action.

## Remaining decisions

Owner: grouped approval for 208 formula prices, 10 overrides, 16 categories and
descriptions; Water Heater workbook authority; whether member pricing remains
disabled pending Service Agreement/legal reconciliation; exclusions; and a
later explicit activation authorization.

Accountant: reusable tax treatment for the 16 mechanically identical
source-category groups, identifying only factual exceptions that require a
smaller subgroup. No tax treatment or rate is proposed here.

## Hard boundaries

No real price activation, automatic repricing, invented tax treatment,
accounting posting, Employee recommendation, Preview deployment, Production
deployment, or mutation of real Customers/Jobs/Estimates occurred.
