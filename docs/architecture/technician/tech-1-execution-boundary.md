# TECH.1 controlled execution boundary

`TECH.1 — Establish technician application shell` is a migration-free,
frontend-only Field Service milestone. The scheduler manifest owns its versioned,
fingerprinted execution boundary. Scheduler reconciliation copies that contract
into the durable milestone evidence; the owner Start path validates the identity
and fingerprint before composing an Engineering Command.

The approved implementation surface is the technician feature, route, API, hook,
and type modules, the exact shared router/navigation integration files, and this
technician architecture documentation. Backend code, Alembic migrations,
deployment and infrastructure files, credentials, environments, and unrelated
product modules are outside the boundary.

The bounded execution may inspect, modify, validate, commit, perform safe
mechanical reconciliation, and push normally. It may not deploy Preview or
Production, import or cut over data, force-push, resolve semantic conflicts, or
perform irreversible operations. Its provider validation contract is `git diff
--check`, ESLint, and TypeScript production validation. Device-oriented and
focused frontend tests remain required completion evidence in the milestone
instruction even though they are not provider command primitives.

Changing this scope requires a new boundary version and fingerprint in the
authoritative scheduler manifest. A Ready code-changing scheduler milestone
without a valid boundary remains fail-closed.
