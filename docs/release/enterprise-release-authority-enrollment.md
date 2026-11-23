# Permanent Beta Enterprise release authority

## Roles

- **Authority:** `twelvehats-beta-release-authority`
- **Human custodian:** Michael Fouse (`michael-fouse`)
- **Scope:** `BETA_PREVIEW` only
- **Independent reviewer:** the owner-enrolled qualification reviewer, which must
  differ from the custodian and candidate developer
- **Authority workstation:** Laptop Master

The custodian controls the encrypted Ed25519 private key. The independent
reviewer produces an immutable `enterprise-release-independent-review/v1`
receipt; they do not receive the authority private key. A candidate developer
may request a release but cannot enroll, review, or sign it.

## One-time owner enrollment

The reviewed authority bundle is installed outside Git at a digest-pinned path,
for example:

```text
/Users/michaelfouse/ReleaseAuthority/TwelveHats/tooling/<bundle-sha256>/
```

The owner opens an interactive terminal on Laptop Master and runs:

```sh
python3 /Users/michaelfouse/ReleaseAuthority/TwelveHats/current/enterprise_release_authority.py \
  enroll \
  --authority-root /Users/michaelfouse/ReleaseAuthority/TwelveHats/custody \
  --custodian-id michael-fouse \
  --custodian-name "Michael Fouse" \
  --reviewer-id "$APPROVED_REVIEWER_ID" \
  --reviewer-name "$APPROVED_REVIEWER_NAME" \
  --owner-approval-id "$OWNER_APPROVAL_UUID" \
  --validity-days 90
```

The command requires a real terminal, the exact phrase
`ENROLL TWELVEHATS BETA AUTHORITY`, and a twice-entered passphrase of at least
16 characters. The passphrase is never accepted on a command line, environment
variable, file, log, or chat. Store it in the owner's approved password manager
and offline recovery custody.

Enrollment creates mode-`0700` custody directories and mode-`0600` encrypted
PKCS#8 private key, public key, trust registry, enrollment receipt, and
hash-chained audit log. Only the public key, trust registry, key ID, and
enrollment receipt are registered in protected Beta release custody.

## Independent review and issuance

The independent reviewer receives an immutable evidence archive and produces a
mode-`0600` review receipt using
`docs/release/enterprise-independent-review.schema.json`. Review is admissible
only when every mandatory gate passed, `defects` is empty, `decision` is
`APPROVE`, and the receipt is no more than 72 hours old.

After a fresh protected backup and isolated restore exist, the custodian runs the
issuer interactively. The issuer checks exact bindings, reviewer enrollment,
key status and expiry, private/public key correspondence, and the maximum
24-hour approval lifetime. It writes a mode-`0600` artifact and a hash-chained
audit event; it never deploys.

## Rotation

Rotate at or before 90 days, on suspected exposure, or when custodian authority
changes. Rotation requires the current private-key passphrase, a new twice-entered
passphrase, an owner approval UUID, and the phrase
`ROTATE TWELVEHATS BETA AUTHORITY KEY`. The predecessor becomes
`verification_only` for at most 24 hours so already-issued approvals can expire;
it cannot issue new approvals. Register the new public key and key ID atomically.

## Revocation

Revocation requires the affected private-key passphrase, owner approval UUID,
reason, and the phrase `REVOKE TWELVEHATS BETA AUTHORITY KEY`. The registry marks
the key revoked immediately. Validators reject all artifacts from a revoked key.
Remove the corresponding protected Beta trust binding, preserve the public key
and receipts as revoked audit evidence, rotate any successor, and investigate.

If the private key is unavailable, the owner performs emergency revocation by
removing the protected public-key/key-ID binding and recording a separately
signed incident receipt before enrolling a replacement.

## Circular-prerequisite resolution

There are two decisions, not one circular GO:

1. **Preflight authority:** owner enrollment permits read-only qualification and
   a fresh backup/isolated restore. It does not authorize deployment.
2. **Candidate approval:** after those receipts and independent review exist, the
   authority signs the exact Beta change set. This authorizes the bounded change
   window, not final acceptance.
3. **Final Release GO:** recorded only after deployment, authenticated smoke,
   tenant isolation, operational acceptance, and monitoring pass. Failure before
   final GO invokes the preapproved rollback.

Short-lived release-actor and acceptance-reader principals are provisioned only
inside the authorized change window after the schema and protected runtime are
ready. Their absence therefore cannot block the preflight backup or signing
ceremony, while their post-deployment failure still blocks final GO.

## Audit and recovery

- Verify `audit/events.ndjson` before and after every authority operation.
- Seal the authority bundle, registry, public key, enrollment receipt, approval,
  independent review, backup/restore receipts, and qualification packet by SHA-256.
- Back up only the encrypted private key and owner-approved metadata through
  encrypted offline custody; never place them in Git or Beta.
- Rehearse public-key replacement and audit recovery quarterly without signing an
  application candidate or deploying.
