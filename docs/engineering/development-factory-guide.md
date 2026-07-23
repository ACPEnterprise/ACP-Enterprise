# Development Factory Operating Guide

The Development Factory checks work and writes reports. It does not change
source files, stage changes, commit, push, merge, or deploy.

Run commands from the repository root.

## Running one approved isolated worker

For an approved LIA contract and DF.4A workspace:

```sh
./scripts/development-factory lia worker inspect CONTRACT TASK_ID
./scripts/development-factory lia worker execute CONTRACT TASK_ID OPERATIONS
./scripts/development-factory lia worker diff CONTRACT TASK_ID
./scripts/development-factory lia worker record CONTRACT TASK_ID
```

The operations file is structured JSON, not a command prompt. Execution leaves
approved changes unstaged and uncommitted. Completion always requires owner
review. `lia worker cancel` records cancellation without removing or changing
workspace content.

## Commands

Full validation:

```sh
./scripts/development-factory validate
```

Backend only:

```sh
./scripts/development-factory validate --backend
```

Frontend only:

```sh
./scripts/development-factory validate --frontend
```

Safe disposable-database migration validation:

```sh
./scripts/development-factory validate --migrations
```

Architecture and security policies:

```sh
./scripts/development-factory validate --architecture
```

Select checks based on currently changed files:

```sh
./scripts/development-factory validate --changed
```

Print the latest Markdown report:

```sh
./scripts/development-factory report
```

Inspect an approved task contract without running validation:

```sh
./scripts/development-factory task inspect path/to/task.json
```

Create an inspection-only dry-run record:

```sh
./scripts/development-factory task run path/to/task.json --dry-run
```

Run the validation selection declared by an approved task:

```sh
./scripts/development-factory task run path/to/task.json
```

Check whether an action has both contract permission and the required explicit
workflow approval state:

```sh
./scripts/development-factory task check-action path/to/task.json \
  --action stage_and_commit --state approved_for_commit
```

This command checks authorization only. It never performs the action.

Inspect a LIA supervisory decomposition:

```sh
./scripts/development-factory lia inspect path/to/lia-contract.json
```

Generate an inspection-only execution-wave and integration-plan report:

```sh
./scripts/development-factory lia dry-run path/to/lia-contract.json
```

Confirm that LIA rejects a privileged action:

```sh
./scripts/development-factory lia check-action push
```

LIA does not start agents or create isolated workspaces. The commands validate
and report the owner-approved plan only.

Reports are stored locally at:

```text
.development-factory/latest.json
.development-factory/latest.md
.development-factory/runs/<run-id>.json
.development-factory/runs/<run-id>.md
.development-factory/lia/<supervisory-run-id>.json
.development-factory/lia/<supervisory-run-id>.md
```

This directory is ignored by Git.

## Understanding results

- `passed`: the check ran and succeeded.
- `failed`: the check ran and found a problem.
- `skipped`: your explicit selection did not request the check.
- `unavailable`: a required program or safe dependency was missing.
- `blocked`: an earlier required failure prevented safe execution.
- `not_applicable`: the check does not apply to this repository state.

Skipped and unavailable checks are never called passed. A required failure or
unavailable dependency blocks owner-review readiness.

Docker and the local ACP backend/PostgreSQL containers are required for backend
tests and migration validation. Node/npm dependencies are required for
frontend checks. Migration validation creates a uniquely named disposable
database, removes it afterward, and fails if removal cannot be confirmed.

The tool may report warnings from heuristic architecture or security scans.
Open the Markdown report for file and line references. Warnings require human
judgment; do not change product architecture mechanically to silence them.

## Task-contract failures

A task stops if a required branch, starting HEAD, clean-start condition, empty
index, or approved file boundary does not match. Ask the owner to review the
contract; do not edit the contract merely to bypass the mismatch.

Validation success means “Ready for owner review.” It does not mean permission
to stage, commit, push, merge, or deploy. Each later approval remains a
separate owner decision.
