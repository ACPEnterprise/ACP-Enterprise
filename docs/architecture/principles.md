# Engineering Principles

These principles guide design and review. When principles conflict, protect data integrity, security, and operational continuity first; record material tradeoffs in an ADR.

## Single Source of Truth

Each business fact has one authoritative owner. Customer identity belongs to CRM; appointment state belongs to Operations; invoice state belongs to Financial. Other modules consume identifiers, APIs, or events rather than maintain competing copies.

- Enforce business invariants in the owning backend module.
- Treat derived views, caches, search indexes, and analytics projections as rebuildable.
- Make ownership explicit for every table, API, event, and calculation.
- Resolve conflicting data by correcting the source, not by adding reconciliation logic to every consumer.

## Event-Driven Architecture

Meaningful completed business actions emit durable, past-tense events such as `appointment.booked` and `payment.received`.

- Commit state changes and their outbox events atomically.
- Use events for history, projections, integrations, notifications, and automation.
- Do not use events to avoid clear synchronous validation or transactional consistency within a module.
- Version event schemas and make consumers idempotent.
- Events are facts; corrections are new events, not silent history rewrites.

See [ADR 0002](adr/0002-event-driven-architecture.md).

## API First

All product capabilities are exposed through explicit, versioned backend contracts. The web application is a client of those contracts, not a privileged path around them.

- Define validation, authorization, errors, and idempotency before UI coupling develops.
- Keep transport schemas separate from persistence models.
- Preserve backward compatibility within a published API version.
- Make contracts discoverable through OpenAPI and durable documentation.

## Modular Design

ACP Enterprise is a modular monolith until operational evidence justifies independent services.

- Organize by business capability, with clear ownership and public interfaces.
- Prevent cross-module table writes and circular dependencies.
- Share small technical infrastructure, not business logic disguised as utilities.
- Extract a service only when scaling, deployment, reliability, security, or team ownership requires it.

## Security by Default

Access is denied unless explicitly authorized. Tenant, branch, and role scope are part of every protected operation.

- Never trust tenant, actor, price, or permission claims supplied by a client.
- Apply least privilege to users, services, database roles, and credentials.
- Protect sensitive data in transit, at rest, in logs, exports, and backups.
- Audit security-sensitive and financially significant actions.
- Include threat analysis in the design of exposed or high-impact workflows.

## Performance by Design

Performance is a product requirement for office and field workflows, not a late optimization exercise.

- Define expected data volume and latency for important paths.
- Avoid unbounded reads, N+1 queries, and in-memory aggregation of large datasets.
- Use indexes, pagination, projections, caching, and asynchronous work intentionally.
- Measure before optimizing and protect critical paths with performance tests and telemetry.

## AI Ready

AI capabilities depend on reliable data, explicit semantics, and controlled actions.

- Capture structured domain data and well-defined events before adding models.
- Preserve provenance, timestamps, actor identity, and explainable decision context.
- Expose AI through permissioned tools and APIs with validation, auditability, and human approval for consequential actions.
- Evaluate models against business outcomes and safety criteria; never allow probabilistic output to bypass domain rules.

## Documentation First

Significant work begins with enough written context to align product, design, and engineering.

- Define workflow, rules, ownership, data, events, failure behavior, and acceptance criteria before implementation.
- Record consequential decisions in ADRs.
- Update permanent documentation in the same change as the system.
- Prefer concise authoritative documents over duplicated knowledge and informal memory.
