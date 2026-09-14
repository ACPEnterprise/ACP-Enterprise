# OM1 Enterprise integration queue

Snapshot: 2026-09-14 13:09 America/New_York

## Authority and deployed state

- Protected authority: `7cdfb183c1d07e064eba88cc547df4f090708ff6`
- Protected tip: PR #263, current-overlay dependency ordering
- Deployed Preview: `7cdfb183c1d07e064eba88cc547df4f090708ff6`
- Preview health: application healthy; PostgreSQL and Redis connected
- Deployment gap: none; deployed and protected SHAs match
- Acceptance state: pending. A transient HTTP 502 occurred during deployment;
  exact-SHA health recovered by 2026-09-14 13:08 America/New_York. Required
  #261/#262/#263 qualification and authenticated persona evidence have not been
  supplied.
- GitHub CI evidence: no check runs or commit statuses are reported for the
  protected SHA. Local qualification does not substitute for the tests below.

Independent qualification of that exact protected-but-undeployed tranche on
2026-09-12 passed PostgreSQL zero-to-head, 20 affected backend tests, nine
affected frontend suites and 43 tests, full ESLint, and the production
TypeScript/Vite build. Four SQLAlchemy transaction-deassociation warnings were
emitted by Invoice tests and remain part of the evidence.

PR #261 added an explicit rollback between read-only authorization resolution
and fixture mutation plus one focused regression test. It has no GitHub checks.
Composition and `git diff --check` were revalidated at the exact protected SHA
on 2026-09-14. The focused test could not be rerun on this host: the installed
pytest uses Python 3.9, which cannot import the repository's modern type syntax,
while the available Python 3.12 environment has no pytest. Enterprise must run
that test under the supported backend environment before accepting this
deployment or deploying another batch:

```bash
ENVIRONMENT=test PYTHONPATH=backend python -m pytest -q \
  backend/tests/platform/test_preview_tenant_fixture_command.py
```

PR #262 integrated the lineage bootstrap without GitHub checks or statuses.
Its focused PostgreSQL tests and zero-to-head migration qualification remain
mandatory before accepting this deployment or deploying another batch; exact
commands appear in the lineage section.

PR #263 integrated deterministic Customer-to-Location-to-Job-to-Appointment
overlay ordering without GitHub checks or statuses. Its focused overlay test
suite is mandatory before accepting this deployment or guarded execution.

## Protected integration policy

GitHub ruleset `21781922` is active for exactly
`refs/heads/customer-management-v1`. It blocks branch deletion and
non-fast-forward updates and requires changes to enter through a pull request.
It allows merge, squash, or rebase integration. It has no bypass actors, but it
requires zero approving reviews, no code-owner review, no last-push approval,
and no status checks. Enterprise must therefore enforce the qualification and
acceptance gates in this packet operationally; GitHub will not enforce them.

## Active candidates

| Candidate | Exact branch | Head | PR | Behind/ahead | Effective tree | Classification |
|---|---|---|---|---:|---|---|
| OM2-C persona contract and acceptance harness | `work/om2c-launch-20260911-e2e-acceptance-1` | `2b749ff29d2f1c15210ed0bc22ac739eb5a46913` | None; prior #212 is merged | 2/44 | `24b59e6e1877f19652b6f75e2ad8e62248ddbbb8` | Stale but reconcilable; merge-clean; authority metadata edit and fresh PR required |
| SOURCE.4 artifact recovery | `work/migration-source4-accepted-artifact-recovery-1` | `a3cad3d389b9ed69300939d15c19e2d7b08da063` | None | 5/1 | `e0f59598461a17e858a38d3ebb5e55bd5abb8f5a` | Stale but reconcilable; merge-clean; documentation-only |
| HCP historical safe-tranche builder | `work/hcp-historical-safe-tranche-1` | `b32f99ff80f447bf8140b73380d19191ccb8db59` | None | 15/1 | `72a4cd1b0c5c5f5f735591945559f9944c44c6aa` | Stale but reconcilable; merge-clean; metadata edit required |
| ECO reconciliation | `work/eco-migration-reconciliation-integration-watch-1` | `1c0e7b20db62b6a342548f2842ea1a3a45965386` | None | 7/13 | `6045a450b3013f7785c746d392cffd0e91c6e23f` | Blocked on schema reconciliation; duplicate protected revision ID; do not integrate current head |
| Payroll/QBO read UI | `work/om2b-payroll-accounting-continuation-1` | `724398348b566f655d2bc7127c20beeb6be52d6c` | #215 open/CLEAN | 26/1 | `0c85fa8fea4302f432986d0f3cc1a356dffaa0f0` | Stale but reconcilable; merge-clean; PR refresh required |
| Mobile Apple release packet | `work/mobile-apple-owner-release-packet-1` | `0183eaec3e2825a79b683e9e684a761243c86ea7` | None | 12/15 | `629471e756f243cb75ada33772e95f349e7ef4f6` | Stale but reconcilable; merge-clean; two manifest edits required |

