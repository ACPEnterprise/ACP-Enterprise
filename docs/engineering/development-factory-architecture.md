# ACP Development Factory Architecture

## Purpose and trust model

The Development Factory is repository-local engineering tooling that inspects,
validates, classifies, and reports. The repository is the authoritative policy
source. Humans approve architecture, file boundaries, commits, migrations,
merges, and deployments. The factory never approves its own work and contains
no commit, push, merge, deployment, infrastructure, preview, or production-data
operation.

The flow is:

```text
Developer or Codex work
→ repository-state and changed-file inspection
→ backend, frontend, migration, architecture, and security validation
→ stable JSON and concise Markdown reports
→ owner review
→ separately approved Git action
```

Tooling lives in `backend/development_factory`, outside `backend/app`. A runtime
isolation policy fails if application modules import it. Product runtime code
does not depend on factory tooling.

## Manifest and execution

`development-factory/manifest.json` is the ordered validation contract. Each
check declares its stable identifier, name, category, command or built-in
implementation, required state, applicable area, timeout, dependencies, failure
class, parallel-safety metadata, and report order. The current engine executes
deterministically in manifest order; parallel metadata is reserved for a later
isolated runner.

`development-factory/config.json` contains secretless local policy,
allowlists, mandatory-rationale suppressions, safe disposable PostgreSQL
container configuration, report location, and future parallelism limits.
Machine-specific values may use documented `DF_*` environment variables.

Missing dependencies produce `unavailable`, never `passed`. Explicitly
unselected checks produce `skipped`. Required failed, unavailable, or blocked
checks prevent “Ready for owner review.”

## Safe migration validation

Migration and backend-test checks create uniquely named databases whose names
must match the configured disposable prefix. They run inside the existing
PostgreSQL/backend containers, upgrade from empty, downgrade one revision,
re-upgrade, check metadata drift and heads, then force-drop and verify absence.
Creation failure, validation failure, or teardown failure fails closed.

The factory never accepts a general application `DATABASE_URL` for migration
validation and never targets preview or production names.

## Architecture and security checks

Deterministic heuristics inspect:

- Router SQL and direct persistence/transaction calls
- Repository commits, HTTP imports, authorization, and event publication
- HTTP construction in services
- SQL placement outside documented paths
- Runtime imports of factory tooling
- Merge markers and unresolved Git conflicts
- Prohibited automation actions
- Apparent missing Company predicates
- Obvious secret literals, plaintext-token persistence, CORS wildcards, and
  test authentication bypasses

Findings include paths and lines where practical. Suppressions require an exact
rule/path match and a committed rationale. Allowlisting and suppression never
silently erase findings from the policy process.

These checks identify review risks; they are not formal proofs of architecture,
authorization, tenant isolation, or security. They deliberately avoid forcing
product changes merely to satisfy simplistic pattern matching.

## Reports and future consumers

Generated artifacts live in ignored `.development-factory/`:

- `latest.json` follows `development-factory/report.schema.json`.
- `latest.md` is suitable for ChatGPT or phone review.

Reports contain safe tool/platform metadata, repository state, classifications,
durations, check outcomes, findings, test/migration summaries, warnings,
blocking failures, and owner-review items. Command output is bounded and common
secret assignments are redacted. Environment dumps and credentials are never
included.

The stable manifest and report contracts can later support CI, scheduled Codex
validation, isolated worktrees, agent task manifests, pull-request review,
remote notifications, mobile summaries, preview health checks, approval queues,
and quality trends. DF.1 implements none of those systems, no remote approvals,
no dashboard, and no autonomous repair or Git action.

## DF.2 task automation boundary

DF.2 adds a task-supervision layer to the same local Development Factory. A
versioned task contract describes the approved objective, scope, repository
preconditions, validation selection, file boundary, action permissions, stop
conditions, and required completion-report fields. The strict parser rejects
unknown fields and invalid combinations instead of guessing intent.

The task runner supports repository inspection, dry-run records, and existing
Development Factory validation. It deliberately has no implementation that
stages, commits, pushes, merges, deploys, rewrites history, destroys databases,
or changes infrastructure. Permission fields and workflow states are durable
contracts for checking whether a later, separately owner-approved action would
be authorized; they do not execute that action.

The workflow is:

```text
proposed → approved → running → ready_for_owner_review
                                  ↓ owner approval
                         approved_for_commit → committed
                                  ↓ owner approval
                           approved_for_push → pushed
                                  ↓ owner approval
                          approved_for_merge → merged
                                  ↓ owner approval
                     approved_for_deployment → deployed
```

`blocked`, `rejected`, and `cancelled` are explicit outcomes. Invalid
transitions fail closed. A successful validation run can reach only
`ready_for_owner_review`; it can never infer approval for a later action.

Generated task records live under ignored `.development-factory/runs/`.
Records contain safe command-stage identifiers rather than shell transcripts or
environment dumps, explicitly audit whether privileged actions occurred, and
reuse report redaction. Task and run-record schemas are versioned in
`development-factory/`.

This is local-first and vendor-neutral. A future CI runner, isolated agent, LIA
supervisor, or remote notification system may consume these contracts, but
must preserve the same state transitions and owner gates. DF.2 does not
implement remote execution, webhooks, parallel agents, a control plane, or an
approval interface.
