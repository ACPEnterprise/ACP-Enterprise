# Immutable release manifest

`scripts/release-manifest` creates and independently verifies the
`enterprise-immutable-release-manifest/v1` contract. It binds one release to:

- the exact application and tooling commits;
- one expected migration head;
- a named rollback release and exact rollback commit; and
- byte digests for the application, tooling, migration, backup, and rollback
  artifacts.

Generation uses exclusive creation and makes the completed manifest read-only.
It never overwrites an existing record. Artifact paths are relative to a
caller-selected custody root; absolute, escaping, symlink, and secret-like
paths are rejected. The manifest contains identities, sizes, and SHA-256
digests only, not artifact contents or credentials.

## Generation

```console
scripts/release-manifest generate \
  --root /approved/release-custody \
  --output /approved/release-custody/evidence/release-manifest.json \
  --candidate-sha "$APPLICATION_SHA" \
  --tooling-sha "$TOOLING_SHA" \
  --migration-head "$MIGRATION_HEAD" \
  --rollback-target-sha "$ROLLBACK_SHA" \
  --rollback-target-release "$ROLLBACK_RELEASE" \
  --application-artifact artifacts/application.tar.gz \
  --tooling-artifact artifacts/tooling.tar.gz \
  --migration-artifact artifacts/migration-graph.json \
  --backup-artifact artifacts/database-backup.dump \
  --rollback-artifact artifacts/rollback.tar.gz
```

The variables above are ordinary non-secret release identities. Runtime
credentials and signing keys are not inputs to this contract.

## Independent verification

An independent lane must supply every expected binding. Verification fails if
the manifest was changed, any binding differs, or any artifact size or digest
does not match:

```console
scripts/release-manifest verify \
  --root /approved/release-custody \
  --manifest /approved/release-custody/evidence/release-manifest.json \
  --candidate-sha "$APPLICATION_SHA" \
  --tooling-sha "$TOOLING_SHA" \
  --migration-head "$MIGRATION_HEAD" \
  --rollback-target-sha "$ROLLBACK_SHA" \
  --rollback-target-release "$ROLLBACK_RELEASE"
```

The verified values are safe inputs for release qualification. This contract
does not approve, sign, merge, or deploy a release.
