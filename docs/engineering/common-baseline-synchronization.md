# Common baseline synchronization

The qualified development baseline is
`6aec17be3ac0bc1316975b0222f39bc7c9903837` at
`origin/handoff/friday-consolidated-20261127`. Hosted immutable qualification run
`46029775062` completed successfully for that exact commit.

Every worker successor must preserve its existing branch and worktree, then:

1. Fetch the authoritative remote and verify the full baseline SHA.
2. Checkpoint dirty or unpublished work without rewriting a published ref.
3. Create a new nonprotected successor branch from the exact baseline.
4. Use `git cherry` or `git log --cherry-pick --right-only` to identify only the
   lane's unique assignment commits. Replay those commits in chronological order;
   do not replay superseded CI fixes.
5. Confirm the diff stays inside the assignment's allowed paths and use
   `git range-diff` to confirm that worker implementation was preserved.
6. Require `git merge-base --is-ancestor 6aec17be3ac0bc1316975b0222f39bc7c9903837 HEAD`,
   `scripts/verify-development-candidate.py`,
   `scripts/verify-platform-corrections.py`, `git diff --check`, and the lane's
   focused checks before publication.
7. Accumulate implementation and evidence locally and make one non-force push to
   a new `work/**` ref. Its bounded hosted preflight rejects ancestry or
   preservation drift without installing the full dependency graph.
8. Publish the same stable SHA, without another commit, to a new `handoff/**` ref.
   The handoff must complete the mandatory full hosted static, backend, frontend,
   mobile, artifact construction, independent verification, and publication job.
9. Laptop Reviewer independently repeats ancestry and preservation checks. Laptop
   Master remains the only integration authority.

Old task refs are frozen. They must not receive evidence-only follow-up pushes,
rebases, force-pushes, or partial workflow repairs. A failed or cancelled SHA is
not qualified evidence.

## Trigger policy

`work/**` pushes run only the bounded ancestry and preservation preflight.
`handoff/**`, `integration/**`, and pull requests always run full qualification.
There are no path exclusions for release-bearing candidates. Evidence-only is an
informational classification, never permission to skip full candidate
qualification. Hosted artifacts and the workflow URL are the receipt; do not add
a post-CI evidence commit to the candidate merely to record them.

Rapid updates to a work ref may cancel its superseded preflight. Full handoff and
integration runs do not cancel each other. Publish a new successor ref if a
qualified handoff must change.
