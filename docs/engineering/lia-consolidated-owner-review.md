# LIA Consolidated Owner Review

## Purpose and boundary

DF.4C gives the owner one evidence package for several completed worker
workspaces. It reads an approved LIA contract, finalized DF.4B records, and the
corresponding live DF.4A workspaces. It does not run workers or alter their
output.

The package is advisory. “Verified ready for review” means the supplied
evidence is internally consistent enough for human review. It never means
approved, integrated, staged, committed, pushed, merged, or deployed.

## Consolidation lifecycle

```text
pending → records_loading → provenance_verifying
        → dependencies_analyzing → conflicts_analyzing
        → validation_consolidating → review_generating
        → completed or blocked → owner_review_required
```

Invalid transitions fail closed. A cancellation changes ignored Development
Factory metadata only and preserves every workspace and worker record.

## Inputs and provenance

The strict consolidation input identifies the parent contract by digest, the
approved branch and full starting SHA, included workers and records, expected
execution waves, evidence requirements, policies, and output identity. Unknown
fields are rejected.

Records are selected explicitly or discovered by their parsed supervisory-run
and task identities—not by filename alone. JSON and Markdown record pairs must
exist. The consolidator verifies role, task, workspace, branch, starting and
ending HEAD, timestamps, state history, and false privileged-action audits.

It then checks the live worktree and immutable DF.4A metadata. Branch, HEAD,
index, changed and untracked paths must agree with the record. Files modified
after record finalization are treated as provenance drift. Git metadata that
was not captured by DF.4B cannot be proven historically; uncertainty blocks or
is called out for owner review rather than being repaired.

DF.4D adds per-file content evidence and a worker provenance-manifest digest.
The review verifies the supervisory-contract and workspace-metadata digests,
declared paths and operations, validation evidence, live output hashes, and
explicit unapproved/unintegrated state. It then records an aggregate
evidence-chain digest. These hashes detect content disagreement but do not
prove authorship, identity, or trustworthiness.

## Dependencies, conflicts, and classifications

The DF.3 graph remains authoritative. Missing, failed, stale, contradictory, or
late dependencies block downstream readiness. Actual changed paths are
compared for exact, case-normalized, parent/child, file/directory, and declared
ownership conflicts. Typed resource claims cover migrations, schemas, public
contracts, API and security surfaces, routes, shared configuration, dependency
manifests, integration points, and shared test infrastructure.

Worker classifications distinguish verified review readiness from validation,
boundary, resource, contamination, provenance, security, architecture, and
dependency blockers. No conflict is automatically resolved and no ownership
claim is invented after execution.

Migration and durable-schema changes always require their declared ownership
and aggregate lifecycle/drift validation. Security-sensitive or tenant-
isolation surfaces require explicit owner attention even without a textual
merge conflict.

## Validation and ordering

Worker validation evidence is matched to approved selections. Missing, failed,
unsupported, or contradictory evidence blocks readiness. The package lists the
aggregate validation required after any separately approved future integration.
Passing validation is evidence, not approval.

Review order is deterministic: blockers and security-sensitive work first,
then migrations and schemas, shared contracts and integration points, backend,
frontend, tests, and documentation, with dependency and task-ID tie-breaking.
Future integration ordering is only a recommendation and contains no Git
commands.

## Owner decisions

The package asks the owner to accept work for continued review, reject it,
request remediation or re-execution, resolve scope or ownership ambiguity,
request more validation, preserve a workspace, or approve further planning.
Viewing the report makes no decision.

An owner-decision record is immutable ignored metadata tied to the exact review
digest. It can authorize only further planning. It cannot stage, commit,
cherry-pick, merge, push, deploy, delete, reset, or clean.

## Commands

```sh
./scripts/development-factory lia review inspect CONTRACT INPUT
./scripts/development-factory lia review consolidate CONTRACT INPUT
./scripts/development-factory lia review list CONTRACT
./scripts/development-factory lia review show CONTRACT REVIEW_ID
./scripts/development-factory lia review workers CONTRACT REVIEW_ID
./scripts/development-factory lia review conflicts CONTRACT REVIEW_ID
./scripts/development-factory lia review validations CONTRACT REVIEW_ID
./scripts/development-factory lia review decisions CONTRACT REVIEW_ID
./scripts/development-factory lia review record-decision CONTRACT REVIEW_ID DECISION
./scripts/development-factory lia review cancel CONTRACT REVIEW_ID
```

`inspect`, `list`, `show`, and section commands are read-only. `consolidate`,
`record-decision`, and `cancel` write only ignored Development Factory
metadata. Final packages cannot be overwritten.

## Reports, recovery, and secrets

JSON and concise Markdown packages live under ignored
`.development-factory/owner-reviews/`; decisions live under ignored
`.development-factory/owner-decisions/`. Reports use bounded summaries,
redaction, digests, and explicit false audit flags. They do not copy source
files, environment dumps, credentials, or raw shell history.

Partial packages, reused IDs, changed inputs, stale decision digests, or
interrupted consolidation require a new identity and renewed owner review.
The consolidator never repairs, resets, cleans, removes, or overwrites evidence.

DF.4D may complete broader validation and demonstrations. Any future
integration capability requires a separately approved milestone with its own
privileged workflow.
