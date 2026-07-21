# Branching and Release

Source-control and deployment actions are separate approval boundaries. A clean
commit does not authorize a push, merge, release, or deployment.

## Working branches

- Work on the explicitly approved branch and confirm it before making changes.
- Do not switch, rebase, merge, reset, clean, amend, or rewrite history without
  direction.
- Preserve unrelated tracked and untracked work.
- Keep commits coherent, buildable, testable, and dependency-complete. Do not
  manufacture invalid intermediate states solely to obtain smaller commits.

## Commit preparation

1. Complete validation and technical review.
2. Define the exact file and hunk boundary.
3. Stage explicit paths or reviewed hunks; never use broad staging in a mixed
   worktree.
4. Inspect `git diff --cached`, its name/status list, statistics, and whitespace.
5. Scan for secrets, generated artifacts, environment files, and unrelated work.
6. Commit only after explicit approval, using the reviewed subject.

## Push, merge, and release

- Push only the approved branch and revision after confirming a clean worktree and
  expected remote.
- Merge only through the separately approved integration process.
- A release identifies an immutable commit, required migrations, configuration,
  secrets, backups, health checks, verification, and rollback procedure.
- Run migrations as an explicit release step; never rewrite applied history.
- Deploy only to the named environment and verify the deployed revision and
  critical routes. Preview authorization does not authorize production.

Follow the [Validation Standard](validation-standard.md) before approval and the
applicable deployment runbook during release operations.
