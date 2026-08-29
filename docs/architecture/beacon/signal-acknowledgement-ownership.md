# Beacon signal acknowledgement and ownership

`BANK.BEA.005` extends the canonical immutable Beacon review-event stream with
an independent human workflow projection. Acknowledgement records that an
authorized User saw the admitted evidence. Ownership records which explicit
canonical Enterprise User is responsible for follow-up. Neither state changes
the operational condition, its severity, its priority, or evaluator-driven
resolution.

Every new workflow event binds Company, optional Branch, signal and condition
identity, catalog definition/version, evidence digest, actor User, request ID,
workflow version, acknowledgement snapshot, previous owner, resulting owner,
and timestamps. Current state is derived from the highest immutable workflow
version; history is never overwritten.

Commands are serialized by a PostgreSQL transaction advisory lock scoped to
Company and condition. Optimistic `expected_version` prevents stale ownership
changes, while unique request identities make safe replay deterministic. The
permissions are intentionally separate: `COMPANY_BEACON_REVIEW` acknowledges,
`COMPANY_BEACON_OWN` self-claims or releases the caller's ownership, and
`COMPANY_BEACON_ASSIGN` assigns, transfers, or administratively releases.

Read-only projections expose current state, immutable history, and explicit
`all`, `unowned`, `mine`, and `acknowledged` operational views. These filters do
not alter the BANK.BEA.004 comparator or digest. Snooze and suppression remain
separate lifecycle presentation facts. If evidence clears or expires, workflow
history remains durable; reappearance receives ownership only when the
deterministic condition/signal identity actually continues.

Each mutation stages a Company/Branch-scoped Business Event and audit record in
the same transaction. No event claims source-domain resolution, and no command
mutates Jobs, Scheduling, Dispatch, Customers, invoices, or other source facts.