## Named launch queue coverage

| Lane originally requested | Current disposition |
|---|---|
| JOB-000306 owner-observed failure | Acceptance observation; reproduce only after the protected deployment gap is deployed. No independent candidate is present. |
| Scheduling mutation registry | `e26c9bd5...` now conflicts in the registry and its test; protected #237 is authoritative. Do not integrate the stale branch. |
| Laptop1-A CSR booking | `d172cd11...` conflicts with the evolved Scheduling UI; protected #241 and recovery #250 are authoritative. Do not integrate the stale branch. |
| Laptop1-B Customer office UX | `8516b08b...` conflicts in one add/add reliability test, while current-authority reconciliation `174fcd4e...` composes to zero delta. Superseded by #242 and #257. |
| Workforce / Payroll #216 | Merged as `d52d1178...`; already protected. |
| Workforce / Payroll #221, stacked #222, and #223 | Closed; their current successors are protected through #229, #231, and #235 respectively. |
| Current OM2 successor | Persona-contract and authenticated-acceptance successor `2b749ff2...` is current and active. Its former PR #212 is already merged and does not cover the new head; open a fresh PR. |
| Payroll tax rule | Reconciled `9a44f714...` composes to zero delta; superseded by protected #236. |
| Identity #227 and #230 | Still open but superseded by protected #256 and #258; close, do not integrate. |
| Identity recovery successor | `4cf7bdf4...` composes to zero delta; protected #256 is authoritative. |
| Laptop1 Phone distribution readiness | `bf28a61c...` is an ancestor of the active Mobile owner-release packet; integrate only the successor packet. |
| ECO named commits and persistence | `d7ef88d1...` and `37b32949...` are superseded by patch-evolved equivalents; `fe7a9623...`, `f587c271...`, and persistence `863cab13...` feed the active ECO watch. |
| QBO `5fe11183...` | Superseded by protected real-company evidence #243. Preserve the OAuth owner gate. |
| Migration executor / acceptance | `5b8b02de...` and `83bbeef0...` are superseded by protected guarded execution and acceptance #253. Lineage dependency `9b9d3023...` is protected through #262; recovery and builder remain active preparation. Guarded execution remains owner-only. |
| Price Book operator readiness | `c1c90a0a...` is superseded by the broader held review candidate `49e852aa...`; no candidate is admissible yet. |

Zero-delta classifications above use a three-way composition with current
protected authority, not a direct endpoint diff. Conflicting stale branches are
not reconciliation inputs: use their named protected successors as authority.

The six remaining effective deltas have zero pairwise file overlap. ECO is not
admissible: its differently named migration still declares protected revision
`g7i9k1m3o5q7` from `f6h8j0l2n4p6`. The five-candidate combined tree excluding
ECO is `45131ad133b06b15ec4e03c6fb92c1012db678c6`; it changes 51 files and passes
`git diff --check`. Recompute all trees after protected movement or packet edits.

## Integration order and release waves

There is no Git-level dependency between active candidates. Prefer this
operational order:

1. OM2-C persona contract and acceptance harness, before deployed acceptance.
2. SOURCE.4 artifact recovery and safe-tranche builder preparation; lineage and
   parent ordering are protected through #262/#263 and require qualification
   before acceptance or guarded execution.
3. Reconcile ECO onto protected schema with a new unique revision
   ID/down-revision, then integrate ECO as its own database checkpoint.
4. PR #215 in Wave B if QBO read-evidence acceptance is scheduled.
5. Mobile in Wave D; authoritative Job Clock `d52d1178` is already protected.

Do not execute Migration admission, authorize QBO, execute Payroll, or sign or
upload an Apple build as part of integration.

## Dependency graph

```mermaid
flowchart LR
    A[Protected 7cdfb183] -->|reconcile| R[SOURCE.4 recovery]
    A --> C[OM2-C persona contract]
    A --> L[Protected lineage #262/#263 qualification]
    A -->|reconcile| B[Historical builder]
    A -->|reconcile| E[ECO watch]
    A -->|reconcile| P[PR 215]
    A -->|reconcile| M[Mobile owner packet]
    R -.->|operational evidence order| B
    R --> I[Enterprise per-lane PR integration]
    B --> I
    E --> I
    P --> I
    M --> I
    C --> I
    L -.->|new revision downstream of protected g7| E
    I --> D[Enterprise deployment]
    L --> D
    D --> H[Exact deployed-SHA health gate]
    H --> EA[ECO acceptance]
    H --> QA[QBO read-only acceptance]
    H --> MA[Mobile readiness acceptance]
    H --> XA[Migration artifact acceptance]
    C --> PA[Sealed persona acceptance]
    H --> PA
    XA -.->|separate owner authority| MG[Guarded Migration admission]
    QA -.->|separate owner authority| QG[QBO OAuth]
    MA -.->|separate owner authority| AG[Apple signing and upload]
```

