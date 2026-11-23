# Enterprise Preview Release Approval

`enterprise-preview-release-approval/v1` is the immutable, signed approval
required by the protected Preview qualification profile. It is separate from a
normal qualification packet, which must continue to contain
`deployment_authorized=false`.

## Authority boundary

Only the documented Enterprise release authority `OM1E` may issue the artifact.
Laptop Master and the candidate developer have validation authority only. The
validator trusts an Ed25519 public key supplied by protected release custody;
the private issuer key never belongs in Git, the candidate worktree, or a
qualification packet.

The artifact is immutable by contract: its canonical unsigned payload is
SHA-256 bound in `artifact_digest`, and the complete payload including that
digest is signed. Any field change, including the candidate, migration head,
receipt, rollback, scope, issuer, or expiration, invalidates the signature or
the requested binding.

## Required bindings

The artifact must bind:

- exact candidate SHA;
- candidate migration head;
- backup and isolated-restore receipt SHA-256 values;
- rollback release and SHA;
- exact `BETA_PREVIEW` scope;
- UTC issue and expiration timestamps, with a maximum 24-hour lifetime; and
- issuer `OM1E`, role `Enterprise Release Authority`, and trusted key ID.

The validator also requires the artifact and trusted public key to be protected
regular files and rejects expired, not-yet-valid, mismatched, forged, or
candidate-issued approvals.

## Protected runtime checks

When Preview qualification runs in the protected execution environment, pass
the protected runtime root, Compose project, current runtime SHA/schema, signed
approval artifact, trusted issuer key, and expected receipt/rollback bindings.
The runner then executes `scripts/protected-runtime-check.py` for PostgreSQL and
Redis.

The PostgreSQL check uses the service's own password-backed identity, verifies
`pg_isready`, current user/database, and records the runtime role's superuser
state for Enterprise review. The check does not change the existing runtime
role or turn a configuration observation into a false health failure. The Redis
check reads the mounted health secret without printing it and requires an
authenticated `acp-health` `PING`. Both checks first verify the protected
release metadata and Alembic head. Missing runtime metadata, credentials,
identity mismatch, failed health, or inconsistent schema is `BLOCKED`.

Example protected qualification shape:

```sh
scripts/enterprise-release-qualify \
  --profile preview --execute \
  --candidate-sha "$CANDIDATE_SHA" \
  --preview-revision "$CANDIDATE_SHA" \
  --migration-head "$CANDIDATE_MIGRATION_HEAD" \
  --approval-artifact /protected/release/preview-approval.json \
  --trusted-issuer-key /protected/release/om1e-preview-release.pub \
  --trusted-issuer-key-id om1e-preview-2026-01 \
  --expected-backup-receipt-sha256 "$BACKUP_RECEIPT_SHA256" \
  --expected-restore-receipt-sha256 "$RESTORE_RECEIPT_SHA256" \
  --rollback-target-sha "$ROLLBACK_SHA" \
  --rollback-target-release "$ROLLBACK_RELEASE" \
  --protected-runtime-root /opt/acp-enterprise \
  --protected-runtime-project acp-enterprise-preview \
  --runtime-sha "$CURRENT_RUNTIME_SHA" \
  --runtime-schema-head "$CURRENT_RUNTIME_SCHEMA" \
  --backup-receipt /protected/release/backup-receipt.json \
  --restore-receipt /protected/release/restore-receipt.json \
  --evidence-dir /protected/release/qualification
```

The command performs no deployment, migration, OAuth, application mutation, or
financial action. Enterprise must independently validate the sealed packet and
then record Release GO through its existing governance process.
