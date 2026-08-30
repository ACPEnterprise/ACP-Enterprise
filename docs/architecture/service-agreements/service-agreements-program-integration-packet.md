# Service Agreements program integration packet

## Qualified lineage

The provider-neutral Service Agreements program is carried by
`work/service-agreements-program-1`. Its coherent checkpoints are:

- `a439ee9`: plan, enrollment, coverage, entitlement, API, permission, and operator-workspace foundation;
- `9d925e9`: lifecycle evidence, scheduling/job linkage contracts, entitlement consumption/correction, and billing readiness;
- `393d6dd`: renewal successor authority and durable plan-command replay;
- `23e64a6`: compatible operational receivables controls composed from the independently qualified Revenue Collection lineage;
- `1f5dc98`: removal of command idempotency identities from plan API responses.

Migrations are linear at `g5e4c93b0f6d` → `h6f5d04c1a7e` →
`i7g6e15d2b8f` → `j8h7f26e3c9a`.

## Acceptance boundary

The branch provides versioned immutable plan authority; explicit Customer and
Service Location enrollment; deterministic recurring entitlements; governed
activation, renewal, cancellation, and expiration; native Scheduling/Job
handoff identities without duplicating those authorities; exact entitlement
consumption/correction evidence; non-posting Invoice/Payment readiness; safe
reporting; and permission-gated responsive Enterprise UI.

Production plan values remain deliberately unconfigured. The implementation
does not enroll a real Customer, schedule a real visit, issue an Invoice, move
money, send a communication, post Accounting, or calculate Economics.

## Qualification evidence

- 311 affected backend tests passed across Service Agreements, Customers,
  Scheduling, Jobs, Invoicing, Payments, and the platform mutation registry.
- 94 frontend files / 285 tests passed; ESLint and the TypeScript/Vite
  production build passed.
- Ruff, MyPy, Python compilation, and `git diff --check` passed.
- PostgreSQL upgraded to the single head `j8h7f26e3c9a`; `alembic check`
  reported zero operations; downgrade to `i7g6e15d2b8f` and re-upgrade passed.

## Protected integration and Preview

Enterprise may integrate the branch through the normal protected workflow.
Preview should use synthetic Company, Branch, Customer, Location, plan, and
entitlement fixtures to exercise plan activation, enrollment, service-due
generation, Scheduling/Job linkage, consumption/correction, billing readiness,
renewal, cancellation, and read-only/management/admin permission boundaries.
No owner browser action or Production operation is required for integration.
