# Testing Strategy

Testing provides evidence that ACP Enterprise preserves operational workflows, tenant boundaries, financial correctness, and deployment safety. The goal is confidence at the lowest practical test level, with end-to-end coverage reserved for critical journeys.

## Test layers

### Unit tests

Unit tests cover deterministic domain behavior without network, filesystem, clock, or database dependencies.

Required targets include:

- State transitions and business rules
- Price, tax, discount, totals, and timezone calculations
- Permission and policy decisions
- Event payload construction
- Validation and mapping logic
- Frontend formatting, reducers, and complex hooks where behavior is isolated

Use explicit clocks and deterministic identifiers. Test externally visible behavior, boundaries, and edge cases rather than private implementation steps.

### Integration tests

Integration tests exercise real boundaries, especially PostgreSQL, Redis or queue infrastructure, file storage, and external-provider adapters.

- Run database tests against the supported PostgreSQL major version, not SQLite.
- Apply Alembic migrations to an empty database and test upgrading from the production revision.
- Verify constraints, transactions, rollback, locking, idempotency, outbox publication, and tenant scoping.
- Replace third-party networks with contract-faithful fakes for ordinary CI; maintain a smaller sandbox suite for provider compatibility.
- Isolate test data and make tests safe for parallel execution.

### API tests

API tests verify the published HTTP contract through the ASGI application:

- Success responses and status codes
- Request and response validation
- Standard error envelopes
- Authentication and role/resource authorization
- Cross-company and cross-branch isolation
- Pagination, filtering, sorting, and stable ordering
- Idempotency and concurrency conflicts
- Event emission and transactional consistency

OpenAPI generation and compatibility checks run in CI when contracts change.

### Frontend tests

- Use component tests for user-visible states and interactions, not component internals.
- Cover loading, empty, error, stale, unauthorized, validation, and success behavior.
- Test keyboard navigation and automated accessibility rules for shared components and critical screens.
- Use mocked HTTP at the network boundary with responses that conform to the API schema.
- Add visual regression coverage selectively for high-value layouts such as dispatch, technician workflow, estimates, and invoices.
- Type checking, linting, and production builds are mandatory CI checks.

### End-to-end tests

End-to-end tests run against a production-like stack and cover a small set of business-critical journeys:

1. Create or identify a customer and service location.
2. Book, reschedule, assign, and dispatch an appointment.
3. Execute technician arrival, estimate approval, work, and completion.
4. Generate an invoice, collect or record payment, and reconcile the result.
5. Confirm customer communications and operational analytics reflect the workflow.
6. Verify users cannot access another tenant or unauthorized branch.

Tests should validate business outcomes and durable state, not merely page navigation. The launch suite must include rollback-sensitive and failure-recovery paths.

## Coverage expectations

Coverage is a signal, not the Definition of Done.

- New or changed backend and frontend code should maintain at least 80% line coverage and 75% branch coverage within the changed scope.
- Security policy, tenant isolation, money calculations, workflow transitions, payment idempotency, and event/outbox behavior require complete meaningful branch coverage regardless of aggregate percentages.
- Generated code, declarations, and trivial framework wiring may be excluded transparently.
- Coverage reductions require an explicit explanation and reviewer approval.
- A passing percentage never compensates for missing critical-path assertions.

## CI and release gates

Every pull request runs:

- Formatting and linting
- Python and TypeScript type checks
- Unit, integration, API, and frontend tests affected by the change
- Migration upgrade validation
- OpenAPI generation/compatibility validation
- Frontend production build
- Dependency and secret scanning

The main branch additionally runs the full suite and produces immutable build artifacts. Production candidates run end-to-end, migration, smoke, security, backup/restore, and performance checks appropriate to the release.

Flaky tests are defects. Quarantine requires an owner, tracking issue, documented risk, and near-term removal date; critical-path tests may not be silently quarantined.

## Test ownership and data

- The team changing behavior owns corresponding test changes.
- Test fixtures use synthetic data and builders that express business intent.
- Production customer data must not be copied into developer or CI environments without an approved, verified anonymization process.
- Defects receive a regression test at the lowest level that proves the failure and prevents recurrence.
