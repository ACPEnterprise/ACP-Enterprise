# SOURCE.4 accepted artifact recovery

Date: 2026-09-12

Milestone: `MIGRATION.SOURCE4.ACCEPTED.ARTIFACT.RECOVERY.1`

Outcome: the exact accepted immutable artifacts were recovered in the sanctioned
ACP Migration evidence store. No regeneration, reclassification, Preview access,
or source-system access was performed.

## Recovered authority

Sanctioned root:

```text
/Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-admission-packet-20260912T170000Z
```

Overlay:

```text
/Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-admission-packet-20260912T170000Z/current-overlay-merge-packet.json
SHA-256 ce9d4ea1e048a70b7a8a5b85fab33fd1a0568eb5cb1356229187144ab8bc7558
size 1993952 bytes
owner michaelbfouse
group staff
mode 0600
```

Hold packet:

```text
/Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-admission-packet-20260912T170000Z/current-operational-hold-dispositions.json
SHA-256 c13cb0b565d2b86d34365f12d565f37f0e7ba6ec6bfa0d65de7f4a81ee088324
size 21990 bytes
owner michaelbfouse
group staff
mode 0600
```

The overlay is contract `hcp-current-overlay/v1`, contains exactly 503 records,
and passes `CurrentOverlayManifest.load`. Its embedded canonical manifest digest
is:

```text
e23b7bcf5ac34ea650184afacc711af0c7028e83a6b1f7405e2ae17e13441eb2
```

That manifest digest is not the byte SHA-256 of the separate historical
`successor-manifest.json`. It is the executor-verified canonical digest embedded
in the recovered overlay file; substituting the successor manifest as the
overlay artifact would fail correctly.

The overlay binds:

```text
base SOURCE.4 digest 4a4a9582d7fde37dba73ba9e93db5669d9341768c7f5741f6e8916971fd9ec60
delta digest         8a2caa60a3b2761ceeebb2cedf337e2f5efb6d929e7d0e4b634aca2526664abf
```

The hold packet binds the same delta digest. It contains 13 Appointment holds
(10 duplicate-risk and 3 insufficient-evidence) and 22 Location-unresolved Job
holds, with zero true global blockers. This relationship mechanically ties both
recovered files to the same accepted overlay generation.

## Enterprise verification and staging

Run on the host that contains the sanctioned source directory before copying:

```bash
SOURCE_ROOT=/Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-admission-packet-20260912T170000Z
test "$(stat -f '%Lp' "$SOURCE_ROOT/current-overlay-merge-packet.json")" = 600
test "$(stat -f '%Lp' "$SOURCE_ROOT/current-operational-hold-dispositions.json")" = 600
test "$(shasum -a 256 "$SOURCE_ROOT/current-overlay-merge-packet.json" | awk '{print $1}')" = ce9d4ea1e048a70b7a8a5b85fab33fd1a0568eb5cb1356229187144ab8bc7558
test "$(shasum -a 256 "$SOURCE_ROOT/current-operational-hold-dispositions.json" | awk '{print $1}')" = c13cb0b565d2b86d34365f12d565f37f0e7ba6ec6bfa0d65de7f4a81ee088324
ENVIRONMENT=test PYTHONPATH=backend python -c 'from pathlib import Path; from app.operational_migration.hcp_current_overlay import CurrentOverlayManifest; p=Path("/Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-admission-packet-20260912T170000Z/current-overlay-merge-packet.json"); m=CurrentOverlayManifest.load(p); assert m.digest == "e23b7bcf5ac34ea650184afacc711af0c7028e83a6b1f7405e2ae17e13441eb2"'
```

Stage exact bytes into the Enterprise-controlled execution host only after
setting an explicit protected destination and executor identity:

```bash
SOURCE_ROOT=/Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-admission-packet-20260912T170000Z
test -n "$ARTIFACT_DEST" && test -n "$EXECUTOR_USER" && test -n "$EXECUTOR_GROUP"
install -d -m 0700 -o "$EXECUTOR_USER" -g "$EXECUTOR_GROUP" "$ARTIFACT_DEST"
install -m 0600 -o "$EXECUTOR_USER" -g "$EXECUTOR_GROUP" "$SOURCE_ROOT/current-overlay-merge-packet.json" "$ARTIFACT_DEST/current-overlay-merge-packet.json"
install -m 0600 -o "$EXECUTOR_USER" -g "$EXECUTOR_GROUP" "$SOURCE_ROOT/current-operational-hold-dispositions.json" "$ARTIFACT_DEST/current-operational-hold-dispositions.json"
test "$(sha256sum "$ARTIFACT_DEST/current-overlay-merge-packet.json" | awk '{print $1}')" = ce9d4ea1e048a70b7a8a5b85fab33fd1a0568eb5cb1356229187144ab8bc7558
test "$(sha256sum "$ARTIFACT_DEST/current-operational-hold-dispositions.json" | awk '{print $1}')" = c13cb0b565d2b86d34365f12d565f37f0e7ba6ec6bfa0d65de7f4a81ee088324
```

For a containerized executor, bind the protected directory read-only, for
example:

```text
--mount type=bind,src=$ARTIFACT_DEST,dst=/run/acp/hcp-source4,readonly
```

The guarded authority file must then use:

```text
overlay_path=/run/acp/hcp-source4/current-overlay-merge-packet.json
overlay_file_digest=ce9d4ea1e048a70b7a8a5b85fab33fd1a0568eb5cb1356229187144ab8bc7558
overlay_manifest_digest=e23b7bcf5ac34ea650184afacc711af0c7028e83a6b1f7405e2ae17e13441eb2
hold_path=/run/acp/hcp-source4/current-operational-hold-dispositions.json
hold_digest=c13cb0b565d2b86d34365f12d565f37f0e7ba6ec6bfa0d65de7f4a81ee088324
expected_base_source4_digest=4a4a9582d7fde37dba73ba9e93db5669d9341768c7f5741f6e8916971fd9ec60
```

The authority file itself remains mode `0600`. Enterprise must preserve its
existing backup, restore-receipt, deployed-authority, classification, schema,
permission, concurrency, and idempotency guards. Artifact recovery supplies no
execution authorization and does not weaken any guard.
