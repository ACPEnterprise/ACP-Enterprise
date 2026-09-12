# ECO policy persistence reconciliation

Date: 2026-09-12

- Protected starting authority: `9096a77705623409da1418022c7949cae08468ce`
- Protected reconciled authority: `d50b47a3de06554ff84ea3db5aed1478f7382415`
- Final protected reconciliation: `d4eee6f6b0bc178d58654f26f3ef2b9429332ab3`
- Composed operations candidate: `37b329490a1a3a69ae59737b6a2754e6a42a9ae2`
- Candidate branch: `work/eco-policy-persistence-reconciliation-1`
- Migration: `e5g7i9k1m3o5` on protected parent `d4f6h8j0l2n4`

## Reconciliation

One append-only `economics_break_even_policy_events` table now persists the
qualified `eco.break-even-policy-contract.v1` and
`eco.owner-policy-operations.v1` lifecycle exactly. It supports Company and
validated Branch scope, all registered policy-family keys, typed value payload,
version/effective interval, actor and approval identity, rationale/provenance,
policy and event digests, predecessor linkage, and event-chain linkage.

The SQL adapter:

- round-trips and re-verifies policy/event digests;
- returns identical-event replay without inserting a duplicate;
- rejects contradictory version/state collision;
- takes a PostgreSQL transaction advisory lock per Company/scope/family before
  insertion;
- retains every lifecycle event for historical reconstruction;
- never resolves DRAFT or AWAITING_APPROVAL into an authoritative snapshot.

An UPDATE/DELETE trigger enforces append-only history in PostgreSQL.

## Legacy compatibility

Existing `economics_company_policy_versions`, parameter, gap, snapshot, reads,
permissions, and audit records remain unchanged. No legacy row is copied or
reinterpreted. The compatibility projection reports each old row as explicit
read-only legacy-compatible or legacy-incompatible evidence pending deliberate
contract admission. The new table is the persistence implementation of the
qualified break-even operations contract, not a second generic Finance-policy
authority.

## Migration behavior

Upgrade creates the bounded table, constraints, resolution index, and immutable
history trigger. Downgrade removes only those new objects. Historical legacy
policy tables are never modified. Removing the new table on downgrade is the
standard explicit rollback boundary and therefore requires normal rollback
custody if it contains post-upgrade events.

## Boundaries

No policy value is selected or migrated. No Production, QBO mutation,
Accounting posting, repricing, Payroll execution, employment action,
recommendation automation, or money movement was performed.
