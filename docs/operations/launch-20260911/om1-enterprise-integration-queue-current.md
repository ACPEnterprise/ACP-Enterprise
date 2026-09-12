# OM1 Enterprise integration queue

Snapshot: 2026-09-12 17:15 America/New_York

## Authority and deployed state

- Protected authority: `91dae4a52084daef42048e21b7754742e5e5eba9`
- Protected tip: PR #260, Preview acceptance-fixture runtime wiring
- Deployed Preview: `52dc336766a67fc0c4698244b9894bab0fe65913`
- Preview health: application healthy; PostgreSQL and Redis connected
- Deployment gap: protected PRs #257, #258, #259, and #260
- GitHub CI evidence: no check runs or commit statuses are reported for the
  protected SHA. Local qualification does not substitute for the tests below.

## Protected integration policy

GitHub ruleset `21781922` is active for exactly
`refs/heads/customer-management-v1`. It blocks branch deletion and
non-fast-forward updates and requires changes to enter through a pull request.
It allows merge, squash, or rebase integration. It has no bypass actors, but it
requires zero approving reviews, no code-owner review, no last-push approval,
and no status checks. Enterprise must therefore enforce the qualification and
acceptance gates in this packet operationally; GitHub will not enforce them.

## Active candidates

| Candidate | Head | Behind/ahead | Effective tree | State |
|---|---|---:|---|---|
| SOURCE.4 artifact recovery | `a3cad3d389b9ed69300939d15c19e2d7b08da063` | 2/1 | `e4bcdfdc5898ec62f6166d164b43d9416054d2f5` | Merge-clean; documentation-only; PR required |
| HCP historical safe-tranche builder | `b32f99ff80f447bf8140b73380d19191ccb8db59` | 12/1 | `9371c6ab231ae05a1feb2f3f38f3a90d8880145d` | Merge-clean; authority metadata stale |
| ECO reconciliation | `1c0e7b20db62b6a342548f2842ea1a3a45965386` | 4/13 | `657821646f4fcfc3eda071fa2b285b3903f5dbbd` | Merge-clean; qualified; authority metadata stale |
| PR #215 Payroll/QBO read UI | `724398348b566f655d2bc7127c20beeb6be52d6c` | 23/1 | `c964c398836e12ec16d398fbc81c246b66fec189` | Open/CLEAN; reconcile and refresh packet |
| Mobile Apple release packet | `0183eaec3e2825a79b683e9e684a761243c86ea7` | 9/15 | `fad3ab879576b7bfb392c8e30e68ed6df63e2425` | Merge-clean; refresh two manifests |

All five effective deltas have zero pairwise file overlap and produce identical
trees in either integration order. The combined pre-metadata tree is
`7fe61501fb00d3d578d5b9eadec92d9eb412e5f1`; it changes 59 files and passes
`git diff --check`. Recompute all trees after protected movement or packet edits.

## Integration order and release waves

There is no Git-level dependency between active candidates. Prefer this
operational order:

1. SOURCE.4 artifact recovery, then safe-tranche builder (Wave C tooling).
2. ECO as its own database checkpoint.
3. PR #215 in Wave B if QBO read-evidence acceptance is scheduled.
4. Mobile in Wave D; authoritative Job Clock `d52d1178` is already protected.

Do not execute Migration admission, authorize QBO, execute Payroll, or sign or
upload an Apple build as part of integration.

## Required reconciliation and qualification

### SOURCE.4 artifact recovery

Merge current protected authority into
`work/migration-source4-accepted-artifact-recovery-1`, require tree
`e4bcdfdc5898ec62f6166d164b43d9416054d2f5`, run `git diff --check`, push the
lane branch, and open a documentation PR. The packet contains no protected SHA
that needs editing.

### HCP historical safe-tranche builder

Update the packet authority from `9096a777...` to `91dae4a5...` and state that
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

### ECO

Update the current integration-watch authority from `52dc3367...` to
`91dae4a5...`. Current composition qualification has passed:

- PostgreSQL zero-to-head and current-head checks;
- Alembic head `g7i9k1m3o5q7`, down revision `f6h8j0l2n4p6`;
- no Alembic autogenerate drift;
- 252 Business Economics tests.

### PR #215

Run the three affected Vitest suites plus frontend lint, typecheck/build. Confirm
the eight-file effective delta contains no OAuth connect/disconnect mutation and
continues to report `mutation_authority: none`. GitHub reports no checks on the
candidate branch, so Enterprise must require and record these results before
integration.

### Mobile

Refresh protected authority and reconciliation commit in:

- `MOBILE.APPLE.RELEASE.INTEGRATION.PREFLIGHT.1.json`
- `MOBILE.DISTRIBUTION.PACKAGE.COMPLETION.1.integration.json`

Retain the 138-test qualification count. Run Mobile tests, typecheck, lint,
configuration validation, and Apple preflight. Signing/upload remains an owner
operation.

## Held candidate

Price Book `49e852aa8c931c8042de0634b68d993b0e02452e` supersedes the smaller
`c1c90a0a...` candidate but remains held for:

1. savepoint-based test isolation;
2. fail-closed `effective_catalog` multiple-match handling;
3. review-route authorization matrix coverage.

## Secrets and owner gates

- Preserve the QBO OAuth owner gate; no active candidate requires new OAuth.
- No active candidate rotates secrets.
- Preview fixture defaults disabled. Authorized use requires Preview environment,
  `PREVIEW_ACCEPTANCE_FIXTURE_ENABLED=true`, an access token read from stdin,
  and `COMPANY_ADMINISTER` plus `IDENTITY_ONBOARDING_MANAGE`.
- Fixture creation/reuse is audited. Do not invoke internal `record_reset`.
- Migration generation/admission, Payroll execution, and Apple distribution stay
  separately owner-authorized.

## Post-deployment acceptance

1. Require `/backend-health` to report the deployed protected SHA and connected
   PostgreSQL/Redis.
2. Scheduling: reproduce JOB-000306 and verify authoritative mutation recovery.
3. Customer: exercise search, multiple Locations, Job/Appointment/Invoice return
   paths, open/history separation, source limitations, retry, and phone width.
4. Employee/Identity: verify Payroll Setup navigation, authorization failure,
   conflict-without-mutation, and actual password recovery delivery/reset.
5. ECO: verify migration head, then create/read/update governed policy behavior
   and immutable event audit evidence.
6. QBO: validate read evidence without OAuth or provider mutation.
7. Mobile: run distribution readiness; do not sign or upload without owner action.
8. Migration: validate recovered artifacts and builder output; do not execute
   guarded admission without separate authority.

## Rollback

- #257-#260, PR #215, and Mobile have no schema rollback. Rebuild the previous
  approved application image and retain evidence.
- Disable the Preview fixture flag rather than deleting its tenant or audit data.
- ECO application rollback should retain additive migration `g7i9k1m3o5q7`.
  Its downgrade drops the immutable event table and requires database-owner
  review, verified backup/restore, and preserved event evidence.
- Migration tooling rollback must retain recovered and generated immutable
  artifacts.

## Superseded open PRs

Close, do not integrate: #255, #252, #249, #248, #247, #246, #245, #244,
#240, #239, #238, #234, #233, #232, #230, #228, #227, #226, #225, #198,
#132, #97, and #65. Their product changes are zero-delta, patch-equivalent, or
represented by protected successor waves. PR #215 is intentionally retained.