Solid candidate-to-integration arrows do not require a combined batch; each lane
may enter independently through its own PR. There are no hard Git dependency
edges or effective file overlaps among the six candidates. The dotted
SOURCE.4-to-builder edge is operational ordering only. The dotted lineage/ECO
edge is a mandatory schema reconciliation boundary, not permission to batch.
Dotted owner-gate edges
are explicitly outside this packet's authority. Price Book is omitted from the
integration path because it remains held.

## Batch boundaries and refresh checkpoints

All six remaining lanes may be inspected concurrently from the guarded
authority above. Integration remains sequential because the first protected PR
changes the authority for every remaining lane. ECO qualification cannot
complete until its duplicate Alembic revision is replaced downstream of #262.

| Checkpoint | Enterprise action | Required stop condition |
|---|---|---|
| Acceptance tooling | Reconcile `2b749ff2...` to `7cdfb183...`, update its contract authority, open a fresh PR, integrate it, refetch, then deploy the resulting protected tip containing #257-#263 and this contract | Contract tests fail, protected SHA moves, persona permissions/digests differ, or secret material appears in arguments/evidence |
| Current deployed acceptance | Preserve the recovered healthy exact-SHA result for `7cdfb183...` and the transient 502 evidence; run missing #261/#262/#263 qualification; do not mark accepted until evidence is attached | Focused test, zero-to-head migration, exactly-one-head/drift check fails, or health/dependency state regresses |
| Wave C preparation | Qualify protected #262/#263 before acceptance; prepare SOURCE.4 recovery and retain the historical builder as preparation tooling | Artifact digest/loader check, lineage/parent-order tests, exactly-one-head check, zero-to-head migration, builder tests, or authority metadata fails |
| ECO checkpoint | Assign ECO a new unique revision ID with down-revision `g7i9k1m3o5q7`; requalify, then integrate/deploy independently | Duplicate/multiple Alembic head, drift, migration failure, or governed-policy acceptance failure |
| Wave B | Integrate PR #215 independently | QBO/Payroll projection tests fail or any provider mutation appears |
| Wave D | Integrate Mobile independently | Test/static/preflight failure or either manifest is stale |

After every protected integration, stop before integrating another candidate and
run this read-only checkpoint in a clone containing the remaining remote branch:

```bash
set -euo pipefail
git fetch origin --prune
prior_authority="REPLACE_WITH_AUTHORITY_USED_FOR_LAST_QUALIFICATION"
new_authority=$(git rev-parse origin/customer-management-v1)
test "$new_authority" != "$prior_authority"
lane=work/REMAINING_LANE
expected_head="REPLACE_WITH_EXPECTED_REMOTE_HEAD"
test "$(git rev-parse "origin/$lane")" = "$expected_head"
composed_tree=$(git merge-tree --write-tree "$new_authority" "origin/$lane")
git cat-file -e "$composed_tree^{tree}"
git diff --check "$new_authority^{tree}" "$composed_tree"
git diff --name-status "$new_authority^{tree}" "$composed_tree"
```

The command exits nonzero on a merge conflict. Recompute behind/ahead counts,
effective trees, pairwise overlaps, metadata edits, and test scope before the
next integration. If ECO is blocked, proceed with reconciliation and
qualification of PR #215 or Mobile; neither depends on ECO. Owner-gated
Migration admission, QBO OAuth, Payroll execution, and Apple distribution never
block preparation of an independent lane.

## Required reconciliation and qualification

All candidate heads remain fetchable from `origin`; PR #215's branch head and
`refs/pull/215/head` both resolve to `724398348b566f655d2bc7127c20beeb6be52d6c`.
Use a clean worktree for one lane at a time. The following sequence is
pre-integration only: it updates the candidate branch and never checks out,
pushes, or merges the protected branch.

```bash
git fetch origin --prune
test "$(git rev-parse origin/customer-management-v1)" = \
  7cdfb183c1d07e064eba88cc547df4f090708ff6

lane=work/REPLACE_WITH_LANE
expected=REPLACE_WITH_FULL_HEAD
test "$(git rev-parse "origin/$lane")" = "$expected"
git switch --force-create "$lane" "origin/$lane"
git merge --no-edit origin/customer-management-v1
git diff --check origin/customer-management-v1...HEAD
```

