# Factory Control authority boundary

Factory Control is a Twelve Hats platform control plane. Its roadmap, worker-lane,
release, deployment, gate, and acceptance evidence is platform-global. A Company
identifier may be attached only as provenance for tenant-related work; it does not
make the telemetry tenant-owned or tenant-authorized.

## Human read authority

`PLATFORM_FACTORY_CONTROL_READ` is granted only by an explicit, audited
`platform_authority_assignments` row for an active authenticated user with
`PLATFORM_OWNER` or `PLATFORM_ADMIN` authority. Tenant roles and Company
membership do not confer this permission. Revocation advances the user's
authorization version so previously issued bearer tokens become stale.

No platform authority assignment is seeded or inferred by the migration. The
initial grant requires a separately governed platform-custody bootstrap after the
Twelve Hats / The 10:31 Project authority boundary is approved.

## Controller write authority

The existing Development Factory authenticates workers inside a Company scope.
That tenant-scoped identity is only an authentication starting point. Factory
Control ingestion or snapshots additionally require:

1. an active authenticated Development Factory worker session and credential;
2. an active `WorkerIdentity` bound to that exact orchestration worker; and
3. an explicit global `FACTORY_CONTROLLER` assignment for the exact worker
   identity and exact `INGEST` or `SNAPSHOT` permission.

There is no automatic grant for an All County worker, Company administrator, or
any other tenant identity. The explicit global assignment is the temporary
authority bridge while Development Factory authentication remains Company-scoped.
A permanent platform-owned controller identity remains part of the approved
platform-boundary successor, not an inferred tenant privilege.

## Evidence and queue rules

Events and snapshots are immutable, digest-bound, replay-safe evidence. The same
idempotency key with different facts fails closed. Owner actions are surfaced only
after engineering prerequisites are recorded as resolved and include the exact
action, reason, workflow, expected minutes, and engineering resume action.

Factory Control is telemetry only. It does not dispatch work, deploy releases,
mutate tenant business records, expose payroll values, or grant authority.
