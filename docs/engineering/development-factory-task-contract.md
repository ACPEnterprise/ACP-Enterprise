# Development Factory Task Contract

## Contract structure

`development-factory/task-contract.schema.json` defines version 1.0. Contracts
are JSON so they are deterministic, machine-readable, diffable, and easy to
review without a vendor-specific runtime.

Required fields describe:

- Stable task ID, milestone, and objective
- Current workflow state
- Approved and prohibited scope
- Expected branch and full starting revision
- Allowed changed-file patterns
- Required Development Factory validation areas
- Explicit code-change, stage/commit, push, merge, and deployment permissions
- Fail-closed repository stop conditions
- Required milestone completion-report sections

Unknown fields, duplicate entries, unsupported validation combinations, short
revision identifiers, and invalid workflow states are rejected.

An empty allowed-file boundary means that the boundary is not yet known; it
does not grant product scope. The approved-scope and prohibited-scope text
remain authoritative, and the final exact boundary still requires owner
review. When patterns are supplied and boundary enforcement is enabled,
unexpected paths block the run.

## State and permission separation

Permission and approval state are both required. For example, a contract that
permits a commit still cannot authorize it while the workflow is merely
`ready_for_owner_review`. It must separately reach
`approved_for_commit`. Validation never makes that transition.

DF.2 checks these gates but does not implement privileged actions. Destructive
actions are always rejected.

## Safe example

`development-factory/examples/df2-inspection-only.json` has all privileged
permissions disabled. It exists to demonstrate inspection and local run-record
generation. Its expected revision is intentionally exact; after the repository
advances, execution blocks until an owner-approved task contract names the new
starting revision.

## Run records

`development-factory/run-record.schema.json` defines the local run record.
Records include starting and ending repository state, safe validation-stage
identifiers, changed files, blockers, state, next action, and explicit booleans
for commit, push, merge, and deployment occurrence. Generated instances are
ignored under `.development-factory/runs/`.
