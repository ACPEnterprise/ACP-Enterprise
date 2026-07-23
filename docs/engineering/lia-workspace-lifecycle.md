# LIA Isolated Workspace Lifecycle

## Boundary

DF.4A turns DF.3 workspace plans into safely prepared Git worktrees. It does
not execute workers, edit product code, clean workspaces, integrate results, or
perform privileged Git actions.

```text
owner-approved supervisory contract
→ owner repository verification
→ deterministic workspace identity
→ inspection
→ explicit preparation
→ ignored versioned metadata
→ owner review
```

The primary worktree must remain on the approved branch and exact approved
commit with a clean working tree and empty index.

## Identity and provenance

Each workspace identity contains the supervisory run, worker, task, workspace,
approved branch, full starting commit, deterministic path, and deterministic
workspace branch. Paths live below ignored
`.development-factory/workspaces/`. Collision-resistant normalized segments
make names safe without treating human labels as globally unique identifiers.

Preparation creates a branch and worktree directly from the approved commit. It
never switches, resets, cleans, or checks out the owner's primary worktree.

Metadata follows `workspace-metadata.schema.json` version 1.0 and is stored
below ignored `.development-factory/workspace-metadata/`. It records immutable
identity, creation and inspection timestamps, repository state, and validation
status. Validation remains `not_run` because worker execution is out of scope.

## Inspection and recovery

Inspection classifies a workspace as planned, ready, dirty, staged, untracked,
stale, interrupted, orphaned, mismatched, duplicate-owned, or
repository-diverged. It detects detached or wrong branches, HEAD movement,
workspace contents, missing or incomplete metadata, duplicate identity
ownership, and movement of the owner repository.

Preparation is idempotent only for a fully verified ready workspace. Every
other existing state fails closed and requires owner review. Interrupted
preparation, orphaned metadata, and stale workspaces are evidence; they are not
repaired automatically.

DF.4A deliberately provides no cleanup command. Worktree removal, branch
deletion, reset, clean, forced checkout, and automatic metadata repair remain
prohibited. Cleanup is manual and separately reviewed.

## Commands

```sh
./scripts/development-factory lia workspace list CONTRACT
./scripts/development-factory lia workspace inspect CONTRACT WORKSPACE_ID
./scripts/development-factory lia workspace prepare CONTRACT WORKSPACE_ID
./scripts/development-factory lia workspace show CONTRACT WORKSPACE_ID
```

`list` and `inspect` are read-only. `show` reads ignored metadata. `prepare` is
the only mutating operation and may only create the declared worktree and
metadata after all owner-repository checks pass.

## Relationship to DF.3

DF.3 remains authoritative for roles, scope inheritance, dependencies,
conflicts, and execution waves. DF.4A consumes its validated contract but does
not start an agent. Later separately approved work may add bounded worker
execution records and consolidated review without weakening these guarantees.
