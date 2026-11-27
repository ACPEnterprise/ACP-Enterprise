# P0 authoritative HCP recovery handoff

This assessment verified the existing read-only All County HCP handoff and its
record-level reconciliation artifacts. It did not call HCP, mutate the isolated
clone, or admit records into a protected database. The machine-readable result
is `docs/quality/om2a-p0-authoritative-hcp-recovery-20261127.json`.

## Population finding

The stated 5,524 historical customers and 635 restored customers are not proven
to be comparable sets. The strongest inspected source artifacts contain 5,464
unique numeric customer IDs in the owner-recovered export, 5,253 opaque IDs in
sealed SOURCE.4, and 5,381 opaque IDs in the later GET-only snapshot. No sealed
artifact inspected proves 5,524 provider customer identities. The 635 count has
no authorized record-level protected snapshot in this custody packet, so the
exact missing set cannot yet be computed without fabricating identity matches.

The protected packet already holds record-level SOURCE.4 crosswalks for 5,253
customers, 5,801 jobs, and 1,307 estimates. Customer control coverage is zero;
job control coverage is 4,816 of 5,801; estimate control coverage is 1,306 of
1,307. These are evidence artifacts, not admission authority. A later complete
graph overlay classifies 522 delta records, with 339 still held.

## Laptop Master protected execution

Laptop Master should first create a new mode-0600 runtime snapshot containing
domain, provider source ID, native target ID, parent provider IDs, source digest,
admission disposition, and merge successor. Do not include names, addresses,
notes, or media bodies in the coordination receipt. Run the existing
`backend/scripts/reconcile_hcp_historical_population.py` against sealed source
and runtime snapshots, writing to a new path; the command refuses overwrite and
does not mutate either source.

Before any admission decision, verify the recorded crosswalk and overlay SHA-256
values against the machine-readable assessment, retain the clone dump digest as
the rollback anchor, and require zero unresolved duplicate native targets,
orphaned parent relationships, and identity changes for every admitted record.
Held records remain held unless Laptop Master supplies explicit authority.

## Attachment custody

Prior integration evidence declares 621 attachment references totaling
3,088,372,246 bytes, but the three recorded November packet paths are absent on
this machine and the present protected handoff contains no attachment bodies.
The provider attachment endpoint was HTTP 404; that is unavailable, not proof of
zero attachments. Laptop Master must restore or reseal the original manifest and
body bundle in approved custody, or approve a provider-supported GET-only route.
Never derive media URLs from filenames or provider identifiers.

Use `backend/scripts/hcp_open_work_attachment_custody.py` only after the sealed
reference inventory and approved HTTPS retrieval references are present. Its
output must remain in protected custody. A complete result requires one terminal
status per reference, content digest verification for every recovered body, and
preservation of customer, job, timestamp, filename, and provenance relationships.

## Stop conditions

Stop before protected admission if the 635-record snapshot is absent, identity
namespaces cannot be bridged deterministically, any parent is unresolved, media
references lack approved retrieval authority, or rollback inputs fail digest
verification. Aggregate counts alone do not clear any stop condition.