Replace the two placeholders with exactly one row below. Stop and recompute the
packet if either SHA guard fails or the merge conflicts.

| Lane | Expected head |
|---|---|
| `work/om2c-launch-20260911-e2e-acceptance-1` | `2b749ff29d2f1c15210ed0bc22ac739eb5a46913` |
| `work/migration-source4-accepted-artifact-recovery-1` | `a3cad3d389b9ed69300939d15c19e2d7b08da063` |
| `work/hcp-historical-safe-tranche-1` | `b32f99ff80f447bf8140b73380d19191ccb8db59` |
| `work/eco-migration-reconciliation-integration-watch-1` | `1c0e7b20db62b6a342548f2842ea1a3a45965386` |
| `work/om2b-payroll-accounting-continuation-1` | `724398348b566f655d2bc7127c20beeb6be52d6c` |
| `work/mobile-apple-owner-release-packet-1` | `0183eaec3e2825a79b683e9e684a761243c86ea7` |

After the lane-specific edits and tests below, commit and push only that lane,
then open or refresh its PR into `customer-management-v1`. Enterprise must
review the resulting PR delta and integrate it through the ruleset-required PR
flow; direct protected updates are not an execution option.

### OM2-C persona contract and acceptance harness

The branch is based on exact protected authority and has no open PR. PR #212 is
historical and already merged; do not append this head to that closed identity.
Open a fresh PR for the 16-file effective delta. It has no Alembic migration and
zero file overlap with every other active or held lane.

Static qualification on 2026-09-14 passed Python 3.12 compilation for both
scripts and the 12-test module, JSON parsing for the contract/schema/example,
all four canonical permission digests, empty default mutation lists, and the
declared persona mutation ceilings. Full pytest was not runnable locally because
the Python 3.12 environment lacks pytest; require it in the supported backend
environment before integration:

```bash
ENVIRONMENT=test PYTHONPATH=backend python -m pytest -q \
  backend/tests/platform/test_authenticated_preview_acceptance.py
python -m compileall -q \
  backend/scripts/acceptance_identity_provisioning_contract.py \
  backend/scripts/authenticated_preview_acceptance.py
```

Update the contract's protected authority from `e1015aad...` to `7cdfb183...`.
Require that exact authority, exact synthetic Company/Branch IDs,
exact permission digests, file references under
`/run/secrets/acp-preview-acceptance/v1/{run_id}`, directory mode `0700`, file
mode `0600`, and no credential content in contract, attestation, report, logs,
or command arguments. EMPLOYEE, OFFICE, and QBO_READ must retain empty maximum
mutation lists. CSR may name only the scheduling route and receives no mutation
authority unless Enterprise seals that route into the run attestation.

### SOURCE.4 bounded lineage bootstrap

PR #262 integrated `9b9d3023...` as `efbe85fa...`; PR #263 then integrated
deterministic parent ordering as protected `7cdfb183...`. Together they close the
missing SOURCE.4 run-lineage dependency for bounded current-operational overlay
admission without admitting the canonical population. It retains 1,389
canonical holds and `canonical_admission_allowed: false`. Do not integrate the
current ECO head because its migration reuses protected revision
`g7i9k1m3o5q7`; ECO must receive a new revision downstream of that head.

Static qualification on 2026-09-14 passed Python 3.12 compilation for the
affected #262 application/model files, migration, and tests, plus the #263
executor and test. The protected tranche adds four lineage tests, updates two
command tests, and adds the parent-order case to the seven-test executor module.
Full tests and database qualification remain required in a supported environment
with a fresh disposable PostgreSQL database:

```bash
test -n "$QUALIFICATION_DATABASE_URL"
cd backend
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic upgrade head
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic current
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic heads
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic check
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" pytest -q \
  tests/operational_migration/test_hcp_current_overlay_lineage.py \
  tests/operational_migration/test_hcp_current_overlay_command.py \
  tests/operational_migration/test_hcp_current_overlay.py
python -m compileall -q \
  app/operational_migration/hcp_current_overlay.py \
  app/operational_migration/hcp_current_overlay_adapter.py \
  app/operational_migration/hcp_current_overlay_command.py \
  app/operational_migration/hcp_current_overlay_lineage.py \
  app/operational_migration/hcp_current_overlay_native.py \
  app/operational_migration/models.py \
  tests/operational_migration/test_hcp_current_overlay.py \
  tests/operational_migration/test_hcp_current_overlay_command.py \
  tests/operational_migration/test_hcp_current_overlay_lineage.py
```

