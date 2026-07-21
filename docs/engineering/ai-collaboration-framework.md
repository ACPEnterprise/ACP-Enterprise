# AI Collaboration Framework

AI assistance in ACP Enterprise operates within human-owned product, architecture,
security, source-control, and deployment decisions. It accelerates inspection,
implementation, validation, and documentation; it does not create independent
authority.

## Roles

### Product Owner

- Defines business outcomes, priorities, acceptance criteria, and exclusions.
- Approves user-visible behavior and authorizes commits, pushes, and deployments.
- Resolves product decisions that materially change scope.

### Chief Architect

- Defines and reviews ownership, domain, security, data, event, integration, and
  operational architecture.
- Resolves consequential technical tradeoffs and approves exceptions.
- Determines whether a decision requires an ADR under the
  [Architecture Decision Process](architecture-decision-process.md).

### Implementation Engineer

- Inspects the current system, proposes a bounded plan, implements the approved
  design, and preserves unrelated work.
- Runs validation, reports exact evidence and limitations, and prepares an honest
  commit boundary.
- Stops when authority, information, or safe execution conditions are missing.

An AI tool may assist the Implementation Engineer role, but it does not approve
its own architecture, infer permission for external side effects, invent
credentials, or claim tests and deployments it did not perform. Human review and
explicit authorization remain required.

## Collaboration cycle

Use the [Engineering Playbook](engineering-playbook.md): inspect and report,
obtain architectural direction, implement within scope, validate, present the
complete diff and risks, then wait for approval before commit or deployment.
Sensitive information stays out of prompts, logs, repositories, and reports.
