# ADR 0002: Use an Event-Driven Architecture

- **Status:** Accepted
- **Date:** 2026-07-17
- **Decision owners:** Engineering leadership

## Context

Home-service operations are a sequence of consequential changes: a lead is created, an appointment is booked, a technician is dispatched, an estimate is approved, a job is completed, and a payment is received. Multiple capabilities need to react to those changes for notifications, analytics, automation, integrations, and audit history.

Direct point-to-point calls between every producer and consumer would tightly couple modules, make workflows fragile, and obscure what happened. Database polling and shared-table access would also weaken module ownership. ACP Enterprise needs both transactional correctness for the immediate action and a durable way to communicate completed business facts.

## Decision

ACP Enterprise will use event-driven architecture alongside synchronous APIs within a modular monolith.

- The module that owns a business action validates it and commits its authoritative state synchronously.
- Meaningful completed actions produce durable, past-tense business events.
- State changes and event publication records are committed atomically using a transactional outbox.
- Background consumers deliver notifications, update projections, invoke integrations, and run automation.
- Consumers are idempotent and tolerate duplicate delivery.
- Event schemas are named, versioned, documented, and backward-compatible within a version.
- Events include a unique event ID, event type, schema version, tenant and branch context, entity identity, occurred time, actor/source, correlation ID, causation ID, and validated payload.
- Event records are append-only. Corrections are represented as subsequent facts.

Synchronous calls remain appropriate when a caller requires immediate validation or a result. Events do not replace transactions, module APIs, or explicit workflow orchestration.

## Consequences

### Positive

- Producers remain independent of most downstream consumers.
- A durable business history supports audit, analytics, replay, integration, and future AI features.
- New consumers can be added without modifying the originating workflow.
- Expensive or failure-prone secondary work can occur outside user-facing transactions.
- Correlation and causation metadata improve operational diagnosis.

### Negative and required mitigations

- Some views become eventually consistent; the UI and product rules must define acceptable lag.
- Duplicate, delayed, or out-of-order delivery must be expected and tested.
- Schema evolution requires governance and compatibility testing.
- Outbox processing, retries, dead-letter handling, lag monitoring, and replay tooling add operational complexity.
- Events can expose sensitive data if payloads are not minimized and access-controlled.

## Alternatives considered

### Synchronous module calls for all side effects

Rejected because availability and latency of secondary consumers would affect the originating transaction, and producers would accumulate knowledge of every consumer.

### Shared database tables as the integration mechanism

Rejected because it bypasses module contracts, creates hidden coupling, and makes schema changes unsafe.

### Database polling without explicit events

Rejected because polling cannot reliably express business intent, causation, or exactly what changed and often produces inefficient, ambiguous consumers.

### Full event sourcing for all domain state

Not selected as the default. Reconstructing every aggregate solely from events would add substantial modeling and operational complexity. ACP Enterprise will keep normalized transactional state as the operational source of truth while publishing durable events. A bounded module may adopt event sourcing later through a separate ADR if its benefits justify the cost.
