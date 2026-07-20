# Definition of Done

A feature is done only when it is usable, secure, observable, supportable, and documented across every layer included in its approved scope. “Code complete” is not done.

## Required completion criteria

### Behavior and scope

- Acceptance criteria and out-of-scope behavior are explicit and satisfied.
- Product and design behavior is approved for the affected workflow.
- Empty, error, permission, concurrency, retry, and recovery paths are defined.
- Existing workflows remain compatible or have an approved migration and rollout plan.

### Database complete

- The owning module, tables, columns, constraints, relationships, tenant scope, audit fields, retention behavior, and concurrency strategy are correct.
- Query plans and indexes are appropriate for expected volume.
- No module bypasses another module's data ownership.

### Migration complete

- Alembic upgrade is reviewed and tested from both an empty database and the current production revision.
- Data backfill, lock duration, backward compatibility, deployment order, recovery, and rollback or forward-fix behavior are documented.
- Production execution ownership and verification queries are defined.

### API complete

- Versioned request, response, error, pagination, and idempotency contracts follow API standards.
- Validation, authentication, authorization, tenant isolation, and audit behavior are enforced server-side.
- OpenAPI and client contracts are updated.

### UI complete

- The workflow is connected to real APIs with no production hard-coded business data.
- Loading, empty, error, stale, unauthorized, validation, success, and retry states are implemented.
- Responsive behavior, keyboard use, focus handling, semantics, and accessibility checks meet the supported standard.
- Product analytics or operational telemetry is present where required.

### Business events emitted

- Every meaningful completed action emits the documented, versioned business event through the transactional outbox.
- Tenant, entity, actor, time, correlation, causation, and idempotency metadata are correct.
- Consumers are idempotent, tested, observable, and have retry/dead-letter behavior where applicable.
- No event is emitted for state that failed to commit.

### Tests passing

- Unit, integration, API, frontend, and end-to-end tests exist in proportion to risk.
- Critical tenant, permission, financial, workflow, and failure branches are covered.
- Formatting, linting, type checking, builds, migration tests, security scans, and the full required CI suite pass.
- No unexplained flaky or skipped test remains.

### Documentation updated

- Module specifications, API/event contracts, operational procedures, configuration, and user-facing guidance reflect the delivered behavior.
- Significant architectural decisions are recorded in ADRs.
- Release notes identify migrations, flags, operator actions, known limits, and compatibility effects.

### Operational readiness

- Structured logging, metrics, traces, dashboards, and alerts cover the new critical paths.
- Performance and capacity have been validated against defined expectations.
- Secrets, privacy, threat, backup, restore, and support implications have been reviewed.
- Feature flag, rollout, rollback, and data-recovery procedures are tested where risk warrants them.

### Code reviewed and accepted

- At least one qualified engineer has reviewed the code and tests; domain, security, database, or infrastructure specialists review high-risk changes.
- Review comments are resolved, not merely acknowledged.
- Product acceptance is recorded for user-visible behavior.
- The change is deployed to the target environment and smoke-tested before its work item is closed.

## Exceptions

An unmet criterion requires an explicit exception with rationale, risk, compensating control, owner, tracking issue, and due date. Security, tenant isolation, financial integrity, migration safety, and recoverability cannot be waived solely to meet a schedule.
