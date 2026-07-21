# Domain Architecture Brief Standard

A Domain Architecture Brief (DAB) defines a workstream before implementation.
Every major ACP Enterprise workstream begins with a reviewed and approved DAB.
Use direct statements, link to existing standards, and omit sections only when
the brief explains why they do not apply.

## Required structure

### 1. Purpose

State the intended business or engineering outcome and why the work matters.

### 2. Business Problem

Describe the current workflow, constraint, or risk being addressed. Avoid framing
the problem as a predetermined technical solution.

### 3. Scope

List the behavior, data, modules, users, and operational boundaries included.

### 4. Out of Scope

Identify adjacent behavior intentionally excluded to prevent implicit expansion.

### 5. Business Workflow

Describe the end-to-end actor and system sequence, including important failure,
recovery, and approval paths.

### 6. Business Objects

Define the domain objects, important fields, lifecycle states, and invariants.
Distinguish durable records from commands, projections, and transient data.

### 7. Object Ownership

Assign each object and business rule to one module, service, or repository.
Identify transaction boundaries and prohibit cross-module persistence writes.

### 8. Public APIs

Describe new or changed HTTP, service, or other public contracts, including
authorization, validation, idempotency, errors, and compatibility. State `None`
when the work introduces no public API.

### 9. Events Published

List each Business, Security, Audit, or delivery event with its owner, trigger,
transaction relationship, identifiers, and non-sensitive payload purpose.

### 10. Events Consumed

List consumed events, owning producer, handling behavior, idempotency, ordering,
retry, and failure expectations. State `None` when no events are consumed.

### 11. Security Model

Define authentication, permissions, tenant and branch isolation, sensitive-data
handling, auditability, abuse controls, and fail-closed behavior.

### 12. Dependencies

Identify existing modules, platform services, contracts, migrations, design-system
components, and operational prerequisites. Do not invent future tooling.

### 13. Risks

Record material business, security, data, concurrency, compatibility,
performance, and operational risks with their controls or unresolved decisions.

### 14. Acceptance Criteria

Provide observable, testable conditions that prove the workstream outcome,
including negative and isolation behavior where relevant.

### 15. Future Extension Points

Describe only credible seams that the present architecture must preserve. Do not
implement speculative behavior or placeholders.

## Review and maintenance

The DAB must be approved at the architecture-review stage of the
[Engineering Playbook](engineering-playbook.md). Implementation must remain within
its approved scope and satisfy the [Workstream Standard](workstream-standard.md).
If implementation reveals a material ownership, security, data, API, or event
change, update and re-review the DAB before proceeding.
