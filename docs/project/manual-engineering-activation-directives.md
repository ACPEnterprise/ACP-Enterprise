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

## Laptop continuation

Laptop Master continues its reserved All County workflow assignments and may
integrate only independently reviewed OM1/OM2 branches. Worker Control
activation recovery proceeds separately and does not block safe isolated work.
