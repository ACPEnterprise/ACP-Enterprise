# HCP operational cutover isolated-clone rehearsal

This packet consumes the already sealed operational HCP gate. It performs no HCP
acquisition and authorizes no Preview or Production access. All evidence roots are
private (`0700`) and every evidence file is sealed `0600`.

## Required inputs

- `gate-packet.json` from the fresh operational finalization
- the final sealed operational disposition policy resolving the two original-gate
  omissions
- the last admitted cutoff and base SOURCE.4 digest
- ACP Company and Branch UUIDs for the isolated clone
- `isolated-clone-native-observations.json`, exported read-only from the fresh clone
- a clone backup plus a verified restore receipt using contract
  `hcp-isolated-clone-restore-receipt/v1`

The restore receipt must contain `restore_verified: true`, database
`acp_hcp_rehearsal_import`, the exact backup digest, and the current Alembic head.

## 1. Validate the fresh gate now

```bash
umask 077
export GATE_PACKET=/absolute/private/gate/gate-packet.json
export FINAL_OPERATIONAL_POLICY=/absolute/private/policy/final-operational-cutover-disposition.json
export GATE_VALIDATION_ROOT=/absolute/private/rehearsal/gate-validation

PYTHONPATH=backend python \
  backend/scripts/prepare_hcp_continuous_delta_rehearsal.py validate-gate \
  --gate-packet "$GATE_PACKET" \
  --final-policy "$FINAL_OPERATIONAL_POLICY" \
  --output "$GATE_VALIDATION_ROOT"
```

The command recomputes every manifest digest, every raw response/page seal, every
attachment-body digest and custody seal, lineage between all manifests, exact
classification totals, final-policy reconciliation, open-work hold propagation, and
technician dispositions. It expects the sealed original-gate counts—404 open Jobs,
547 Appointments, 633 Customers, 966 Locations, five Employees, 37 absent technician
identities, 22 originally enumerated Location-less Jobs, 13 legacy Appointment holds,
2,065 original-gate holds, 621 attachment bodies, and zero Appointment relationship
HTTP 400 failures—then verifies the final exact-ID policy expands operational holds to
23 Location-less Jobs, 30 held Appointments (including the unassigned Appointment and
parent cascades), four held Locations, and 67 operational holds total. The two
original-gate omissions cannot execute.

## 2. Consume native observations

Run immediately after the read-only native observation appears:

```bash
umask 077
export NATIVE_OBSERVATIONS=/absolute/private/clone/isolated-clone-native-observations.json
export DELTA_ROOT=/absolute/private/rehearsal/continuous-delta
export LAST_ADMITTED_CUTOFF=2026-09-12T23:59:59Z
export BASE_SOURCE4_DIGEST=4a4a9582d7fde37dba73ba9e93db5669d9341768c7f5741f6e8916971fd9ec60
export ACP_COMPANY_ID=3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd
export ACP_BRANCH_ID=887f413a-70dc-4ab1-98aa-8e84f4e7efd0

PYTHONPATH=backend python \
  backend/scripts/prepare_hcp_continuous_delta_rehearsal.py consume-native \
  --gate-packet "$GATE_PACKET" \
  --final-policy "$FINAL_OPERATIONAL_POLICY" \
  --native-observations "$NATIVE_OBSERVATIONS" \
  --cutoff "$LAST_ADMITTED_CUTOFF" \
  --base-source4-digest "$BASE_SOURCE4_DIGEST" \
  --company-id "$ACP_COMPANY_ID" \
  --branch-id "$ACP_BRANCH_ID" \
  --output "$DELTA_ROOT"
```

Stop if the native file has an unknown identity, the provider chronology is outside
the delta window, any source/native digest is malformed, or any gate byte has drifted.
The output contains the deterministic decision plan and executable overlay separately.

## 3. Bind clone authority

After the clone backup and restore verification exist:

