# HCP current overlay: Enterprise execution and acceptance packet

Date: 2026-09-12  
Executor candidate: `5b8b02deb3f76172d8fe6666a11dda071cee0fbe`  
Executor development authority: `d52d117801d72d04e81afac157671c97a941efa0`  
Acceptance development authority: `8cf3bdbf0c814c4a45f2b189b061db556d1c704f`  
Schema head: `d4f6h8j0l2n4`

The required execution authority is the exact deployed protected SHA produced by
Enterprise after integrating the executor candidate. It must not be substituted
with either development authority above.

## Sealed inputs

- Overlay contract: `hcp-current-overlay/v1`
- Overlay manifest digest: `e23b7bcf5ac34ea650184afacc711af0c7028e83a6b1f7405e2ae17e13441eb2`
- Overlay file SHA-256: `ce9d4ea1e048a70b7a8a5b85fab33fd1a0568eb5cb1356229187144ab8bc7558`
- Hold packet SHA-256: `c13cb0b565d2b86d34365f12d565f37f0e7ba6ec6bfa0d65de7f4a81ee088324`
- Acceptance plan contract: `hcp-current-overlay-post-admission-acceptance/v1`
- Acceptance plan digest for the sealed local evidence: `64af7e1130e984679cb955043a6449ff4c13c92a82785c64af0db3551dee23ce`

The acceptance plan contains source identifiers and therefore remains in the
sanctioned Migration evidence store; it is not committed to Git.

## Pre-execution reconciliation

| Domain | Packet assertions | Deterministic classifications |
| --- | ---: | --- |
| Customers | 55 create, 20 update, 1 removal | 9 supporting current parents, 51 safe historical, 15 safe update, 1 held removal |
| Locations | 41 complete-address create, 22 incomplete-address hold | 4 supporting current parents, 37 safe historical, 22 held |
| Jobs | 34 create, 25 safe update, 252 hold | 10 current operational, 27 safe historical, 22 safe update, 252 held |
| Appointments | 47 create, 6 update | 13 current operational, 34 safe historical, 6 held lifecycle updates |

The raw Job packet contains 49 create, 254 update, and 8 explicit hold
assertions. Native lifecycle qualification converts 15 creates and 229 updates
to hold. Of the 25 safe updates, three belong to the current-calendar set and
are classified `CURRENT_OPERATIONAL`; the other 22 are classified
`SAFE_UPDATE`. Together with the eight explicit holds this yields exactly 252
Job holds. Acceptance uses the record-level plan and receipt, not totals alone.

There are 503 packet assertions. Of these, 222 are mechanically writable or
replayable and 281 are held. Classification totals are:

- `CURRENT_OPERATIONAL`: 23
- `SAFE_SUPPORTING_PARENT`: 13
- `SAFE_HISTORICAL`: 149
- `SAFE_UPDATE`: 37
- `HELD`: 281

The current-calendar closure is 11 Customers, 11 Locations, 15 Jobs, and 18
Appointments (55 records). Thirty-six appear in the overlay (13 supporting
parents and 23 operational children); nineteen already resolve through the
sealed base/native lineage and require no overlay write. The other 186 safe
packet records are historical or non-current compare-before-write work. This is
why total safe write/replay scope is larger than current-calendar scope.

No record is eligible without one of the five classifications in the immutable
acceptance plan. `HELD` is never an active-native outcome.

## Authority file

The authority file must be mode `0600`, use contract
`hcp-current-overlay-native-execution/v1`, and contain exactly:

```text
expected_repository_sha
expected_schema_head
expected_database
company_id
branch_id
actor_id
master_run_id
customer_run_id
operational_run_id
overlay_path
overlay_file_digest
overlay_manifest_digest
hold_path
hold_digest
classification_path
classification_digest
classification_result_digest
expected_base_source4_digest
backup_path
backup_digest
restore_receipt_path
restore_receipt_digest
idempotency_identity
zero_migration_drift
expected_classification_admission_allowed
current_operational_admission_allowed
```

`expected_repository_sha` is the deployed protected SHA;
`expected_schema_head` is `d4f6h8j0l2n4`; both admission booleans and
`zero_migration_drift` must be true. The restore receipt must have contract
`preview-isolated-restore-receipt/v1`, the same backup digest, the same schema
head, and `restore_verified: true`. The idempotency identity is SHA-256 over the
canonical JSON object containing contract, manifest digest, backup digest,
Company ID, and Branch ID, as enforced by the executor.

## Guarded execution

Only Enterprise runs this in the sanctioned Preview environment after backup
and isolated restore verification:

```bash
ENVIRONMENT=preview TARGET_ENVIRONMENT=preview \
PREVIEW_ACCESS_ENABLED=true PRODUCTION_ACCESS_ENABLED=false \
python -m app.operational_migration.hcp_current_overlay_command \
  --authority-file "$AUTHORITY_FILE" \
  --authorize-preview-execution
```

Expected mutation boundary: at most 222 create/update/reuse operations, plus
281 durable held/removal journal outcomes, all inside the executor's guarded
transaction. Exact created/reused/updated counts are determined from the
compare-before-write receipt. No Preview mutation occurs from the acceptance
commands below.