Require exactly one current/head revision and no drift. Validate atomic master
and child creation, deterministic replay, fail-closed conflicting bindings,
rollback on failure, receipt persistence, the 503-assertion scope, canonical
hold count 1,389, terminal status `completed_current_operational`, and ordered
Customer-to-Location-to-Job-to-Appointment processing even when the packet is
child-first. These tests and integration do not authorize
`--authorize-preview-execution`; guarded
Preview execution remains a separate owner action requiring a fresh backup,
verified isolated-restore receipt, mode-0600 v2 authority, exact deployed SHA,
and exact schema head.

### SOURCE.4 artifact recovery

Merge current protected authority into
`work/migration-source4-accepted-artifact-recovery-1`, require tree
`e0f59598461a17e858a38d3ebb5e55bd5abb8f5a`, run `git diff --check`, push the
lane branch, and open a documentation PR. The packet contains no protected SHA
that needs editing.

Independent host revalidation on 2026-09-12 confirmed both documented byte
SHA-256 values, sizes, owner/group, and mode `0600`. The protected
`CurrentOverlayManifest.load` accepted the `hcp-current-overlay/v1` artifact at
canonical digest `e23b7bcf5ac34ea650184afacc711af0c7028e83a6b1f7405e2ae17e13441eb2`
with exactly 503 records. The hold packet binds the documented delta digest and
contains 10 duplicate-risk plus 3 insufficient-evidence Appointment holds, 22
Location-unresolved Job holds, and zero true global blockers.

Reproduce the read-only artifact checks on the host that owns the recovered
files. Do not run the recovery packet's staging/install or executor commands.

```bash
SOURCE_ROOT=/Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-admission-packet-20260912T170000Z
test "$(stat -f '%Lp' "$SOURCE_ROOT/current-overlay-merge-packet.json")" = 600
test "$(stat -f '%Lp' "$SOURCE_ROOT/current-operational-hold-dispositions.json")" = 600
test "$(shasum -a 256 "$SOURCE_ROOT/current-overlay-merge-packet.json" | awk '{print $1}')" = ce9d4ea1e048a70b7a8a5b85fab33fd1a0568eb5cb1356229187144ab8bc7558
test "$(shasum -a 256 "$SOURCE_ROOT/current-operational-hold-dispositions.json" | awk '{print $1}')" = c13cb0b565d2b86d34365f12d565f37f0e7ba6ec6bfa0d65de7f4a81ee088324
ENVIRONMENT=test PYTHONPATH=backend python -c 'from pathlib import Path; from app.operational_migration.hcp_current_overlay import CurrentOverlayManifest; p=Path("/Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-admission-packet-20260912T170000Z/current-overlay-merge-packet.json"); m=CurrentOverlayManifest.load(p); assert m.digest == "e23b7bcf5ac34ea650184afacc711af0c7028e83a6b1f7405e2ae17e13441eb2"'
```

### HCP historical safe-tranche builder

Update the packet authority from `9096a777...` to `7cdfb183...` and state that
the executor and post-admission acceptance are protected through PR #253 at
`96d67cb73dbe4838e882e1551de5906eda598f4e`. Run:

```bash
ENVIRONMENT=test PYTHONPATH=backend python -m pytest -q \
  backend/tests/operational_migration/test_hcp_historical_safe_tranche.py
python -m compileall -q \
  backend/app/operational_migration/hcp_historical_safe_tranche.py \
  backend/scripts/hcp_historical_safe_tranche.py
```

The builder is read-only with respect to application data, but writes the
explicit `--output` artifact. It must not be treated as admission authority.

Composition was revalidated on 2026-09-14 at tree
`72a4cd1b0c5c5f5f735591945559f9944c44c6aa`; lane qualification on 2026-09-12
passed all three focused tests and Python compilation. The tests cover accepted-record selection,
HOLD treatment for unbound updates, `execution_allowed = false`, acceptance-plan
digest tampering, and conflicting cross-scope native bindings.

### ECO

Update the current integration-watch authority from `52dc3367...` to
the protected authority produced by the lineage integration. The existing ECO
candidate independently declares Alembic revision `g7i9k1m3o5q7` from
`f6h8j0l2n4p6`; that identity is now reserved by the lineage candidate. Before
opening ECO's PR, merge the new protected authority, rename ECO's migration file
and internal `revision` to a new unique ID, set `down_revision` to the protected
lineage head, and update every ECO packet/test reference.

Prior isolated ECO qualification passed:

