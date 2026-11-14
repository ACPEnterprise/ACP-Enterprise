# HCP isolated clone and native observation rehearsal

This procedure is limited to `migration_rehearsal`. It does not connect to or
mutate Preview or Production. The rehearsal PostgreSQL service has no published
host port; the exporter runs on the private Compose network.

## Restore a fresh Preview-isolated custom dump

The dump must have the existing `platform-resilience.backup.v1` manifest, the
`preview-isolated` environment, and restrictive permissions. Use a dedicated
rehearsal password that is not used by any other environment.

```sh
: "${HCP_REHEARSAL_POSTGRES_PASSWORD:?Set via the authorized secret source}"
export ACP_HCP_GATE_DIR='/authorized/path/hcp-operational-cutover-gate'
python3 scripts/hcp-isolated-restore.py \
  --backup /authorized/path/fresh-preview-isolated.dump \
  --expected-source-identity '<approved-preview-isolated-database-identity>' \
  --project-name hcp-isolated-rehearsal-20261110 \
  --receipt-output "$ACP_HCP_GATE_DIR/restore-receipt.json"
```

The command refuses a non-empty target, streams the source dump to `pg_restore`,
checks the `migration_rehearsal` container labels and private network, verifies
the database identity and exact Alembic head `yp8r0t2v4x6z`, and writes a mode
`0600` receipt. It never writes to the source dump.

## Export native observations

Run from the same checked-out repository and keep the restored service running.
The repository SHA is captured and compared before the database read begins.

```sh
: "${HCP_REHEARSAL_POSTGRES_PASSWORD:?Set via the authorized secret source}"
REPOSITORY_SHA="$(git rev-parse HEAD)"
ARTIFACT_DIR="$ACP_HCP_GATE_DIR"
RESTORE_RECEIPT="$ARTIFACT_DIR/restore-receipt.json"
docker compose -f docker-compose.migration-rehearsal.yml \
  --project-name hcp-isolated-rehearsal-20261110 \
  --profile export run --rm --no-deps \
  -v "$ARTIFACT_DIR:/output" \
  -v "$RESTORE_RECEIPT:/input/restore-receipt.json:ro" exporter \
  python backend/scripts/export_hcp_isolated_native_observations.py \
  --repository-sha "$REPOSITORY_SHA" \
  --expected-repository-sha "$REPOSITORY_SHA" \
  --company-id '<company-uuid>' \
  --branch-id '<branch-uuid>' \
  --restore-receipt /input/restore-receipt.json \
  --output /output/isolated-clone-native-observations.json
```

The exporter reads the private restore receipt through a read-only bind mount. It uses
a read-only transaction, verifies scope and schema, joins native binding
evidence to native rows, requires exactly one valid durable overlay journal
lineage per observation, and emits deterministic JSON with mode `0600`.

This is rehearsal evidence only. It does not authorize HCP cutover, source
mutation, deployment, financial execution, or Production access.
