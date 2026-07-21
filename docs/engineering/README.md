# ACP Engineering System

The ACP Engineering System (ACES) is the operating framework for changing ACP
Enterprise safely and deliberately. It connects business intent, architecture,
implementation, validation, review, approval, commits, and deployment without
turning those activities into unnecessary ceremony.

ACES applies to people and AI-assisted work. It does not replace engineering
judgment, product ownership, security review, or explicit authorization for
operations that change source control or deployed environments.

## Document organization

- [Engineering Constitution](engineering-constitution.md): durable principles
  governing engineering decisions.
- [Engineering Playbook](engineering-playbook.md): the standard delivery flow.
- [Workstream Standard](workstream-standard.md): required structure for a scoped
  milestone or workstream.
- [Domain Architecture Brief Standard](domain-architecture-brief-standard.md):
  required pre-implementation structure for major workstreams.
- [Definition of Done](definition-of-done.md): completion gate before approval.
- [Review Checklist](review-checklist.md): focused technical-review questions.
- [Validation Standard](validation-standard.md): evidence required before review.
- [AI Collaboration Framework](ai-collaboration-framework.md): accountable human
  and AI-assisted collaboration.
- [Architecture Decision Process](architecture-decision-process.md): when and how
  consequential decisions are recorded.
- [Branching and Release](branching-and-release.md): safe source-control and
  release boundaries.

Existing detailed standards remain authoritative within their areas:
[Coding](coding-standards.md), [API](api-standards.md),
[Database](database-standards.md), and [Testing](testing-strategy.md).

## Using ACES

Start work with the [Workstream Standard](workstream-standard.md). Every major
workstream begins with an approved
[Domain Architecture Brief](domain-architecture-brief-standard.md) before
implementation, following the [Engineering Playbook](engineering-playbook.md).
Apply the detailed standards relevant to the change, collect validation evidence,
and use the
[Definition of Done](definition-of-done.md) and
[Review Checklist](review-checklist.md) before requesting approval.

Documentation changes with the architecture and behavior it governs. Prefer a
short link to an owning document over repeating rules in multiple places.
