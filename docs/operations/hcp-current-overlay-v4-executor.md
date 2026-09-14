# HCP current overlay v4 guarded executor

`MIGRATION.HCP.CURRENT.OVERLAY.V4.EXECUTOR.1` adds an explicit execution path for
`hcp-current-overlay-merge-packet/v4`. It does not reinterpret v4 as the legacy
v2 packet. The v2 executor remains unchanged by default for historical replay.

## Contract

The parser verifies canonical semantic and file digests, exactly 522 unique
records, the 174 `CREATE_NEW`, 4 `REUSE_EXISTING`, 5 `UPDATE_EXISTING`, and 339
`HOLD` dispositions, plus the exact 11/11/15/18 current graph. Qualified reuse
and update targets must be UUIDs carried by the sealed baseline evidence.

The complete read-only preflight runs before the write transaction and reports
all failures in one result. It checks parent closure for every mutating record,
current-graph closure, source and fingerprint duplicate boundaries, qualified
target existence/scope, conflicting SOURCE.4 bindings, artifact availability,
artifact modes/digests, repository authority, schema, Company/Branch, permission,
backup, and isolated-restore evidence. Historical `HOLD` records do not require
their non-operational parents to exist and cannot mutate native business truth.

Within the single migration-owned transaction, qualified reuse/update targets
receive SOURCE.4 successor lineage only after the sealed target is revalidated.
Creates and updates continue through native domain services. Run lineage,
source bindings, business events, holds, receipt, and native graph writes commit
or roll back together. Exact replay uses the same deterministic lineage and
receipt.

## Authority file

Enterprise must seal a mode-0600 JSON authority with contract
`hcp-current-overlay-native-execution/v3`. It contains:

- `protected_sha`, `deployed_sha`, `schema_head`, and `expected_database`
- `company_id`, `branch_id`, and authorized `actor_id`
- `overlay_path`, `overlay_file_sha256`, `overlay_semantic_digest`, and
  `complete_current_graph_digest`
- paths, file SHA-256 values, and semantic digests for the SOURCE.4 package, v3
  predecessor, original overlay, hold packet, update cohort, runtime inventory,
  and Preview baseline
- `backup_path`, `backup_digest`, `restore_receipt_path`, and
  `restore_receipt_digest`
- `idempotency_identity` and executor version
  `migration.hcp.current.overlay.v4.executor.1`

Every path and its parent must remain sanctioned and private. The idempotency
identity is SHA-256 over canonical JSON containing the authority contract, v4
semantic digest, backup digest, Company, and Branch.

## Guarded command

From `backend`, after Enterprise has deployed the exact protected candidate and
sealed a fresh authority file:

```console
TARGET_ENVIRONMENT=preview PREVIEW_ACCESS_ENABLED=true \
PRODUCTION_ACCESS_ENABLED=false \
python -m app.operational_migration.hcp_current_overlay_v4_command \
  --authority-file /absolute/sanctioned/path/v4-execution-authority.json \
  --authorize-preview-execution
```

This lane did not run that command against Preview.
