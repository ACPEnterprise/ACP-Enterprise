# LIA Bounded Worker Execution

## Owner summary

DF.4B lets one approved worker operate inside one verified DF.4A workspace.
The worker receives structured operations rather than a shell. It can inspect
approved files and, only when every permission agrees, make deterministic text
changes inside its declared boundary.

The worker never stages, commits, pushes, merges, deploys, removes a worktree,
deletes a branch, or changes the owner's primary worktree. Completion means
only that the operation and validation finished and a record awaits review.

```text
approved LIA contract
→ verified isolated workspace
→ allowlisted operation adapter
→ boundary and permission checks
→ worker-local Development Factory validation
→ contamination inspection
→ immutable JSON and Markdown record
→ owner review
```

DF.4B handles one worker. Consolidated review belongs to DF.4C.

## States and operations

The transition model is:

```text
pending → workspace_verifying → workspace_ready → running
→ validation_running → completed or blocked → owner_review_required
```

`failed` and `cancelled` are explicit alternatives. Invalid transitions fail
closed. Completed never means approved or integrated.

The version 1.0 operations contract accepts only `inspect_file`,
`inspect_paths`, `write_text_file`, `append_text_file`,
`replace_exact_text`, and `create_demonstration_file`. There are no raw
commands, executable names, shell strings, or environment dumps.

Paths must be relative POSIX paths matching approved patterns. Absolute paths,
parent traversal, `.git`, `.development-factory`, environment and credential
paths, symlinks, and workspace escape are denied.

## Permissions, resources, and bounds

Mutation requires parent permission, worker permission, role permission,
mutation action approval, a verified workspace, an approved file pattern, and
an owned resource claim when declared. No worker receives privileged Git,
deployment, cleanup, or destructive authority.

Each run limits operations, mutations, inspected files, changed files, record
bytes, validation selections, and elapsed time. Exceeding a bound preserves
the workspace and blocks the result.

Validation uses existing Development Factory selections approved by the
parent, worker, and role. Missing, unavailable, or failed required validation
blocks completion. Passing never grants approval.

## Contamination and records

DF.4B compares workspace and primary branch, HEAD, index, status, worktree and
branch registries, local Git configuration, and hooks. It inspects actual files
for boundary escape, symlinks, special files, generated databases, keys, and
credential-like content. Findings block the result and are never reverted.

Final records use exclusive creation beneath ignored
`.development-factory/worker-executions/`. They contain provenance, state
history, permissions, operations, files, validation, findings, blockers,
redaction status, and false privileged-action audit values.

Reused execution IDs are denied. Missing, partial, stale, or disagreeing state
requires owner review. Cancellation writes metadata only and preserves every
workspace change. DF.4B provides no cleanup.

## Commands

```sh
./scripts/development-factory lia worker inspect CONTRACT TASK_ID
./scripts/development-factory lia worker execute CONTRACT TASK_ID OPERATIONS
./scripts/development-factory lia worker validate CONTRACT TASK_ID
./scripts/development-factory lia worker show CONTRACT TASK_ID
./scripts/development-factory lia worker diff CONTRACT TASK_ID
./scripts/development-factory lia worker record CONTRACT TASK_ID
./scripts/development-factory lia worker cancel CONTRACT TASK_ID
```

There are intentionally no stage, commit, cherry-pick, merge, push, deployment,
reset, cleanup, worktree-removal, or branch-deletion commands.