- PostgreSQL zero-to-head and current-head checks;
- its then-isolated `g7i9k1m3o5q7` revision from `f6h8j0l2n4p6`;
- no Alembic autogenerate drift;
- 252 Business Economics tests;
- clean Python compilation for the affected application, migration, and tests.

That database evidence is superseded for integration purposes by the collision
and must be rerun after revision reconciliation.

The repository does not configure a Ruff, mypy, Flake8, or backend
`pyproject.toml` gate; clean compilation must not be represented as coverage by
those tools.

Reproduce the database evidence against an empty disposable PostgreSQL
database. Never point this sequence at Preview or Production.

```bash
test -n "$QUALIFICATION_DATABASE_URL"
test -n "$EXPECTED_ECO_REVISION"
test -n "$ECO_MIGRATION_FILE"
cd backend
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic upgrade head
test "$(ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic current | awk 'NR == 1 {print $1}')" = "$EXPECTED_ECO_REVISION"
test "$(ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic heads | awk 'NR == 1 {print $1}')" = "$EXPECTED_ECO_REVISION"
test "$(ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic heads | wc -l | tr -d ' ')" = 1
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic check
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" pytest -q tests/business_economics
python -m compileall -q app/business_economics \
  "$ECO_MIGRATION_FILE"
```

Require exactly one head/current revision equal to the newly assigned ECO
revision and no new upgrade operations from `alembic check`.

### PR #215

Run the three affected Vitest suites plus frontend lint, typecheck/build. Confirm
the eight-file effective delta contains no OAuth connect/disconnect mutation and
continues to report `mutation_authority: none`. GitHub reports no checks on the
candidate branch, so Enterprise must require and record these results before
integration.

Composition was revalidated on 2026-09-14 at tree
`0c85fa8fea4302f432986d0f3cc1a356dffaa0f0`; lane qualification on 2026-09-12
passed three suites and nine tests, followed by clean full ESLint and production
TypeScript/Vite builds. This evidence does not replace Enterprise's final rerun
after branch reconciliation.

```bash
cd frontend
npm run test:run -- \
  src/api/qboAccountingEvidence.test.ts \
  src/components/accounting/QboSourceEvidence.test.tsx \
  src/routes/PayrollRoute.test.tsx
npm run lint
npm run build
```

### Mobile

Refresh protected authority and reconciliation commit in:

- `MOBILE.APPLE.RELEASE.INTEGRATION.PREFLIGHT.1.json`
- `MOBILE.DISTRIBUTION.PACKAGE.COMPLETION.1.integration.json`

Retain the 138-test qualification count. Run Mobile tests, typecheck, lint,
configuration validation, and Apple preflight. Signing/upload remains an owner
operation.

Composition was revalidated on 2026-09-14 at tree
`629471e756f243cb75ada33772e95f349e7ef4f6`; lane qualification on 2026-09-12
passed all 18 suites and 138 tests, followed by clean typecheck, lint, configuration
validation, and the non-mutating Apple distribution preflight. Jest emitted
React `VirtualizedList` updates-not-wrapped-in-`act(...)` warnings; these did not
fail the run but should remain visible in final qualification evidence.

```bash
cd mobile
npm test
npm run typecheck
npm run lint
npm run config:validate
npm run apple:preflight
```

Do not run `beta:aasa:verify`, `apple:release:qualify`, account-authenticated EAS
commands, signing, or upload during pre-integration qualification.

## Enterprise PR handoff

Run this only after a lane's reconciliation, metadata edits, tests, and
`git diff --check` pass. It pushes the candidate lane, never the protected
branch. `PR_TITLE` and `PR_BODY` must describe the effective delta, exact test
results, warnings, owner gates, rollback, and acceptance steps.

```bash
set -euo pipefail
test "$(git branch --show-current)" = "$lane"
candidate_head=$(git rev-parse HEAD)
test -n "$PR_TITLE"
test -f "$PR_BODY"
git push origin "HEAD:refs/heads/$lane"
remote_head=$(git ls-remote --heads origin "refs/heads/$lane" | cut -f1)
test "$remote_head" = "$candidate_head"

pr_number=$(gh pr list --repo ACPEnterprise/ACP-Enterprise \
  --state open --base customer-management-v1 --head "$lane" \
  --json number --jq '.[0].number // empty')
if test -z "$pr_number"; then
  gh pr create --repo ACPEnterprise/ACP-Enterprise \
    --base customer-management-v1 --head "$lane" \
    --title "$PR_TITLE" --body-file "$PR_BODY"
  pr_number=$(gh pr list --repo ACPEnterprise/ACP-Enterprise \
    --state open --base customer-management-v1 --head "$lane" \
    --json number --jq '.[0].number')
else
  gh pr edit "$pr_number" --repo ACPEnterprise/ACP-Enterprise \
    --title "$PR_TITLE" --body-file "$PR_BODY"
fi

gh pr view "$pr_number" --repo ACPEnterprise/ACP-Enterprise \
  --json baseRefName,headRefName,headRefOid,isDraft,mergeable,mergeStateStatus | \
  jq -e --arg lane "$lane" --arg head "$candidate_head" \
    '.baseRefName == "customer-management-v1" and .headRefName == $lane and .headRefOid == $head and .isDraft == false and .mergeable == "MERGEABLE" and .mergeStateStatus == "CLEAN"'
```

