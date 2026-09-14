# SOURCE.4 authority-successor exact replay

`MIGRATION.HCP.SOURCE4.AUTHORITY.SUCCESSOR.REPLAY.1` is a read-only verifier for
an already-committed `hcp-current-overlay-merge-packet/v4` execution. It never
enters `CurrentOverlayExecutor`, never establishes lineage, and never calls a
native mutation service.

## Authority contract

Enterprise seals a mode-0600 JSON document using contract
`hcp-source4-authority-successor-replay/v1` and purpose
`EXACT_REPLAY_VERIFICATION`. It binds:

- original protected/deployed SHA, executor version, schema head, authority-file
  path/SHA-256, backup digest, restore-receipt digest, execution timestamp, and
  durable receipt digest;
- successor protected/deployed SHA, verifier version
  `migration.hcp.source4.authority.successor.replay.1`, current schema head,
  expected Preview database, actor, and schema-semantic digest;
- Company/Branch, v4 path/file/semantic digests, complete graph, SOURCE.4,
  predecessor overlays, holds, cohort, runtime inventory, Preview baseline, and
  idempotency identity;
- sealed post-execution digests for source bindings, native rows, hold rows,
  Business Events plus their count, and child lineage.

The schema-semantic digest is printed by the command and is derived from the
specific master/child, hold, event, source-identity, v4, and receipt contracts
used by the verifier. A schema advance is accepted only when this digest remains
the explicitly sealed current value.

## Complete read-only preflight

The verifier uses a PostgreSQL read-only transaction and accumulates all
record-level mismatches. It proves one successful original master, the unchanged
original authority and timestamp, exactly one Customer and Operational child,
the original immutable receipt and execution context, exact 174/4/5/339 outcome
accounting, all 522 journal entries, all 183 admitted source bindings and native
targets, 339 non-mutating holds, native post-state, and the bounded Business
Event set. It also rejects any artifact, scope, idempotency, schema-semantic, or
successor-authority mismatch.

Success returns `EXACT_REPLAY_VERIFIED_EXISTING_EXECUTION`, the original receipt
digest, and `mutation_count: 0`. It creates no successor database row and does
not alter the original master or receipt.

## Enterprise command

After integrating and deploying the exact successor verifier, seal the authority
file and run from `backend`:

```console
TARGET_ENVIRONMENT=preview PREVIEW_ACCESS_ENABLED=true \
PRODUCTION_ACCESS_ENABLED=false \
python -m app.operational_migration.hcp_source4_authority_successor_replay_command \
  --authority-file /absolute/sanctioned/source4-replay-successor-authority.json \
  --verify-exact-replay
```

The expected successful `receipt_digest` is
`24a5cd302745352bd005f1e72996f61131dc9db32214c50f0e635d07863c24dd`.
This development lane did not connect to or mutate Preview.

Protected PostgreSQL qualification must cover original-authority immutability,
identical receipt return, zero writes/events/bindings, exact repeated replay,
all specified mismatch families, and fresh zero-to-head/current=head/one-head/
zero-drift checks.