## Read-only post-execution acceptance

First rebuild the sealed plan and require its digest to remain the value above:

```bash
ENVIRONMENT=preview PYTHONPATH=backend python \
  backend/scripts/hcp_post_admission_acceptance.py build \
  --overlay "$OVERLAY_PACKET" \
  --refresh-root "$CURRENT_REFRESH_ROOT" \
  --schedule-root "$CURRENT_SCHEDULE_ROOT" \
  --cutoff 2026-09-12 \
  --output "$ACCEPTANCE_PLAN"
```

Export the persisted execution receipt and a sanctioned read-only native
snapshot. The snapshot must contain exact source/native bindings and evidence
digests, parent checks, Company/Branch checks, lifecycle checks, Day/Week/Work
Week/Month/Dispatch membership, held-active identities, orphan count, replay
Business Event delta, technician holds, and Location gaps. Then run:

```bash
ENVIRONMENT=preview PYTHONPATH=backend python \
  backend/scripts/hcp_post_admission_acceptance.py verify \
  --plan "$ACCEPTANCE_PLAN" \
  --receipt "$EXECUTION_RECEIPT" \
  --snapshot "$READ_ONLY_NATIVE_SNAPSHOT" \
  --output "$ACCEPTANCE_RESULT"

ENVIRONMENT=preview PYTHONPATH=backend python \
  backend/scripts/operational_realdata_acceptance.py \
  --input "$REALDATA_PROJECTION_BUNDLE" \
  --output "$REALDATA_ACCEPTANCE_RESULT"
```

Replay the guarded command with the identical authority file, export the replay
receipt, and require byte-equivalent semantic receipt evidence plus zero
Business Event delta:

```bash
ENVIRONMENT=preview PYTHONPATH=backend python \
  backend/scripts/hcp_post_admission_acceptance.py verify \
  --plan "$ACCEPTANCE_PLAN" \
  --receipt "$EXECUTION_RECEIPT" \
  --replay-receipt "$REPLAY_RECEIPT" \
  --snapshot "$READ_ONLY_REPLAY_SNAPSHOT" \
  --output "$REPLAY_ACCEPTANCE_RESULT"
```

Acceptance fails closed on missing/duplicate source bindings, duplicate native
truth within a domain, orphan graphs, lifecycle regression, cross-scope data,
calendar mismatch, held identities in active truth, or replay-created Business
Events. The 18 current Appointments must have matching local date, arrival
window, duration, status, technician/unassigned truth, cancellation/completion
state, all three parents, and all five Schedule/Dispatch lanes. Expected current
technician holds and Location gaps are both zero.

## Hold acceptance and next historical tranche

The active snapshot must exclude all 461 historical Appointment projections,
13 legacy Appointment holds, 22 Location-unresolved Jobs, the 252 packet Job
lifecycle/evidence holds, and every unsupported lifecycle/evidence assertion.
These families can overlap and must be reconciled by source identity, not added
as if disjoint.

The next mechanically safe historical tranche is the 149 `SAFE_HISTORICAL`
records plus 37 `SAFE_UPDATE` compare-before-write records already listed in
the sealed plan. They remain separate from current operational acceptance and
must not be expanded to include any held identity. The 281 held packet records
require stronger lifecycle, address, or removal authority before a later
admission.

## Failure and rollback acceptance

On any guarded failure, the migration transaction must roll back with identical
before/after native and Business Event digests, no persisted success receipt,
and no partial aggregate. Capture that external failure evidence and run:

```bash
ENVIRONMENT=preview PYTHONPATH=backend python \
  backend/scripts/hcp_post_admission_acceptance.py verify-failure \
  --evidence "$FAILED_EXECUTION_EVIDENCE" \
  --output "$FAILED_EXECUTION_ACCEPTANCE"
```

A database receipt cannot truthfully be committed inside a transaction that
rolled back. The command failure plus before/after digests is therefore the
failure-state evidence; only a successful atomic run persists the idempotent
receipt. A failed run is replayable after its cause is corrected. A successful
run returns the prior receipt on replay. The advisory run lock must reject a
concurrent executor. Restore is an Enterprise-controlled contingency and must
correspond exactly to the backup digest in the authority and execution receipt;
the acceptance lane never performs a destructive restore.

## Qualification

The readiness lane was qualified with repository-supported CPython 3.12.13.
Focused acceptance and operational-measurement tests pass (`67 passed`), and
Ruff, MyPy, compilation, diff validation, and the real sealed-artifact rebuild
pass. The rebuilt plan reproduces digest
`64af7e1130e984679cb955043a6449ff4c13c92a82785c64af0db3551dee23ce`.

The broader operational-migration suite reports `255 passed, 11 failed`; all 11
fail before test setup because this shell has neither Docker nor a resolvable
PostgreSQL host named `postgres`. This is an environment limitation, not an
application assertion failure. Protected integration must run the full affected
suite and fresh zero-to-head/current=head/zero-drift checks in the sanctioned
PostgreSQL-backed CI runtime before Preview execution.