If GitHub initially reports `UNKNOWN`, wait for mergeability computation and
rerun only the final `gh pr view` check. Empty GitHub checks are not a pass:
attach the required local qualification log because ruleset `21781922` does not
require status checks or approvals. Send the new PR number and candidate head
back through this queue refresh before Enterprise integrates it.

## Held candidate

Price Book branch `work/pricebook-allcounty-review-readiness-1` at
`49e852aa8c931c8042de0634b68d993b0e02452e` is 7 behind / 13 ahead, has no PR,
and composes merge-clean at tree
`15afca73c3dada1417d0c1349ecff629245ab937`. It is stale and Git-reconcilable,
but not qualification-admissible. It supersedes the smaller `c1c90a0a...`
candidate and remains held for:

1. savepoint-based test isolation;
2. fail-closed `effective_catalog` multiple-match handling;
3. review-route authorization matrix coverage.

Composition was revalidated on 2026-09-14 at tree
`15afca73c3dada1417d0c1349ecff629245ab937`; PostgreSQL qualification on
2026-09-12 produced 26 passing tests and one failure. In
`test_operator_catalog_and_optimistic_metadata_management`, the expected stale
tax conflict deassociated the enclosing fixture transaction and removed the
seeded category; the following category update raised `PriceBookNotFound`.
The run also emitted ten SQLAlchemy transaction-deassociation warnings. This is
the deterministic isolation blocker and is not an intermittent failure.

The frontend portion of that exact composition is independently green: all five
focused suites and 14 tests passed, followed by clean full ESLint and production
TypeScript/Vite builds. The hold is therefore specifically the backend isolation
defect plus the unclosed ambiguity and authorization-coverage requirements; it
is not a general UI qualification failure.

## Secrets and owner gates

- Preserve the QBO OAuth owner gate; no active candidate requires new OAuth.
- No active candidate rotates secrets.
- Preview fixture defaults disabled. Authorized use requires Preview environment,
  `PREVIEW_ACCEPTANCE_FIXTURE_ENABLED=true`, an access token read from stdin,
  and `COMPANY_ADMINISTER` plus `IDENTITY_ONBOARDING_MANAGE`.
- Persona tokens and attestations must exist only under the contract's `0700`
  run directory as `0600` files. Pass token-file references, never token values,
  to the acceptance tooling; revoke the bounded sessions after the run.
- Fixture creation/reuse is audited. Do not invoke internal `record_reset`.
- Migration generation/admission, Payroll execution, and Apple distribution stay
  separately owner-authorized.

## Post-deployment acceptance

1. Set `EXPECTED_PROTECTED_SHA` to the integrated protected tip and run the
   command below. Do not begin lane acceptance until it passes.

   ```bash
   EXPECTED_PROTECTED_SHA="REPLACE_WITH_FULL_INTEGRATED_PROTECTED_SHA"
   curl --fail --silent --show-error \
     https://preview.allcountyhomeservices.com/backend-health | \
     jq -e --arg sha "$EXPECTED_PROTECTED_SHA" \
       '.status == "healthy" and .environment == "preview" and .database == "connected" and .redis == "connected" and .version == $sha'
   ```

2. Enterprise/operator: enable the Preview-only fixture flag, create or reuse the
   exact synthetic Company/Branch, provision CSR, EMPLOYEE, OFFICE, and QBO_READ
   identities with the contract's exact permissions, and seal one attestation per
   persona to the deployed SHA, Alembic head, frontend digest, expiry, and empty
   default mutation allowlist. Run `authenticated_preview_acceptance.py` using
   token-file and attestation-file references. Revoke all sessions after evidence
   capture. CSR scheduling mutation requires a separately sealed allowlist entry;
   all other personas remain GET-only.
3. Scheduling: reproduce JOB-000306 and verify authoritative mutation recovery.
4. Customer: exercise search, multiple Locations, Job/Appointment/Invoice return
   paths, open/history separation, source limitations, retry, and phone width.
