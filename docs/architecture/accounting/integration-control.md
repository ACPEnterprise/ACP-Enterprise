<!-- markdownlint-disable MD013 -->

# Accounting Parallel Integration and Cutover Control

## Authority and operating rule

This control implements `ACC.INTEGRATION.1` beneath
[ADR 0005](../adr/0005-internal-accounting-system-of-record.md), the
[Day-1 control contract](day-1-control-contract.md), and the
[implementation packets](implementation-packets.md). It coordinates accepted
non-Production work; it does not authorize product implementation, migration
execution, Preview, Production, import, rehearsal, or cutover.

The repository-owned [integration ledger](accounting-integration-ledger.json)
is the durable control record. Unknown evidence is recorded as `UNKNOWN`, never
inferred from a branch name or planned milestone. Repository commits establish
implementation evidence; owner and Finance gates remain separate evidence.

## Lane ownership and collision controls

| Lane | Controlled sequence | Current repository evidence | Collision boundary |
| --- | --- | --- | --- |
| `OM2-A` | `ACC.AR.CONTRACT.1 → INVOICE.1-3.ACCEL → PAY.CONTRACT.1 → PAY.1-3.ACCEL` | Invoice runtime is complete at `43018e2`; PAY contract and packet are frozen by `PAY.CONTRACT.1` | Owns invoice/payment paths and their named event/permission seams only |
| `OM2-B` | `ACC.CORE.CONTRACT.1 → ACC.CORE.1 → ACC.AP.1` | Accounting Core is complete at `ee87e57`; AP remains a later separately started packet | Owns Accounting core first, then AP; may not overlap invoice/payment paths |
| `LAP-B` | `ACC.DATA.1 → ACC.REHEARSAL.1` | DATA worktree exists at `da37cd1`, clean, with no implementation commit | Documentation/sanitized schema only; no real export or runtime until separately authorized |
| `LAP-A` | `ACC.INTEGRATION.1 → ACC.IC.1 → ACC.PREVIEW.1` | This control lane owns serialization and evidence only | Never edits an unfinished lane; integrates only accepted commits |
| `OM1` | PHONE control until operational | Independent critical-infrastructure lane | No Accounting file or worktree access |
| `MIG`, `ECO` | Parked | No Accounting assignment | Reassignment requires separate Start and clean isolated boundary |

Shared event, permission, application-registration, and migration files are
reserved at final integration. A lane may prepare an authorized narrow change
in isolation, but LAP-A integrates one accepted milestone at a time and reruns
all affected validation. A semantic mismatch in posting facts, account/control
ownership, authorization, Company/Branch isolation, money precision, or
idempotency is not mechanical and stops for owner review.

## Alembic serialization protocol

The authoritative single head inspected for `PAY.CONTRACT.1` at
`06ba3007940ff8d716bb5682d7760473a86ef0e6` is `w8m0i2k4n619`. The migration order is:

`ACC.CORE.1 → INVOICE.1-3.ACCEL → PAY.1-3.ACCEL → ACC.AP.1 → ACC.POST.1 → ACC.RPT.1 → ACC.MIG.1`.

For every migration-bearing packet:

1. At implementation Start, fetch origin, require zero behind, run `alembic heads`,
   and record the starting SHA, proposed revision, and expected parent. The
   expected parent is not integration authority.
2. Before integration, fetch again and determine the actual single authoritative
   head. Confirm all earlier slots are integrated or explicitly migration-free.
3. A mechanical re-parent is allowed only when the incoming migration is not
   integrated or pushed, its schema operations and runtime assumptions remain
   valid against the new parent, there is no table/column/constraint/index/data
   overlap, and the complete migration and affected regression suite can be
   rerun. Record old and new parents in the ledger.
4. Stop for a sibling/merge head, overlapping DDL or data transformation,
   incompatible ORM/runtime assumptions, destructive rewrite, already published
   revision, ambiguous ancestry, downgrade loss, or any security/financial
   semantic change. A merge migration needs separate architecture and owner
   authority; force-push and silent re-parenting are prohibited.
5. Validate a fresh upgrade to the candidate head, downgrade the incoming
   revision to its actual parent where the packet permits, re-upgrade, run drift
   detection, affected regressions, and prove exactly one head before commit and
   again before and after push.

If a packet needs no schema change, it consumes no revision, but its accepted
commit still integrates in order when it owns a shared financial contract.

## Dependency watch and successor readiness

