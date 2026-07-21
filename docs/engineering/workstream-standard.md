# Workstream Standard

A workstream is the smallest reviewable body of ACP Enterprise work that produces
a coherent outcome. A sprint milestone may contain one or more workstreams.

## Required definition

Every workstream states:

- **Purpose:** the business or engineering outcome and why it matters.
- **Scope:** included behavior, systems, data, and explicit exclusions.
- **Dependencies:** existing services, contracts, migrations, decisions, and
  operational prerequisites.
- **Deliverables:** concrete code, schema, tests, documentation, or runbook
  outputs.
- **Acceptance Criteria:** observable conditions proving the outcome.
- **Risks:** security, tenant, data, concurrency, compatibility, operational, and
  delivery concerns with intended controls.
- **Completion Requirements:** validation evidence, review state, repository
  boundary, and approval needed to close the work.

## Execution rules

- Inspect the current branch, worktree, architecture, and relevant history before
  changing files.
- Preserve unrelated tracked and untracked work.
- Resolve ownership and transaction boundaries before implementation.
- Keep out-of-scope behavior unchanged.
- Add no placeholder behavior, hidden bypass, or untracked follow-up debt.
- Stop at the approved milestone boundary.

A workstream is ready for review only when its acceptance criteria and the
[Definition of Done](definition-of-done.md) are satisfied. Follow the
[Engineering Playbook](engineering-playbook.md) for sequencing.
