# LIA Isolation and Owner Guide

## Isolated workspace foundation

DF.3 records isolation plans. DF.4A may inspect and explicitly prepare those
planned workspaces from the exact approved commit. It does not execute workers
or remove workspaces.

Each future worker must:

1. Receive one approved task contract.
2. Use one isolated worktree or equivalent workspace.
3. Start from the exact owner-approved common HEAD.
4. Avoid the owner’s primary working tree.
5. Own only its declared files and shared-resource claims.
6. Produce its own Development Factory validation and run record.
7. Leave integration to a separate owner-reviewed step.

Workers may not share uncommitted state, create merges, perform privileged
actions, or conceal divergence. A workspace whose HEAD, branch, boundary, or
dependencies no longer match is stale and blocked.

Cleanup is manual and reviewed. DF.4A performs no branch deletion, destructive
workspace removal, reset, or history rewriting.

Workspace commands, provenance, and recovery classifications are documented in
`lia-workspace-lifecycle.md`.

DF.4B can execute one bounded operations document inside a ready workspace.
Before approving later action, review its Markdown record, unstaged diff,
validation, boundary findings, and false privileged-action audit values. See
`lia-worker-execution.md`.

## Owner phone review

The LIA Markdown report is designed for a short phone review. Check:

- Are the parent objective and worker scopes exactly what was approved?
- Are roles appropriate and bounded?
- Are wave-one tasks genuinely independent?
- Are later tasks waiting for their dependencies?
- Is any migration, schema, security, or integration surface contested?
- Does every worker use a distinct isolation plan?
- Are validation requirements complete?
- Are blockers and escalation flags understood?
- Is the proposed review/integration order sensible?
- Are commit, push, merge, and deployment audit values all false?

Approve or reject the decomposition separately from approving worker output.
Later commit, push, merge, and deployment decisions remain separate.

## Example dry run

```sh
./scripts/development-factory lia inspect \
  development-factory/examples/df3-lia-dry-run.json

./scripts/development-factory lia dry-run \
  development-factory/examples/df3-lia-dry-run.json
```

The example is fictional documentation inspection. Atlas and Nova occupy the
first parallel-safe wave. Scout depends on both and occupies the second wave.
No worker starts and no repository content changes.

The example’s starting HEAD is intentionally exact. Once the repository
advances, it blocks until an owner-approved contract names the new starting
point.

## Future operational LIA

Later milestones may connect these contracts to isolated worker launchers,
notifications, or owner dashboards. Those systems must remain separate from
ACP product runtime and preserve the same contract validation, explicit owner
gates, isolation, redaction, and no-self-integration rules.

## Consolidated phone review

DF.4C reads completed worker evidence without touching the workspaces. The
Markdown owner-review package answers, in order: what happened, what passed,
what is blocked, what conflicts exist, what to review first, and which decisions
remain yours.

“Verified ready for review” is not acceptance. Rejecting work, requesting
remediation, or preserving a workspace can be recorded as metadata. Commit,
merge, push, deployment, cleanup, and conflict resolution remain unavailable.