```bash
export CLONE_BACKUP=/absolute/private/clone/pre-delta.dump
export CLONE_RESTORE_RECEIPT=/absolute/private/clone/restore-receipt.json
export CLONE_AUTHORITY_DIR=/absolute/private/rehearsal/authority
export CLONE_AUTHORITY="$CLONE_AUTHORITY_DIR/continuous-delta-authority.json"
export ALEMBIC_HEAD=yp8r0t2v4x6z
export REHEARSAL_ACTOR_ID=c427ebd1-7583-4c0d-9c54-55a0c1214174

install -d -m 0700 "$CLONE_AUTHORITY_DIR"
PYTHONPATH=backend python \
  backend/scripts/prepare_hcp_continuous_delta_rehearsal.py prepare-authority \
  --rehearsal-manifest "$DELTA_ROOT/rehearsal-manifest.json" \
  --backup "$CLONE_BACKUP" \
  --restore-receipt "$CLONE_RESTORE_RECEIPT" \
  --expected-schema-head "$ALEMBIC_HEAD" \
  --actor-id "$REHEARSAL_ACTOR_ID" \
  --output "$CLONE_AUTHORITY"
```

## 4. Qualify, execute, and prove exact replay

The command rejects non-loopback hosts, every database except
`acp_hcp_rehearsal_import`, enabled Preview/Production access, repository or schema
drift, incomplete SOURCE.4 lineage, unsafe evidence modes, and unprovable UPDATE
successor bindings.

```bash
export TARGET_ENVIRONMENT=migration_rehearsal
export ENVIRONMENT=migration_rehearsal
export PREVIEW_ACCESS_ENABLED=false
export PRODUCTION_ACCESS_ENABLED=false
export DATABASE_URL='postgresql+asyncpg://acp_hcp_rehearsal:<secret>@127.0.0.1:5432/acp_hcp_rehearsal_import'

cd backend
python -m app.operational_migration.hcp_continuous_delta_rehearsal_command \
  qualify --authority-file "$CLONE_AUTHORITY"

python -m app.operational_migration.hcp_continuous_delta_rehearsal_command \
  execute --authority-file "$CLONE_AUTHORITY" --authorize-execution \
  > /absolute/private/rehearsal/first-receipt.json

python -m app.operational_migration.hcp_continuous_delta_rehearsal_command \
  replay --authority-file "$CLONE_AUTHORITY" --authorize-execution \
  > /absolute/private/rehearsal/replay-receipt.json
cd ..
```

The first and replay outputs must have the same receipt, manifest digest, counts,
journal count, and idempotency identity. The replay must add zero native rows, source
bindings, holds, receipts, or Business Events. Capture before/after read-only counts
and event digests around both calls.

## 5. Real-data operational acceptance

Export a read-only projection bundle from the clone and run:

```bash
PYTHONPATH=backend python backend/scripts/operational_realdata_acceptance.py \
  --input /absolute/private/rehearsal/realdata-projection-bundle.json \
  --output /absolute/private/rehearsal/realdata-acceptance.json
```

Acceptance checklist:

- CSR: every admitted open Job resolves by source ID to the intended Customer,
  contact, Location, notes, Estimates, invoice/balance evidence, and attachments;
  held Jobs never appear as silently repaired active work.
- Schedule: Day, Week, Work Week, and Month return each admitted scheduled/current
  Appointment once with matching local date, arrival window, duration, lifecycle,
  Customer, Location, and Job.
- Dispatch: the same Appointments appear once; exact current-employee assignments
  match; historical/unresolved technician source IDs remain unassigned and queryable.
- My Day: each safely mapped current technician sees only their assigned current work;
  no former, historical-provider-only, or unresolved identity is impersonated.
- Integrity: no active held source identity, no orphan, no lifecycle regression, no
  cross-Company/Branch row, and zero replay Business Event delta.
- Holds: all 22 Location-less Jobs, 13 legacy Appointment duplicate risks, unsupported
  evidence-only records, and unresolved technician identities remain explicit holds.

No command in this runbook targets HCP, Preview, Production, or a live database.
