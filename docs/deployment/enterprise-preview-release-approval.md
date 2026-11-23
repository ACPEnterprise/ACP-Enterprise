# Enterprise Preview Release Approval v2

`enterprise-preview-release-approval/v2` is the immutable, signed approval
required by protected Beta qualification. It replaces the machine/worker name
`OM1E` with the owner-enrolled logical authority
`twelvehats-beta-release-authority`.

## Trust boundary

The authority is operated from Laptop Master, but its encrypted private key,
trust registry, approval artifacts, and audit chain live outside every candidate
worktree. Candidate code has validation authority only. The protected public key
and key ID are pinned independently; changing candidate code cannot enroll a new
issuer.

The enrolled human custodian is Michael Fouse. Enrollment also names an
independent qualification reviewer whose identity differs from the custodian.
The issuer refuses to sign unless a current review receipt binds the exact
candidate, migration, backup/restore receipts, rollback target, evidence archive,
and a zero-defect mandatory-gate decision.

## Required bindings

An approval binds:

- exact candidate SHA and migration head;
- fresh protected backup and isolated-restore receipt SHA-256 values;
- rollback release and SHA;
- exact `BETA_PREVIEW` scope;
- owner-enrolled authority, human custodian, key ID, and enrollment digest;
- immutable independent-review receipt and evidence-archive digests;
- UTC issue and expiration times, with a maximum 24-hour lifetime; and
- an Ed25519 signature over the canonical complete payload.

Expired, future-dated, revoked, untrusted, improperly reviewed, candidate-issued,
or mismatched approvals fail closed.

## Protected qualification

```sh
scripts/enterprise-release-qualify \
  --profile preview --execute \
  --candidate-sha "$CANDIDATE_SHA" \
  --preview-revision "$CANDIDATE_SHA" \
  --migration-head "$CANDIDATE_MIGRATION_HEAD" \
  --approval-artifact /protected/release/preview-approval.json \
  --authority-registry /protected/release/authority.json \
  --trusted-issuer-key /protected/release/twelvehats-beta-release-authority.pub \
  --trusted-issuer-key-id "$ENTERPRISE_AUTHORITY_KEY_ID" \
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

This command validates authority and qualification evidence. It does not deploy,
migrate, create credentials, initiate OAuth, or perform application/financial
mutations.