| Successor | Becomes dependency-ready only when |
| --- | --- |
| `ACC.CORE.1` | `ACC.CORE.CONTRACT.1` is accepted on authoritative Enterprise; its machine boundary is fingerprinted; a fresh Start SHA and single Alembic head are recorded; owner separately Starts the packet |
| `INVOICE.1-3.ACCEL` | `ACC.AR.CONTRACT.1` is accepted and pushed; accepted Estimate/Job authority is verified; its exact execution boundary, migration slot 2, validation, Finance, and owner gates are frozen; owner separately Starts it |
| `PAY.1-3.ACCEL` | `PAY.CONTRACT.1`, [the payment contract](payment-cash-settlement-contract.md), and [machine packet](pay-1-3-accel.packet.json) are authoritative; Invoice application and Accounting seams exist; owner separately Starts it |
| `ACC.AP.1` | Core contract is accepted; AP execution boundary, vendor/bill authority, migration slot 4, and validation/SOD gates are frozen; preceding integrated migration head is known; owner separately Starts it |
| `ACC.POST.1` | Core, invoice, payment, and AP contracts and producer facts are accepted; posting mappings and failure/idempotency boundaries are frozen; slots 1–4 are integrated or proven migration-free; owner separately Starts it |
| `ACC.RPT.1` | Authoritative postings and AR/AP aging/control seams exist; required statements, accounting basis, period, reconciliation, and projection-freshness contracts are accepted; owner separately Starts it |
| `ACC.MIG.1` | `ACC.DATA.1` is accepted; every target schema and loader boundary is authoritative; sanitized fixtures, disposition/replay, checksum, and reconciliation contracts pass; owner separately Starts implementation (not import) |
| `ACC.IC.1` | All Day-1 runtime packets above are accepted and integrated in order, exactly one head exists, aggregate financial/security regression passes, and no control variance or unresolved integration evidence remains |
| `ACC.PREVIEW.1` | `ACC.IC.1` is owner accepted; backup/restore, release, rollback, sanitized validation, and separate Preview authority are recorded |
| `ACC.REHEARSAL.1` | Accepted `ACC.DATA.1`, `ACC.MIG.1`, `ACC.RPT.1`, and healthy `ACC.PREVIEW.1`; immutable real-export package and separate owner/Finance rehearsal authority exist |

Core and Invoice are integrated in the required order. When `PAY.CONTRACT.1` is
authoritative, `PAY.1-3.ACCEL` is dependency-ready for a separate owner Start.
Processor activation, Preview, Production, real transactions, import, rehearsal,
and cutover remain separately gated.

## Cutover critical-path watch

The launch sequence remains Core → Invoice/AR → Payments → AP → Posting →
Reporting → Opening-state loader → `ACC.IC.1` → Preview → Rehearsal → Finance
acceptance → Production → Cutover. The latest safe gates remain August 18 for
Preview, August 19 for the first real-export rehearsal, and August 20 noon for a
repeatable zero-variance go/no-go package. Missing a gate makes the August 21
target at risk; it never weakens financial controls.

LAP-A records a blocker immediately when an accepted contract or runtime packet
misses its required handoff, a migration cannot integrate linearly, a required
QuickBooks artifact is unavailable, any reconciliation variance is unexplained,
or Preview/Finance/Production authority is absent.

## Housecall Pro minimum-cutover observations

Accounting cutover does not by itself retire Housecall Pro. The minimum
operational chain remains Customer/Job/Scheduling/Dispatch authority followed by
`TECH.1`, field execution, estimates, invoices, and payments. `TECH.1` intersects
Accounting only by enabling the technician workflow that later supplies accepted
work and invoice facts; it is not a dependency of `ACC.CORE.1` and must not delay
core implementation.

Before combined Housecall Pro retirement, the accepted-work-to-invoice seam and
payment handoff must be validated end to end. Optional technician polish,
advanced Inventory costing, Economics, and nonessential parity stay outside the
Accounting critical path. OM1 PHONE control remains independent because it
provides unattended engineering capacity; this milestone does not modify or
reassign it.

## Gates and evidence ownership

Only accepted commits enter the ledger as integration candidates. Each row must
eventually record focused tests, affected regressions, authorization and
Company/Branch isolation, migration lifecycle, secret scan, final commit,
integration commit, remote SHA, and gate disposition. `UNKNOWN` blocks the
relevant transition.

Preview requires separate owner authorization. Rehearsal requires approved
real-export handling and Finance evidence. Production, import, activation,
QuickBooks retirement, rollback, and cutover are separately owner-controlled
operations. The Finance Preparer and Independent Finance Approver must be
different identities at the final financial gate.
