# HCP historical population reconciliation

The read-only reconciliation command compares two sealed snapshots without
creating, merging, updating, or deleting ACP or HCP records. It reports missing
and added provider identities, duplicate native Customer targets, explicit
Customer merges, missing Locations, orphaned Jobs and Appointments,
source-to-target identity changes, excluded/held historical records, duplicate
snapshot rows, and provenance changes.

Laptop Master or the independent reviewer can run it inside approved custody:

```bash
umask 077
cd backend
PYTHONPATH=. python scripts/reconcile_hcp_historical_population.py \
  --previous /protected/hcp/restored-population-snapshot.json \
  --current /protected/hcp/current-runtime-population-snapshot.json \
  --output /protected/hcp/historical-population-reconciliation.json
```

Each input must contain `snapshot_id`, `acquired_at`, `provenance_digest`, and a
`records` array. Records carry domain, provider source ID, optional native target
ID, parent source keys, source digest, admission disposition, and optional merge
successor. The mode-0600 output is reproducible and includes a canonical digest.

The reported 5,524/735/1,039 and 635/699/1,005 populations are not embedded as
truth in the implementation. Protected execution must derive exact counts and
identity-level differences from sealed inputs. Synthetic qualification does not
establish actual All County recovery or explain the discrepancy.
