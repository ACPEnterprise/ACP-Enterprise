# CUTOVER.2 deterministic planning and rehearsal

CUTOVER.2 compiles immutable CUTOVER.1 readiness evidence into a provider-neutral,
versioned cutover plan. It does not provide an execution path. Plan and step
identities use UUIDv5 over canonical inputs; evidence digests use SHA-256.

The plan is a single-terminal directed acyclic graph. Every dependency is scoped
to one Company and Branch. Compilation fails for cycles, missing or duplicate
dependencies, unreachable or multiple terminal steps, incompatible readiness
evidence, bypassable owner checkpoints, or inadequate rollback evidence.

Required owner checkpoints are readiness review, exception/disposition review,
pilot-boundary approval, rollback approval, and final cutover authorization.
Technical success never satisfies these checkpoints. CUTOVER.2 creates no owner
approval evidence.

The rehearsal service accepts immutable evidence and simulates dependency and
evidence gates in canonical step order. Its only outcomes are simulated success,
blocked, skipped, or interrupted evidence. It has no provider, operational,
infrastructure, import, synchronization, or deployment port.

Planning and rehearsal persistence is migration-owned and append-only. Composite
foreign keys enforce Company and Branch scope. Deterministic uniqueness supports
concurrent replay, while database triggers reject updates and deletes. The
tables own no Customer, Service Location, Job, Estimate, Invoice, or Payment.

Revision `e0a6c2d8f351` follows isolated workstream head `d9f5b1c7e240`. Its
downgrade removes only CUTOVER.2 evidence tables, triggers, and constraints.
