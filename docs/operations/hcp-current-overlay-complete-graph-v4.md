# HCP complete current SOURCE.4 graph v4

`MIGRATION.HCP.CURRENT.GRAPH.COMPLETENESS.1` rebuilds all 503 v3 predecessor
assertions and explicitly adds the 19 current SOURCE.4 graph records omitted by
v2. It is a sealed authority artifact; it performs no Preview mutation.

## Sealed artifact

- Path: `/Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-overlay-complete-graph-v4/successor-overlay.json`
- Contract: `hcp-current-overlay-merge-packet/v4`
- Semantic digest: `d2bb1e759935c2601140213905b761738543e3bb30bf86542778fed6ca8f1af9`
- File SHA-256: `e886eaeddea4c3c9a7f00e1987beb813eebe872bb9c28953efe78ba3a2fc91ee`
- Original assertions: 503
- Explicit completion records: 19
- Total unique source identities: 522
- Directory/file modes: `0700` / `0600`

Final dispositions across the executable authority are CREATE_NEW 174,
REUSE_EXISTING 4, UPDATE_EXISTING 5, and HOLD 339. The recomputed original 503
are 159/0/5/339. Relative to v3, 13 dependency holds become CREATE_NEW and the
19 completion records add 15 creates and four reuses.

The complete current graph is:

| Domain | CREATE_NEW | REUSE_EXISTING | UPDATE_EXISTING | HOLD |
| --- | ---: | ---: | ---: | ---: |
| Customers | 7 | 1 | 3 | 0 |
| Locations | 8 | 3 | 0 | 0 |
| Jobs | 15 | 0 | 0 | 0 |
| Appointments | 18 | 0 | 0 | 0 |

All 19 omission resolutions and all 13 `PARENT_GRAPH_RESOLVED` records are
embedded record-by-record. Historical holds remain unchanged.

## Enterprise execution-authority boundary

The next guarded execution authority must bind the v4 file and semantic
digests, SOURCE.4 package digest, v3 predecessor, original overlay, canonical
hold packet, update cohort, runtime inventory, Preview baseline file and
semantic digests, complete-current-graph digest, protected/deployed SHA, schema
head, Company/Branch, fresh backup digest, verified isolated-restore receipt,
idempotency identity, and migration authorization. It must reject baseline,
schema, authority, digest, scope, parent, identity, or concurrent-run drift.

The executor must understand the explicit v4 `CREATE_NEW`, `REUSE_EXISTING`,
`UPDATE_EXISTING`, and `HOLD` semantics. V2 and v3 remain non-executable.

## Rebuild verification

Run `python -m scripts.hcp_current_graph_completeness` from `backend` with the
sealed v3, original overlay, current-delta manifest, Preview baseline, accepted
classifier/successor manifest, refresh root, schedule root, and output paths.
Add `--verify` to mechanically compare the rebuilt canonical bytes with the
sealed artifact.
