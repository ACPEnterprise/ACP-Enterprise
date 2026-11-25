# Manual Engineering Activation Directives

Status: `MANUAL_COORDINATED — NOT A WORKER CONTROL LEASE`

These directives provide immediate bounded engineering while Worker Control
authentication, credential recovery, and lease issuance are repaired. They are
bound to the authoritative queue in
`development-factory/continuous-engineering-queue.v1.json`. The queue marks the
listed assignments as manually reserved and blocks the automated claim-envelope
path.

## OM1 — Development Factory recovery

Assignment: `OM1-DF-DURABLE-COORDINATION-01`

Work only in OM1's verified isolated worktree. Preserve the existing checkout,
branches, and worktrees. Inspect and extend the existing Development Factory;
do not create a competing orchestration framework.

Work sequence:

1. Verify the queue SHA, machine inventory, clean worktree, and assignment
   reservation.
2. Qualify atomic claim/race behavior, stale-lease fencing, checkpoint
   integrity, crash/restart recovery, network interruption handling, bounded
   retries, resource limits, and secret redaction.
3. Reconcile CI/CD, immutable release manifests, artifact-derived
   configuration, migration-graph, protected-qualification, and recovery
   contracts.
4. Add regression tests for every demonstrated defect.
5. Publish a task branch and machine-generated evidence handoff for Laptop
   Master and independent review.

Stop for security, migration, release-authority, protected configuration,
deployment, or live-data boundaries. No automatic merge, deployment, or
approval is permitted.

## OM2 — Historical data reconciliation

Assignments:

- `OM2-HCP-HISTORY-RECON-01`
- `OM2-QBO-HISTORY-RECON-01`

Work only in OM2's verified isolated worktree and only with custody roots that
the authorized operator confirms are mounted. If custody is unavailable, use
synthetic fixtures and document the external evidence gate; do not copy source
data into ordinary logs or transfer it outside approved custody.

Work sequence:

1. Verify queue digest, machine inventory, clean worktree, and both assignment
   reservations.
2. HCP: reconcile customer/location/job/appointment/invoice/payment lineage,
   preserve provider identities, and produce deterministic held-exception and
   replay evidence.
3. QBO: reconcile sealed accounts and transaction/report relationships,
   preserve source IDs and known exceptions, and qualify read-only projections.
4. Add regression tests for namespace mismatches, duplicate prevention,
   missing-parent handling, and source-provenance loss.
5. Publish separate task branches and evidence handoffs for Laptop Master and
   independent review.

No HCP writes, QuickBooks writes, OAuth, financial posting, payroll, banking,
or live admission is authorized by these directives.

## OM1 — Follow-on overnight reservations

Assignments:

- `OM1-DF-RELEASE-MANIFEST-02`
- `OM1-DF-MIGRATION-GRAPH-AUDIT-02`
- `OM1-DF-SUPERVISOR-RECOVERY-02`

These are independent manual reservations after the completed durable-
coordination checkpoint. Work only in the reserved isolated worktree and only
within the queue's allowed paths. Bind every checkpoint to the exact queue
digest, assignment ID, source SHA, changed-file list, and machine-generated
validation output. Reconcile application/tooling/migration/backup/rollback
identities, exercise failure and restart recovery, and preserve one Alembic
head. Do not rewrite applied migrations, access protected signing keys, issue
approval, merge, deploy, or mutate live data. Automated claims remain blocked.

## OM2 — Follow-on overnight reservations

Assignments:

- `OM2-HCP-JOB-RELATIONSHIP-02`
- `OM2-COMMUNICATIONS-HISTORY-RECON-01`
- `OM2-QBO-REPORT-READBACK-02`
- `OM2-CUSTOMER-HISTORY-UI-RECON-02`

These reservations may proceed independently using synthetic or sealed custody
evidence only. HCP work must preserve source IDs, parent/location relationships,
and held ambiguity; communications work is readback-only; QBO work is
readback-only and preserves all accounting exceptions; customer-history UI work
must remain independent of native customer admission and must not fabricate
historical records. Browser acceptance packets must identify synthetic,
protected, and live evidence separately. No OAuth, provider write, financial
posting, payroll, banking, live admission, or cross-tenant read is authorized.
Automated claims remain blocked.

## OM2 — Replenished historical-accessibility reservations

Assignments:

- `OM2-HISTORY-DETAIL-READBACK-03`
- `OM2-IMPORT-MAPPING-02`
- `OM2-RECONCILIATION-EXCEPTIONS-02`
- `OM2-QBO-HISTORY-NAVIGATION-03`
- `OM2-COMMUNICATIONS-TIMELINE-02`
- `OM2-BROWSER-HISTORY-ACCEPT-03`

These reservations are manually coordinated and bound to the queue file. They
may use only synthetic or sealed custody evidence. Historical detail must retain
source identifiers, provenance, unresolved relationships, and unavailable-state
explanations. CSV/XLSX mapping must be replay-safe and cannot admit records by
itself. QBO work is source-backed read-only; no OAuth, posting, banking, payroll,
or financial execution is authorized. Browser acceptance must explicitly label
synthetic, protected, and live evidence. Automated claims remain blocked.

## Laptop continuation

Laptop Master continues its reserved All County workflow assignments and may
integrate only independently reviewed OM1/OM2 branches. Worker Control
activation recovery proceeds separately and does not block safe isolated work.
