# Review Checklist

Use this checklist for the technical-review stage of the
[Engineering Playbook](engineering-playbook.md). Apply only relevant sections, but
record why a high-risk section is not applicable.

## Scope and architecture

- Does the diff contain only the approved workstream and preserve unrelated work?
- Are API, service, repository, database, event, UI, and infrastructure ownership
  boundaries respected?
- Is business logic centralized rather than duplicated in routers or components?
- Are dependencies necessary, directional, and free of avoidable cycles?

## Correctness and data

- Are business invariants, transactions, rollback, idempotency, concurrency, and
  error behavior explicit and tested?
- Are migrations forward-safe, ordered, drift-free, and compatible with existing
  data?
- Are queries tenant-scoped, bounded, indexed, and free of avoidable N+1 access?

## Security

- Do authentication and authorization remain separate and fail closed?
- Are Company and Branch boundaries enforced before resource access?
- Are inputs validated and responses free of secrets and internal details?
- Are credential, token, audit, session, and event rules preserved?

## Quality and operations

- Do tests prove behavior, failure, isolation, and regression paths?
- Do lint, types, builds, migrations, and applicable runtime checks pass?
- Are logs, metrics, health behavior, recovery, and deployment effects appropriate
  to the scope?
- Do documentation and the proposed commit boundary match the implementation?
- Are there no placeholders, dead code, generated artifacts, or sensitive files?

Review is complete only when findings are resolved or explicitly accepted under
the [Definition of Done](definition-of-done.md).
