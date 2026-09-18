# COSMIC schema and data safety handoff

Evidence timestamp: 2026-09-16 after remote fetch.

## Current protected authority

- SHA: `e69241c399323090ebbd003b4bd3bef73501fc78`
- Revisions: 178
- Root: `218775b8a49c`
- Head: `o1q9s27h4u0v`
- Lineage digest: `9436cd69cd5a6d7603d339013f98af5db6eb69820abbaa819f6396610c391e8e`
- Graph risks: none

The historical branch at `b0ff279c5aeb` is expected and converges through
merge revision `e3c2a71f8d4b`; it is not a current multi-head condition.

## Factory 2.0 refresh — 2026-09-17

- Current protected SHA: `1be3de4456afc7b67ed6bb9f54644468318dd6e4`.
- Protected schema remains 178 revisions, one root, one head
  `o1q9s27h4u0v`, with lineage digest
  `9436cd69cd5a6d7603d339013f98af5db6eb69820abbaa819f6396610c391e8e`.
- OM2E `0fdc0cea502c1ce2bad7b8136efe02f10cb929f3` is structurally linear at
  180 revisions and one head `oa7oa8p9q012`. It adds no destructive upgrade,
  duplicate schema object, modified protected revision, fork, or orphan. This
  does not admit its application mutations; Payroll and membership replay
  governance remain separate blocking Release gates.
- LaptopE `2602bebacf8424ba1e24c93cbf9717c70b8c1f08` retains the protected
  178-revision graph unchanged. Its current voice-foundation work is not a
  launch-critical schema dependency.
- The candidate sweep was executed directly against both fetched cumulative
  refs. It reported no graph risks and did not check either branch out into the
  protected worktree.

## Cumulative lanes

| Lane | SHA / relationship | Migration disposition |
| --- | --- | --- |
| OM2E (`origin/integration/om2-operations`) | `cf3154d5` is integrated by protected merge PR #384 | No reline required. |
| LaptopE (`origin/integration/laptop1-intelligence`) | 32 commits ahead of the prior protected base and two protected commits behind | No Alembic files changed; reconcile application changes onto current protected before composition. |
| Worker runtime multislot | Two commits beyond an old base and 281 commits behind protected | No new worker migration relative to its own base. Do not integrate as a cumulative head; reconcile code onto current protected if still needed. |

No migration was added to any remote commit newer than the protected Batch 12
merge during this sweep. Accordingly, no canonical reline migration is needed.

### Subsequent arrival watch

After protected advanced through PR #384, the following newly arriving heads
were swept: Cosmic Intelligence real-data, Cosmic mobile employee beta, OM2-C
workforce/scheduling/dispatch, Cosmic office/revenue, and Price Book Preview
operability 2. None changes an Alembic file. The first four are based two
protected commits behind and require ordinary code reconciliation; Price Book
operability 2 is based directly on current protected. None requires a schema
reline. OM2E commit `cf3154d5` is already integrated by protected merge
`e69241c3`.

Run `scripts/migration-candidate-sweep` after every fetch. It evaluates candidate
graphs from Git objects without checking branches out, detects modified protected
revision bodies, forks/orphans/duplicates, behind-protected schema candidates,
and flags destructive operations for mandatory human review.

## Price Book relationship finding

The protected schema correctly constrains each `price_book_service_items` row to
its Company-scoped `price_book_categories` row. It does **not** provide a durable
relationship between `jobs.job_type_code` (a nullable free-standing canonical
code string) and either `price_book_categories.id` or a Price Book service item.
The Economics service-line projection consumes `jobs.job_type_code`, while Price
Book uses UUID category identity. Therefore a Job can be valid and a Price Book
category can be valid while the two remain disconnected.

This is a plausible structural explanation for service/category/binding
acceptance gaps, not authority to infer a binding. Release must not add a fuzzy
name/code migration. The domain owner should supply a Company-scoped,
effective-dated, auditable binding contract or certify that `job_type_code`
equals an authoritative category code. Any future migration must preserve
unmapped Jobs explicitly and must not make a new foreign key non-null until the
population is reconciled.

## Customer / Job / Invoice / Payment relationship audit

The authoritative Invoice relationship is Company/Branch/Job scoped and payment
intents bind Company, Branch, Invoice and Customer together. Those primary links
are structurally protected. However, several downstream Payments rows duplicate
scope without a matching composite FK: `payment_receipts.branch_id/customer_id`,
`payment_refunds.branch_id`, and `payment_deposits.branch_id`. Their parent
Company relationship is constrained, but their redundant Branch/Customer values
can diverge from the parent while remaining database-valid. This is an exact
Payments-domain integrity handoff: reconcile existing rows, then add tenant-
scoped parent keys/FKs or remove redundant scope. OM1-B must not invent that
domain migration while the payment execution authority remains inactive.

## Release posture

- Canonical schema path: ready.
- OM2E/LaptopE current cumulative composition: no schema conflict detected.
- Destructive operations in current arriving cumulative candidates: none.
- Current-to-head delta for these lanes: none.
- Fresh PostgreSQL 16.14 zero-to-head was rerun against a disposable local
  database: all 178 revisions reached `o1q9s27h4u0v`, `alembic current` matched
  the sole head, and `alembic check` reported no new upgrade operations. The
  database was destroyed after qualification.
- Current-to-head for OM2E and LaptopE is a schema no-op because neither lane
  changes the protected migration set. A full upgrade rehearsal must run again
  when a schema-bearing candidate arrives.
- Production was not accessed or mutated.
