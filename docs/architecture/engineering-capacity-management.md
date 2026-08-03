# Engineering Capacity Management

Engineering Capacity is a Company-scoped Development Factory domain. It owns capacity policy, machine inventory, worker limits, reservations, allocations, queue decisions, reconciliation, and append-only capacity history. Engineering Control continues to own owner intent and approval; Worker Control owns worker authentication and leases; Engineering Execution owns execution; repository and provider layers retain all mutation authority.

Capacity is explicit persisted truth. A heartbeat may update the health observation of an already configured worker, but it does not enroll a machine or create capacity. Missing or contradictory policy fails closed. Ambiguous assignments retain their slots in `reconciliation_required` until an authorized resolution is recorded.

The safe default is one assignment per configured worker and one Company-wide concurrent workstream. Released capacity is never execution authority: even when policy permits queued work to receive released capacity, existing owner Start and dispatch rules remain authoritative. This milestone records that policy option but introduces no scheduler or automatic execution.

## Initial office inventory

The capacity API can record owner-controlled inventory without authenticating or trusting it:

- Original Office Machine — available August 3, 2026
- Office Machine 2 — available August 3, 2026
- Laptop 1 — expected August 4, 2026
- Office Machine 3 — expected August 4, 2026

Create these through `POST /api/v1/engineering/capacity/machines`. Each record remains `unenrolled` with no `worker_id` until it is deliberately associated with a separately enrolled Engineering Worker through the capacity-management API. Labels are not credentials and never grant execution authority.
