# TwelveHats Beta release orchestration

This runbook defines the release dependency graph. It separates qualification,
independent review, owner approval, execution, and operational acceptance. No
stage may report a later stage as complete.

## Ordered stages

```text
A pre-signing candidate qualification
        |
B protected-environment readiness
        |
C independent review receipt
        |
D owner-signed candidate-bound approval
        |
E pre-execution approval validation
        |
F authorized maintenance, migration, and deployment
        |
G post-deployment runtime acceptance
        |
H final operational acceptance or rollback
```

Stages A and B produce the candidate, migration, backup, isolated-restore,
rollback, configuration, and evidence bindings. They do not require a signed
approval. Stage C is performed by the enrolled independent reviewer and is
validated with:

```sh
python3 scripts/validate-independent-review.py \
  --review-receipt /protected/release/independent-review.json \
  --registry /protected/release/authority.json \
  --trusted-key /protected/release/twelvehats-beta-release-authority.pub \
  --key-id "$ENTERPRISE_AUTHORITY_KEY_ID" \
  --candidate-sha "$CANDIDATE_SHA" \
  --migration-head "$CANDIDATE_MIGRATION_HEAD" \
  --backup-receipt-sha256 "$BACKUP_RECEIPT_SHA256" \
  --restore-receipt-sha256 "$RESTORE_RECEIPT_SHA256" \
  --rollback-target-sha "$ROLLBACK_SHA" \
  --rollback-target-release "$ROLLBACK_RELEASE"
```

That command is validation-only: it does not load a private key, issue an
approval, deploy, migrate, or authorize a live change. It can therefore run
before Stage D. The existing interactive `issue` command remains the only
approval issuance path and requires the validated Stage-C receipt.

Stage E validates the signed approval again immediately before execution. Stage
F is the only stage that may perform the separately authorized maintenance,
migration, and deployment actions. Stage G tests the actual serving runtime
with short-lived approved identities. Stage H records final operational GO or
invokes the preapproved rollback procedure.

The qualification runner's `presigning` profile executes only the independent
review validation and records all other checks as not yet executed. It is not a
deployment authorization and cannot produce a `deployment_authorized=true`
packet.

## Smoke-principal sequencing

Pre-signing smoke readiness is a non-secret contract, not a live credential. It
validates the canonical token path, mode-0600 root custody, read-only container
mount, verified company/branch and denial-tenant IDs, the exact provisioner
digest, and an isolated provisioner rehearsal. Its artifact must explicitly say
`token_issued: false` and `token_required_for_live_acceptance: true`.

The short-lived release actor and acceptance reader are provisioned only after
the signed approval validates and the successor schema is current. Their token
files must be nonempty before post-deployment smoke begins. A missing token is
therefore a post-approval execution block, never a reason to make pre-signing
readiness circular or to accept a placeholder token.

The immutable evidence chain is:

```text
application SHA + tooling SHA
        -> release-binding manifest digest
        -> independent-review evidence_archive_sha256
        -> signed approval independent_review.review_receipt_sha256
        -> pre-execution evidence validation
```

This binds release tooling without changing the enrolled issuer utility or
trust registry.

## Baseline versus successor

The protected Beta baseline is evidence, not a qualification target for the
successor's security checks. If the baseline reports an elevated
`acp_enterprise` PostgreSQL role, zero forced-RLS coverage, an older backend
image, or older environment configuration, those are recorded as baseline
deficiencies. The authorized transition must verify that the successor changes
those properties during Stage F and that the successor passes the Stage-G
runtime checks. The baseline is not modified merely to make pre-signing checks
pass.

## Protected configuration contract

Before Stage D, the protected release operator must validate the complete
mode-0600 environment and mounted secret set without printing values:

- `DATABASE_URL` points to the runtime database as `acp_app` and is separate
  from `MIGRATION_DATABASE_URL`, which points to `acp_migrate`.
- Backup configuration names `acp_backup`, its protected secret mount, and a
  separate backup destination.
- Redis URL, ACL identity, health identity, ACL file, and health secret are
  present and mounted read-only.
- Authentication signing keys, issuer, audience, and identity-delivery
  references are present without exposing secret material.
- Smoke token file, `SMOKE_COMPANY_ID`, `SMOKE_BRANCH_ID`, and
  `SMOKE_DENIED_COMPANY_ID` are present. `SMOKE_COMPANY_ID` must be resolved
  from the protected tenant database and match the company membership of the
  approved smoke principal; it must never be copied from a fixture or guessed.
- Every required executable is present in the exact successor image, including
  the PostgreSQL, Redis, backend, authentication, authorization, tenant,
  background-service, route, schema, and release-metadata probes.

Missing or inconsistent values remain `BLOCKED`; no identifier or credential is
invented. Protected values are checked by name, owner, mode, mount, and
non-secret digest only.

## Rollback contract

The rollback target is the actual healthy deployed predecessor, not merely an
older retained directory. The operator must bind its immutable application
artifact, compatible configuration contract, current schema compatibility,
credential requirements, health result, and restore procedure. Application
rollback precedes any database restoration; schema downgrade is not an
automatic rollback.

For the current Beta baseline, the verified immediate target is
`enterprise-beta-3d415c07`
(`3d415c07f4438bbb0cdd93bbf7c6a78f3798457c`). The older
`enterprise-beta-33f9aca5` is only the predecessor recorded by that release and
must not be substituted as the successor's rollback target without a separate
compatibility rehearsal.

