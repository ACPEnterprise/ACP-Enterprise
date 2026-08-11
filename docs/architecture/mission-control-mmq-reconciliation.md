# Mission Control / MMQ Scheduler Reconciliation

PHONE-WEEKEND.2 introduces a durable, versioned scheduler contract without
parsing free-form Markdown at runtime.

The repository-owned JSON manifest is validated at load time and fingerprinted
from canonical JSON. Durable scheduler snapshots retain every accepted version.
Milestones adopt stable codes and carry readiness, capacity, integration,
migration, shared-contract, dependency, and reconciliation evidence.

Permanent capacity identities (`OM1`, `OM2`, `MIG`, `ECO`, and `LAP`) are
durable records. Their bindings refer to configured worker capacity and are
audited separately, so worker rotation never changes scheduler ownership.

## Reconciliation modes

`DRY RUN` inventories roadmaps, milestones, commands, runtimes, reservations,
allocations, events, and worker mappings. It emits exact record identifiers and
proposed non-destructive transitions but rolls back and performs zero writes.

`APPLY` is separately gated by Checkpoint 2 authority. It refuses destructive
operations, ambiguous records, or any plan that cannot preserve CRM.2.
Reconciliation retains legacy records and records scheduler events rather than
deleting history.

An explicitly reviewed duplicate identity is represented by a manifest-owned
`superseded_legacy_titles` mapping. The canonical record alone receives the
stable milestone code. The historical record keeps its original roadmap,
title, lifecycle, and command history, while reconciliation marks only its
identity state `superseded` and appends a scheduler audit event. Active or
review-pending command history still fails closed; title ordering is never used
to select a canonical record.

The representative report in
[phone-weekend-2-dry-run.json](examples/phone-weekend-2-dry-run.json) uses
synthetic identifiers and is not a Preview database report.

## Phone semantics

Mission Control distinguishes active commands, executing milestones, capacity
waits, owner review, readiness, planning, blocking, completion, and
reconciliation requirements. A stale runtime becomes reconciliation-required
and does not contribute to the genuine Running count. A milestone exposes Start
only when both its durable scheduler readiness and reconciliation state are
current.

## Checkpoint boundary

Checkpoint 1 supplies code, schema, tests, and dry-run evidence only. Preview
migration, Preview APPLY, worker binding, and physical-phone validation require
separate owner approval.

The reconciled scheduler evidence records OPS.1 complete at
`c89396546a6ba6012e48694ba7737bd30e316637` and COMMS.1 complete at
`06ba0f39b85b0eeda7e5a4d1747bb326bd28668a`. Neither milestone introduced an
Alembic migration, so PHONE-WEEKEND.2 retains `t5j7f9b1c386` as its migration
parent.

## Serialized migration integration

PHONE-WEEKEND.2 revision `u6k8g0c2d497` integrates first. Isolated
INV.3-LEGACY revision `u6k8f0h2j497` currently shares parent `t5j7f9b1c386` and
must integrate second after re-parenting onto `u6k8g0c2d497`. It must repeat
upgrade, downgrade, drift, single-head, and affected regression validation;
sibling heads are prohibited.

## Checkpoint 3C current-state contract

Scheduler version `MMQ.5-2026-08-11.5` records the authoritative Enterprise
head used for owner Start. It incorporates completed EST.4, DISP.2, the distinct
INV.3-LEGACY inventory lineage, and PHONE-WEEKEND.2 Checkpoint 2, plus current
Migration and Economics evidence. MIG.2, BE.9, and residual INV.2A remain
blocked by their recorded gates.

External evidence is retained under stable scheduler codes: `MIG.1`,
`MIG.PREP.2`, `BE.8`, `BE.PLAN.1`, `BE.REVIEW.1`, `BE.EVIDENCE.1`, and
`BE.GAP.1`. Preparation never promotes `MIG.2`, and Economics gap planning
never promotes `BE.9`.

TECH.1 is the sole Ready milestone: OPS.1, DISP.2, and PLAT.1 are complete; its
Version 1 shell boundary requires no migration, Production operation, import,
or cutover. Ready permits only the authenticated owner Start action and never
dispatches automatically.
