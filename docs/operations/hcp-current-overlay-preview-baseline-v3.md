# HCP current overlay Preview-baseline reconciliation

`MIGRATION.HCP.CURRENT.OVERLAY.PREVIEW.BASELINE.RECONCILIATION.1` preserves the
accepted v2 packet and produces a separate, non-executable v3 reconciliation.
It classifies all 503 predecessor assertions against immutable Preview evidence.

## Result

- Path: `/Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-overlay-preview-baseline-v3/successor-overlay.json`
- Contract: `hcp-current-overlay-merge-packet/v3`
- Semantic digest: `919d9bed1899516f760f47671222cbb4868aca4fdb5242611a4997822472d356`
- File SHA-256: `8d5d0a66915b571608662dc9fd8fef07ee17d0225627ac6e00c1b556ab194764`
- Directory/file mode: `0700` / `0600`
- CREATE_NEW: 146
- REUSE_EXISTING: 0
- UPDATE_EXISTING: 5
- HOLD: 352

The result is **not ready for guarded execution**. The v2 overlay omitted 19
members of the accepted current graph because it assumed sealed SOURCE.4 base
admission had already occurred. Preview has no SOURCE.4 master run. The v3
record sweep therefore holds dependent graph records instead of leaving orphan
truth.

Current 11/11/15/18 dispositions:

| Domain | CREATE_NEW | UPDATE_EXISTING | HOLD | Missing from v2 |
| --- | ---: | ---: | ---: | ---: |
| Customers | 6 | 3 | 0 | 2 |
| Locations | 4 | 0 | 0 | 7 |
| Jobs | 4 | 0 | 6 | 5 |
| Appointments | 6 | 0 | 7 | 5 |

The 19 missing records and every current hold are embedded in
`dependency_completeness` / `current_graph`. No first-write discovery is
permitted. The next authority must add mechanically derived, sealed SOURCE.4
intent for those 19 records and recompute their 13 dependent current holds; it
must not reinterpret any historical hold.

## Deterministic verification

From `backend`:

```bash
python -m scripts.hcp_preview_baseline_reconciliation \
  --overlay /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-admission-packet-20260912T170000Z/current-overlay-merge-packet.json \
  --hold /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-admission-packet-20260912T170000Z/current-operational-hold-dispositions.json \
  --cohort /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-source4-update-cohort-authority-v1/update-cohort-authority.json \
  --runtime /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-preview-baseline-20260914/runtime-successor-inventory.json \
  --baseline /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-preview-baseline-20260914/preview-native-baseline-final.json \
  --classifier /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-admission-packet-20260912T170000Z/legacy-classification.json \
  --successor-manifest /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-admission-packet-20260912T170000Z/successor-manifest.json \
  --refresh-root /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-refresh-20260912T120000Z \
  --schedule-root /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-open-schedule-20260912T170000Z \
  --output /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-overlay-preview-baseline-v3/successor-overlay.json \
  --verify
```

## Execution-authority successor

Enterprise must not execute v2 or this blocked v3 artifact. A future authority
must bind the v3 file and semantic digests, all predecessor evidence digests,
the unchanged Preview baseline or a freshly reconciled replacement, the sealed
19-record SOURCE.4 completion packet, protected/deployed SHA, schema head,
Company/Branch, backup and verified restore receipt, hold packet, idempotency
identity, and the final dependency-completeness digest. It may become executable
only when all 55 current graph records have an admitted disposition and none is
HOLD or unresolved.
