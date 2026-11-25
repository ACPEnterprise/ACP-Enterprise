# Protected restored-database rehearsal

This workflow qualifies a candidate only against an isolated restored database.
It cannot approve or deploy a release and must never target Beta or Production.

## Required sequence

1. Create and verify a `platform-resilience.backup.v1` custom-format backup from
   the approved non-Production baseline. Keep the dump and manifest outside the
   repository with mode `0600` in a mode `0700` directory.
2. Restore into a new database whose name begins
   `acp_resilience_restore` and whose target identity begins `isolated-`:

   ```bash
   scripts/platform-resilience restore \
     --environment preview-isolated \
     --database-url "$ISOLATED_RESTORE_DATABASE_URL" \
     --target-identity isolated-candidate-rehearsal \
     --expected-source-identity "$APPROVED_SOURCE_IDENTITY" \
     --backup "$RESTRICTED_BACKUP_PATH" \
     --receipt "$RESTRICTED_EVIDENCE_DIR/restore.json"
   ```

3. Independently verify the restore receipt against the approved baseline SHA,
   schema head, backup digest, and target identity with
   `platform-resilience verify-restore-receipt`.
4. Run the candidate migration as `acp_migrate`; record the before and after
   heads, the single canonical head, `alembic check`, and an idempotent second
   upgrade in `enterprise-release.migration-rehearsal/v1` evidence.
5. Apply the reviewed role transition and capture
   `enterprise-release.database-role-rehearsal/v1` evidence. It must show:
   `acp_schema_owner` owns objects and cannot log in, `acp_migrate` can assume
   only that owner, `acp_app` has no elevated flags, and only `acp_backup` has
   `BYPASSRLS`. Positive application access and negative cross-tenant read and
   write checks are mandatory.
6. Start the candidate with the database connection authenticated as `acp_app`.
   Seal the healthy state, actual role, database identity, and schema head in
   `enterprise-release.application-readiness-rehearsal/v1` evidence.
7. Restore the original backup into a second new isolated target. Verify the
   baseline head and an approved deterministic data digest before and after the
   rehearsal. Seal this as `enterprise-release.rollback-rehearsal/v1`.
8. Run the independent verifier:

   ```bash
   PYTHONPATH=backend python3 -m scripts.verify_protected_rehearsal \
     --candidate-sha "$CANDIDATE_SHA" \
     --baseline-sha "$BASELINE_SHA" \
     --expected-head "$EXPECTED_HEAD" \
     --backup-manifest "$RESTRICTED_BACKUP_PATH.manifest.json" \
     --restore-receipt "$RESTRICTED_EVIDENCE_DIR/restore.json" \
     --migration-evidence "$RESTRICTED_EVIDENCE_DIR/migration.json" \
     --role-evidence "$RESTRICTED_EVIDENCE_DIR/roles.json" \
     --readiness-evidence "$RESTRICTED_EVIDENCE_DIR/readiness.json" \
     --rollback-evidence "$RESTRICTED_EVIDENCE_DIR/rollback.json" \
     --output "$RESTRICTED_EVIDENCE_DIR/verification.json"
   ```

The verifier fails closed for a reused restore target, mismatched candidate or
baseline, stale schema, altered backup, incomplete role separation, privileged
application identity, failed tenant isolation, unhealthy readiness, changed
rollback data digest, permissive evidence files, or tampered evidence seals.
Its output explicitly records `deployment_authorized: false` and is only input
to independent release review.
