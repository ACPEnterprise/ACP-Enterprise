# HCP historical safe tranche 1

Date: 2026-09-12

Protected authority: `9096a77705623409da1418022c7949cae08468ce`

Required predecessors:

- Native executor: `5b8b02deb3f76172d8fe6666a11dda071cee0fbe`
- Post-admission acceptance: `83bbeef03d3a6be1d25c5058be62df79e5f97817`
- Acceptance plan digest: `64af7e1130e984679cb955043a6449ff4c13c92a82785c64af0db3551dee23ce`
- Overlay manifest digest: `e23b7bcf5ac34ea650184afacc711af0c7028e83a6b1f7405e2ae17e13441eb2`
- Overlay file SHA-256: `ce9d4ea1e048a70b7a8a5b85fab33fd1a0568eb5cb1356229187144ab8bc7558`

Neither predecessor was present in protected authority when this lane began.
Enterprise must integrate them before executing either current or historical
admission. The current 11/11/15/18 operational admission remains first priority
and is not gated by this historical packet.

## Deterministic population

The packet includes exactly the previously accepted 186 records and no others:

| Domain | SAFE_HISTORICAL | SAFE_UPDATE | Total |
| --- | ---: | ---: | ---: |
| Customers | 51 | 15 | 66 |
| Locations | 37 | 0 | 37 |
| Jobs | 27 | 22 | 49 |
| Appointments | 34 | 0 | 34 |
| Total | 149 | 37 | 186 |

Every row carries its source identity, optional native identity, Company and
Branch, lifecycle/status, parent keys, source and prior-source digests,
acquisition timestamp, payload, and a derived provenance digest. The builder
verifies the immutable acceptance-plan digest, overlay file and manifest
digests, exact 149/37 membership, supported lifecycle, assertion consistency,
source freshness for updates, scope, and graph dependencies.

The identifier-bearing packet is retained in the sanctioned Migration evidence
store rather than Git. Its no-binding preflight digest is
`c095ddaf349963ecf45ab0e1826b4a217152df7f243e5ca3a6b36387f882d85f`.

## Dependency-safe readiness

Before the first current admission receipt/native snapshot exists, 94 records
form a closed mechanically safe create graph:

- Customers: 51
- Locations: 29
- Jobs: 11
- Appointments: 3

The other 92 remain explicitly held pending read-only native binding evidence:

- 15 Customer safe updates
- 22 Job safe updates
- 8 historical Locations
- 16 historical Jobs
- 31 historical Appointments

Dependency edges requiring evidence are 45 sealed-base parents, six current
packet parents, and 11 held-overlay Job parents. There are 107 intra-tranche
edges. The 11 Appointment-to-held-Job edges are not guessed: each Appointment
requires proof that its source Job already binds a compatible native Job.

This is not a reclassification. All 186 retain their accepted
`SAFE_HISTORICAL` or `SAFE_UPDATE` classification; `ADMIT`/`HOLD` describes only
whether current binding evidence closes the graph. The packet correctly reports
`execution_allowed: false` until the required native evidence is supplied.

## Build command

```bash
ENVIRONMENT=preview PYTHONPATH=backend python \
  backend/scripts/hcp_historical_safe_tranche.py \
  --overlay "$OVERLAY_PACKET" \
  --acceptance-plan "$ACCEPTANCE_PLAN" \
  --protected-authority "$DEPLOYED_PROTECTED_SHA" \
  --native-bindings "$READ_ONLY_NATIVE_BINDINGS" \
  --output "$HISTORICAL_TRANCHE_PACKET"
```

Omit `--native-bindings` only for the pre-execution dependency report. Binding
evidence uses contract `hcp-native-binding-snapshot/v1`, declares
`mutation_authority: none`, carries a canonical digest, and contains record-level
domain/source/native IDs, Company, Branch, and source digest. Duplicate source
or native identities, mismatched scope, and conflicting source versions fail
closed.

Protected movement changes only `protected_authority` and consequently the
packet digest. It must not change membership or classifications. Regenerate
after protected integration and compare the record projection after removing
only `protected_authority`, `digest`, native binding fields, readiness, and hold
reason.

## Enterprise execution support

Enterprise first completes the current overlay admission and its read-only
post-execution acceptance. The resulting exact source/native binding snapshot
is then supplied to this builder. A historical execution packet is qualified
only when:

- schema has one head and current=head/zero drift;
- deployed SHA equals packet authority;
- current execution receipt and replay acceptance pass;
- every admitted historical parent is in this tranche or has an exact native
  binding;
- safe updates have exact native identities and compatible prior source digests;
- all Company/Branch checks pass;
- no unsupported lifecycle transition enters `ADMIT`;
- the historical packet remains distinct from the current idempotency receipt.

No historical live execution command is introduced by this candidate. Binding
the packet to a guarded mutating command requires Enterprise integration review,
backup/restore authority, and PostgreSQL qualification. This lane performs no
Preview, HCP, QBO, Production, or financial mutation.

## Next safe family

After the current admission snapshot, reconcile the 92 binding-dependent rows
in this order: 37 safe updates, eight Locations, 16 Jobs, then 31 Appointments.
The 11 Appointments whose Jobs remain held stay held unless the snapshot proves
an already-existing compatible native Job. Historical cleanup never blocks the
current operational calendar.
