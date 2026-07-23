# LIA Supervisory Architecture

## Purpose and authority

LIA means Leadership Intelligence Assistant. It is an engineering supervisory
layer, not ACP product runtime and not an approval authority.

```text
Owner
→ approved LIA supervisory contract
→ specialized worker task contracts
→ isolated-workspace plan
→ Development Factory validation records
→ advisory integration plan
→ consolidated owner review
→ separately approved privileged actions
```

The owner exclusively approves architecture, task scope, commits, pushes,
merges, deployments, rejection, and cancellation. LIA may inspect, classify,
sequence, summarize, recommend, and escalate. Passing validation never implies
approval.

## Contract composition

`lia-supervisory-contract.schema.json` version 1.0 embeds the authoritative
DF.2 worker task contract. The parent declares:

- Parent objective and owner-approved scope
- Common branch and full starting HEAD
- Parent permission ceiling
- Explicit permission for parallel planning
- Worker role and task assignments
- Dependency edges and exclusive file boundaries
- Typed resource claims for migrations, shared schemas, security surfaces,
  integration surfaces, databases, and documentation
- Isolated workspace identifiers and branch hints
- Validation and owner-reviewed integration strategy
- Fail-closed conflict and stop policies
- Required report fields and owner approval requirements

Unknown fields, duplicate tasks or agents, cycles, unknown dependencies,
workspace collisions, scope expansion, permission escalation, repository
mismatches, and exclusive ownership conflicts are rejected.

## Roles

The initial stable roles are:

- `atlas`: backend and service architecture
- `nova`: frontend and user experience
- `forge`: persistence, migrations, and database architecture
- `sentinel`: security, authorization, and tenant isolation
- `scout`: testing, validation, and quality assurance

The role catalog defines permitted and prohibited responsibilities, default
validation, escalation conditions, code-proposal and review capability, and
explicitly false commit/push/merge/deployment authority. These are bounded
roles, not unrestricted general-purpose agents.

## Dependency and conflict planning

Dependencies form a directed acyclic graph. The planner uses stable task-ID
ordering to produce reproducible waves. Two tasks share a wave only when:

- Their dependencies are satisfied
- Parent and worker contracts permit parallel planning
- Exclusive file patterns do not overlap
- They do not claim a common shared resource
- No migration, schema, security, database, or integration boundary conflicts
- Neither task requires escalation

Exclusive resource conflicts invalidate the contract. Shared resource use is
valid but sequential. Explicit architecture, security, tenant, scope, or
validation ambiguity is reported for owner review.

The planner classifies tasks as `parallel_safe`, `sequential_required`,
`blocked`, or `owner_review_required`. DF.3 simulates planning only; it does
not execute concurrent sessions.

## Advisory integration planning

After future workers complete, LIA can combine immutable outcome summaries into
an advisory plan containing completion and validation state, changed files,
dependency order, conflict risk, review order, proposed integration order,
required aggregate revalidation, blockers, and owner decisions.

LIA cannot stage, cherry-pick, commit, merge, push, deploy, or resolve conflicts
by broadening scope. Integration always returns to owner review.

## Reports and security

Supervisory JSON and Markdown records follow
`lia-supervisory-report.schema.json` and are written to ignored
`.development-factory/lia/`. Reports use existing redaction, include no
environment dump, and record every privileged-action audit flag as false.

The contract and report formats are local-first, vendor-neutral, deterministic,
and suitable for later CI or remote supervision. They do not depend on a
specific AI service.

## Fail-closed escalation

LIA stops for:

- Architecture, authorization, tenant, or security uncertainty
- Migration, schema, file, or integration ownership conflict
- Parent scope expansion or invalid assumptions
- Worker output conflicts
- Incomplete or unavailable validation
- Repository divergence
- Privileged or destructive action requests

No automated conflict resolution may expand the owner-approved boundary.

## DF.4C evidence consolidation

DF.4C realizes the advisory-review boundary anticipated here. It reuses this
contract’s assignments, roles, dependencies, waves, file patterns, and typed
resource claims. Finalized worker records are not trusted alone: their live
workspaces and DF.4A metadata must still match.

The resulting review and future integration ordering are recommendations only.
They contain exact owner decisions and aggregate revalidation requirements but
cannot grant approval or invoke a privileged action.