5. Employee/Identity: verify Payroll Setup navigation, authorization failure,
   conflict-without-mutation, and actual password recovery delivery/reset.
6. ECO: verify migration head, then create/read/update governed policy behavior
   and immutable event audit evidence.
7. QBO: validate read evidence without OAuth or provider mutation.
8. Mobile: run distribution readiness; do not sign or upload without owner action.
9. Migration: validate recovered artifacts and builder output; do not execute
   guarded admission without separate authority.

### Acceptance evidence and rejection rules

Create one immutable acceptance record per deployed batch. Bind it to the
candidate head, integrated PR, protected merge SHA, deployed SHA, environment,
UTC start/end time, qualification-log location, sanitized correlation/audit
identifiers, observer, and `ACCEPTED` or `REJECTED` decision. The integrated and
deployed SHAs must be identical. Never record access tokens, passwords, recovery
links, Payroll values, provider payloads, Apple credentials, or Customer PII.

| Lane | Minimum acceptance evidence | Reject and stop on |
|---|---|---|
| OM2-C persona harness | Contract SHA; deployed release/schema/frontend bindings; exact Company/Branch; persona permission digests; token/attestation file modes and expiry; sanitized audit/session revocation references | Any production target, raw credential exposure, identity or permission mismatch, stale binding, expired attestation, unauthorized mutation route, or session left active |
| Scheduling | JOB-000306 before/after state; authoritative mutation outcome; repeated-idempotency result; Appointment count | Failure/unknown outcome, duplicate Appointment, changed arrival window, or non-idempotent retry |
| Customer | Search and selected Customer IDs; Location count; Job/Appointment/Invoice return paths; open/history state; phone-width capture | Missing/foreign data, wrong source limitation, stale retry failure, or unusable phone layout |
| Employee / Identity | Tested role and Branch; Payroll Setup route result; direct authorization denial; conflict-without-mutation result; delivery/reset audit IDs | Privilege expansion, cross-Branch visibility, mutation on conflict, delivery ambiguity, or reusable/expired reset success |
| ECO | Alembic current/head output; governed policy create/read/update correlation IDs; immutable event IDs and ordering | Wrong/multiple head, drift, mutable/missing audit event, cross-Company visibility, or unexplained calculation variance |
| PR #215 / QBO | Payroll evidence projection and QBO source-evidence response; role-negative result; before/after provider connection state | OAuth prompt/change, provider write, fabricated readiness, unauthorized financial visibility, or `mutation_authority` other than `none` |
| Mobile | App/config version; Preview API target; permission-derived navigation; Job Clock recovery; offline/stale behavior; unsigned preflight result | Production target, stale authority enabling mutation, cross-Branch cache visibility, duplicate clock mutation, or any signing/upload attempt |
| Migration lineage | Exactly one schema head; v2 authority SHA/file mode; SOURCE.4 package identity; 503 assertions; 1,389 canonical holds; deterministic master/child IDs; `completed_current_operational`; receipt/replay and rollback evidence | Duplicate/multiple revision, changed hold/scope/digest, canonical admission enabled, lineage conflict, partial rows/native graph, non-idempotent replay, missing backup/restore receipt, or execution without separate owner authority |
| Migration preparation | Both input SHA-256 values; manifest digest and record count; hold counts; builder output SHA-256 and `execution_allowed` value | Digest/count mismatch, weakened HOLD, global blocker, `execution_allowed = true`, or any admission/executor invocation |

Any rejection freezes that lane, preserves logs and immutable audit evidence,
and invokes the applicable rollback below. It does not authorize destructive
cleanup. Continue preparing other independent lanes after refreshing protected
authority and recomputing their compositions.

## Rollback

- #257-#263, PR #215, and Mobile have no application-state rollback. Rebuild the previous
  approved application image and retain evidence.
- Disable the Preview fixture flag rather than deleting its tenant or audit data.
- ECO application rollback should retain its additive migration under the
  post-reconciliation unique revision. Its downgrade drops the immutable event
  table and requires database-owner review, verified backup/restore, and
  preserved event evidence.
- Lineage rollback requires database-owner review. Do not narrow the status
  column or restore its old check constraint while any
  `completed_current_operational` row exists; preserve master/child, receipt,
  provenance, Business Event, backup, and restore evidence.
- Migration tooling rollback must retain recovered and generated immutable
  artifacts.

## Superseded open PRs

Close, do not integrate: #255, #252, #249, #248, #247, #246, #245, #244,
#240, #239, #238, #234, #233, #232, #230, #228, #227, #226, #225, #198,
#132, #97, and #65. Their product changes are zero-delta, patch-equivalent, or
represented by protected successor waves. PR #215 is intentionally retained.
