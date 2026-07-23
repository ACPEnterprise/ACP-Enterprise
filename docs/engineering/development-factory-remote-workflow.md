# Development Factory Remote Owner Workflow

## Purpose

This workflow lets the ACP Enterprise owner direct and review engineering work
from an office computer, home computer, phone, or tablet without handing
architecture or release authority to automation. The repository remains the
source of truth; Development Factory records make the work concise enough for
remote review.

## The approval sequence

1. A task is proposed with an objective, allowed scope, prohibited scope,
   expected branch and starting revision, file boundary when known, required
   validation, and explicit permissions.
2. The owner approves or rejects that architecture and scope.
3. Codex verifies the task contract and repository state.
4. Codex performs only the approved work and stops on a contract mismatch.
5. The Development Factory runs the declared checks and creates JSON and
   Markdown records.
6. The owner reviews the changed-file boundary, validation, architecture,
   security, blockers, and recommended next action.
7. Commit approval is a new, separate instruction with an exact boundary and
   subject.
8. Push, merge, and deployment approvals are each separate later decisions.

Passing validation never grants any of those approvals.

## Office or home computer

From the repository root, inspect a task:

```sh
./scripts/development-factory task inspect development-factory/examples/df2-inspection-only.json
```

Generate a safe dry-run record:

```sh
./scripts/development-factory task run development-factory/examples/df2-inspection-only.json --dry-run
```

Run the task’s declared validation only after scope approval:

```sh
./scripts/development-factory task run path/to/approved-task.json
```

Review `.development-factory/runs/` and the normal
`.development-factory/latest.md`. These are local ignored artifacts.

## Phone or tablet

Ask Codex for the concise Markdown run summary and changed-file list. Review:

- Does the objective match what was approved?
- Are all changed files expected?
- Did required validation pass?
- Are any checks unavailable or blocked?
- Did architecture and security checks pass?
- Does the action audit show all privileged actions as false?
- Is the recommended next action owner review rather than an inferred approval?

If satisfied, send a separate approval for the precise next action. The owner
does not need to translate that approval into Git internals; the instruction
should name the intended outcome, exact file boundary where applicable, and
the approved subject or target.

## Block, reject, or stop

- `blocked` means a precondition or required check failed. Resolve the cause or
  issue a revised task; do not bypass it.
- `rejected` means the owner declined the task or result.
- `cancelled` means work must stop without advancing.

The owner can say “stop,” “reject this task,” or “do not proceed.” Automation
must preserve work safely, report state, and perform no later action.

## Safety and trust

DF.2 has no remote shell, webhook, cloud controller, autonomous approval,
hosted dashboard, or unattended release function. Task records exclude
credentials, tokens, private keys, environment dumps, and application data.
Run records identify validation stages but do not archive arbitrary shell
history.

The owner remains authoritative for architecture, commits, pushes, merges,
migrations, infrastructure, and deployments.

## DF.3 integration point

DF.3 may add LIA supervision and parallel isolated agents. LIA will consume the
same task contract, state model, permission gates, and run-record schema. It
must coordinate proposals and summaries without becoming an approval
authority. Parallel work must use isolated workspaces and cannot merge itself.
