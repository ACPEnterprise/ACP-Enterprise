# SOURCE.4 native successor binding bootstrap

This bounded successor closes `OVERLAY_UPDATE_SOURCE_IDENTITY_MISSING` without
weakening compare-before-write or changing any UPDATE to CREATE.

## Accepted UPDATE inventory

The accepted overlay contains exactly 280 UPDATE assertions:

| Domain | UPDATE assertions | Exact accepted predecessor candidates |
| --- | ---: | ---: |
| Customer | 20 | 20 |
| Service Location | 0 | 0 |
| Job | 254 | 254 |
| Appointment | 6 | 6 |
| Other | 0 | 0 |

Each UPDATE has exactly one record with the same provider identity in both
preserved `hcp-migration-1` candidate packets. This establishes the bounded
candidate inventory but does not by itself authorize a database binding. At
execution, the new preflight queries the actual Preview identity tables and
classifies every UPDATE as `BINDING_ALREADY_PRESENT`,
`PROVABLE_NATIVE_SUCCESSOR_BINDING`, `AMBIGUOUS_NATIVE_SUCCESSOR`,
`CONFLICTING_BINDING`, `NATIVE_SUCCESSOR_MISSING`, or `UNSUPPORTED`. The exact
database-derived counts are written into the execution receipt context.

Execution continues only when every UPDATE is already bound or has one exact
legacy provider identity whose native target and parent graph still exist in
the authorized Company/Branch. Any other disposition fails the entire guarded
transaction before native overlay mutation.

The 11/11/15/18 current-calendar closure contains eight UPDATE assertions that
require this check: five supporting Customers and three current Jobs. Accepted
evidence contains one exact predecessor candidate for all eight. Preview will
publish the authoritative split between already-present and newly provable
bindings; none may be silently held or omitted. The first failing Customer
below is a non-current `SAFE_UPDATE`, so its failure does not alter the eight
current-set dependencies.

## First failing Customer

- SOURCE.4 identity: `cus_016ebfb110b148f6b391992d0a859081`
- Accepted predecessor provider-native identity:
  `cus_016ebfb110b148f6b391992d0a859081`
- Sealed predecessor source digest:
  `60349d824094938f3e26a2f5b473dd8aaabd3c8f16f7a3bb05913ef34e24f0f0`
- Current overlay source digest:
  `801e00931240445b625411c2dae4bdfc5448238c90612dfea71c275c69c632f2`
- Current overlay change: accepted `addresses` and `updated_at` delta
- Company: `a56fc415-563b-459c-913f-2e6183109119`
- Branch: `4d6929eb-6941-446c-8667-97892ded14c4`

The accepted predecessor candidate and sealed SOURCE.4 row use the same exact
provider identity; the ACP native UUID is resolved only from Preview's exact
legacy source-identity row and is therefore not guessed or recorded here. No
name, phone, address, or time similarity participates.
Preview execution must additionally find the exact legacy `housecall_pro`
identity targeting that same native Customer. If it does, the bootstrap appends
the `housecall_pro_source4` identity and immutable binding evidence. The normal
overlay lookup then resolves that target and compare-before-write requires the
sealed predecessor digest before applying the current digest. If any part of
that chain differs, execution fails closed.

## Transaction and identity behavior

The guarded v2 command and authority file are unchanged. After all existing
authority, artifact, backup/restore, schema, scope, permission, and concurrency
guards pass, the command:

1. creates/resolves bounded SOURCE.4 run lineage;
2. inventories all UPDATE bindings against locked transaction state;
3. processes the overlay in dependency order;
4. creates an exact successor binding immediately before its UPDATE lookup;
5. applies compare-before-write through the native domain services;
6. persists immutable binding evidence, overlay provenance, Business Events,
   and the execution receipt;
7. commits once.

Supporting Customer/Location/Job identities are added only when an UPDATE
binding requires their exact legacy parent graph. Existing legacy identities
remain unchanged. Unique source and target constraints enforce one SOURCE.4
identity per native record and one native target per SOURCE.4 provider identity.
The binding evidence table adds deterministic source, target, legacy identity,
package, predecessor digest, and binding digest custody.

Any missing, ambiguous, conflicting, cross-scope, or graph-inconsistent binding
rolls back master/child lineage, new identities, native changes, events,
evidence, and receipt together. Replay sees the same binding and target and
does not create duplicates.

## Enterprise execution

After protected integration and migration to schema `h8j0l2n4p6r8`, Enterprise
issues a new mode-0600 authority for the deployed protected SHA and matching
fresh backup/restore receipt. The guarded command remains:

```bash
ENVIRONMENT=preview TARGET_ENVIRONMENT=preview \
PREVIEW_ACCESS_ENABLED=true PRODUCTION_ACCESS_ENABLED=false \
python -m app.operational_migration.hcp_current_overlay_command \
  --authority-file "$AUTHORITY_FILE" \
  --authorize-preview-execution
```

The current-calendar acceptance target remains 11 Customers, 11 Locations, 15
Jobs, and 18 Appointments. Enterprise must publish the database-derived binding
inventory and post-admission native-binding snapshot; this lane has not queried
or mutated Preview.
