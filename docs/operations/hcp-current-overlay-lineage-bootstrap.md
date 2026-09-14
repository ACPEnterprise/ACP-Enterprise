# HCP current-overlay lineage bootstrap handoff

This successor closes `OVERLAY_SOURCE4_RUN_LINEAGE_MISSING` without treating the
full SOURCE.4 population as admitted. It atomically creates or resolves a
deterministic SOURCE.4 master, a database-created Customer child, and a
database-created Operational child in the same transaction that applies the
accepted current overlay.

The master terminal state is `completed_current_operational`. Its durable
attestation retains `canonical_admission_allowed: false`, admission scope
`current_operational_only`, and the unchanged canonical hold count of 1,389.
The state is intentionally distinct from broad `completed`.

## Protected bindings

- Deployed authority before this successor: `e1015aada1daa5abf33bfa6968cd1eb1fe5da298`
- Predecessor schema: `f6h8j0l2n4p6`
- Successor schema: `g7i9k1m3o5q7`
- Overlay file SHA-256: `ce9d4ea1e048a70b7a8a5b85fab33fd1a0568eb5cb1356229187144ab8bc7558`
- Hold packet SHA-256: `c13cb0b565d2b86d34365f12d565f37f0e7ba6ec6bfa0d65de7f4a81ee088324`
- Overlay manifest digest: `e23b7bcf5ac34ea650184afacc711af0c7028e83a6b1f7405e2ae17e13441eb2`
- Base SOURCE.4 digest: `4a4a9582d7fde37dba73ba9e93db5669d9341768c7f5741f6e8916971fd9ec60`

Enterprise must set `source4_package_identity` to the exact accepted sealed
package identity from its custody record. It is an attested string, not a run
UUID. The v2 authority contains no `master_run_id`, `customer_run_id`, or
`operational_run_id` fields.

## Authority and execution

The mode-0600 authority contract is
`hcp-current-overlay-native-execution/v2`. In addition to the existing artifact,
backup, restore, scope, authority, database, schema, classification, drift, and
idempotency fields, it requires:

```text
source4_package_identity
canonical_hold_count = 1389
```

`expected_schema_head` must be `g7i9k1m3o5q7` after protected migration and
`expected_repository_sha` must be the resulting deployed protected SHA.
Enterprise remains responsible for supplying a fresh backup digest and matching
verified isolated-restore receipt.

The guarded command is unchanged:

```bash
ENVIRONMENT=preview TARGET_ENVIRONMENT=preview \
PREVIEW_ACCESS_ENABLED=true PRODUCTION_ACCESS_ENABLED=false \
python -m app.operational_migration.hcp_current_overlay_command \
  --authority-file "$AUTHORITY_FILE" \
  --authorize-preview-execution
```

The deterministic master UUID is derived internally from the complete lineage
attestation using the repository's UUIDv5 run pattern. Child UUIDs are created
by their repository-owned model defaults and are stored on the master. Exact
replay resolves the same scoped package/master and unique children. Any changed
digest, actor, Company, Branch, authority, schema, package identity, or hold
count conflicts with the immutable input and fails closed.

Expected packet scope remains 503 assertions. The accepted current-calendar
target remains 11 Customers, 11 Locations, 15 Jobs, and 18 Appointments. The
1,389 canonical holds remain held; the executor does not reclassify them.

If lineage creation, child creation, native overlay processing, or receipt
persistence fails, the single migration-owned transaction rolls back the run
rows, native graph, Business Events, provenance, and receipt together. A
successful replay returns the prior receipt without new native records or
Business Events.
