# Development Factory End-to-End Workflow

## What DF.4D proves

DF.4D composes the existing Development Factory without adding another
orchestrator:

```text
owner-approved LIA assignment
→ isolated DF.4A workspace
→ bounded DF.4B execution
→ DF.1 validation evidence
→ immutable worker record and provenance manifest
→ DF.4C consolidated owner review
→ explicit owner decision boundary
```

The deterministic demonstration creates one documentation file inside a
temporary Git repository and isolated worktree. It runs through the real
workspace, worker, validation, and review services. The supervising repository
never receives the file. No network, Docker daemon, AI provider, production
service, commit, merge, push, or deployment is involved.

Run the focused proof with:

```sh
PYTHONPATH=backend pytest -q \
  backend/tests/development_factory/test_factory_demonstration.py
```

The test fixture owns its temporary repository and removes it when the test
finishes. Development Factory production commands intentionally do not delete
owner workspaces.

## Trust boundaries

The owner approves architecture, scope, and every privileged action. LIA may
validate assignments, dependencies, boundaries, and evidence; it cannot infer
approval. A worker can perform only schema-validated, allowlisted operations
inside its assigned workspace and file/resource boundary. DF.4A owns workspace
identity and metadata, but does not destructively recover or clean workspaces.

Evidence shows that serialized values are internally consistent with the facts
the factory inspected. SHA-256 digests detect later content disagreement. They
do not prove who created content, establish trust in its author, or provide a
digital signature. Live repository verification remains required.

## Provenance chain

Each DF.4B record identifies:

- Supervisory run, assignment, worker, role, execution, and workspace
- Approved branch and full baseline commit
- Logical workspace-metadata and validation-evidence references
- Supervisory-contract, workspace-metadata, operations, validation-plan,
  validation-result, output-content, and complete provenance-manifest digests
- Declared paths and operation identifiers
- Start and completion timestamps
- Ending branch, HEAD, working-tree state, and validation result
- Ignored JSON/Markdown artifact references
- `owner_review_required`, `not_integrated`, and `workspace_retained` states

DF.4C validates this manifest, then checks the contract, current workspace
metadata, live branch and HEAD, changed paths, output content digests, index,
timestamps, and privileged-action audit. The consolidated package records each
worker provenance digest and an aggregate evidence-chain digest.

Missing fields, mismatched assignments or workspaces, unrelated supervisory
records, missing embedded validation evidence, changed manifests, output
outside declared boundaries, changed content, or unsupported approval claims
fail closed. Evidence is never silently repaired.

## Beginner owner workflow

1. Review the proposed milestone, worker boundaries, and validation selection.
2. Approve the assignment contract only if its scope is correct.
3. Prepare the isolated workspace with `lia workspace prepare`.
4. Run only the approved operations with `lia worker execute`.
5. Read the worker record and confirm validation passed and privileged audit
   values remain false.
6. Run `lia review inspect`, then `lia review consolidate`.
7. Open the Markdown file under ignored
   `.development-factory/owner-reviews/`.
8. Check provenance findings, changed paths, validation, conflicts, and the
   recommended review order.
9. Choose to continue review, reject, request revision/re-execution, retain the
   workspace, or approve only further integration planning.

Recording an approval does not integrate anything. A separately designed and
explicitly authorized future operation would still be required to copy,
stage, commit, merge, push, or deploy worker output.

## Safety and cleanup

Generated records remain under ignored `.development-factory/` locations.
Tests use temporary directories and clean only those test-owned resources.
Owner workspaces and evidence are retained until the owner separately decides
how they should be handled. The factory performs no automatic reset, clean,
worktree removal, branch deletion, conflict resolution, or infrastructure
mutation.
