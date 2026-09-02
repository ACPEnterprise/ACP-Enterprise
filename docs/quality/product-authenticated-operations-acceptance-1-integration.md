# Product Authenticated Operations Acceptance 1

## Authority and isolation

- Program: `PRODUCT.AUTHENTICATED.OPERATIONS.ACCEPTANCE.1`.
- Branch: `work/om2b-authenticated-operations-acceptance-1`.
- Isolated worktree: `~/Development/ACP-Enterprise-OM2B-current`.
- Starting protected authority: `428dcbddd7d072b5b8d9edff489efcd4373960b5`.
- Schema head: `m9n7q05f2s8t`.
- Execution boundary: isolated local non-production PostgreSQL and sanctioned
  synthetic fixtures only.
- Preview and Production were not contacted, deployed, migrated, or mutated.
  No real Customer, Employee, communication, payment, Accounting posting,
  Payroll/tax execution, or protected migration source was used.

## Preserved recovery evidence

The original `~/Development/ACP-Enterprise` worktree remains preservation
evidence and was not used for implementation. Its recovered state was:

- branch `customer-management-v1` at
  `303548a7ecba9bc8b5a788237cc3a81a233c0d48`;
- interrupted cherry-pick
  `01b4dcb3c7aece8e4a0f222ecc8c71d3a1aa153e`, parent
  `a86daa79bd5700f028849546a12fa867a05f5fd7`, authored by `michael fouse`
  at `2026-09-01 12:08:04 -0400`, subject
  `feat(assets): establish operational asset identity authority`;
- status fingerprint
  `d2cdafba84432e769d03c4400455bc70003798b2ed3e21b7b14983f68a91362a`;
- index fingerprint
  `a0d9f23d333c517d5e9ca8897149b7d8e99c72d1c529ce020500bd483dfdc6f2`;
- combined staged/unstaged binary-diff fingerprint
  `13a5bcfc95c9d9e6ccdf8840544bfa4095e8510d375ebdf51aa7444331959229`;
- untracked-list fingerprint
  `226a468cfde0dce7785dcad78c8e7b6191348928c948f299c3f26f3ce19423f6`.

Conflicted paths:

- `backend/app/events/types.py`
- `backend/app/main.py`
- `backend/app/platform/idempotency/mutation-coverage.v1.json`
- `backend/app/platform/permissions/codes.py`
- `backend/tests/platform/test_api_idempotency_standard.py`
- `frontend/src/layout/navigation.ts`
- `frontend/src/layout/types.ts`
- `frontend/src/routing/routeMetadata.ts`
- `frontend/src/routing/router.tsx`

Staged paths additionally include the Assets migration, operational-assets
backend, tests, frontend API/hooks/route/types, permission catalog, Alembic
registration, and Assets integration packet. Unstaged paths additionally
include Inventory contracts, models, repository, and two Inventory test files.
Untracked paths are `.internal.swp`, the reservation/allocation/material-issue
migration, and its Inventory test. This inventory is ownership metadata only;
no protected file content was copied into this program.

## Acceptance execution

The versioned evidence is
`docs/quality/product-authenticated-operations-acceptance-1-evidence.json`.
The existing deterministic operational-acceptance catalog was replayed against
a fresh database upgraded from zero to the current schema head. It executed 52
cross-product scenarios in 112.304 seconds: 48 passed, 4 gated, and 0 failed.

Personas exercised through sanctioned fixtures:

1. Company Administrator
2. Office Manager
3. Service CSR
4. Dispatcher
5. Technician
6. Restricted Employee

The operating-day path covered Customer intake and search, Jobs, Scheduling,
Dispatch, Employee readiness, Mobile/My Day server contracts, field arrival,
Communications intent and provider truth, Timekeeping, Assets/Fleet, Price Book,
Estimates, field completion, Invoicing, Payments, AR/AP, Inventory, Service
Agreements, Customer history, Owner Operations, Economics, Luminary, Beacon,
LIA, Audit, and Migration readiness.

The failure-day path covered stale Scheduling/Estimate/Invoice authority,
cancellation, backend event-staging rollback, response loss, exact replay,
ambiguous provider outcomes, permission/Branch/Membership revocation, rapid
concurrent actions, foreign-tenant and persona attacks, safe error projection,
and fail-closed dependency/source gates.

## Authenticated browser acceptance

The browser suite exercises session restoration with refresh-token rotation,
failed restoration purge, logout purge, one-time 401 refresh and retry,
unrecoverable 401 clearing, unauthenticated redirect, permission-gated routes,
direct-API-backed denial behavior, safe error surfaces, truthful empty and
partial states, stale-state recovery, retry controls, responsive table/card and
navigation presentations, keyboard Escape/focus restoration, accessible route
context, live-region announcements, and non-drag scheduling controls.

The complete frontend result is 214 suites / 355 tests passed. ESLint and the
strict TypeScript production build passed. The runtime dependency audit is
clean. Five transitive development-tool advisories were repaired with compatible
lockfile-only patch updates; the complete dependency audit is now clean.

Backend regression on a separate fresh database produced 2,533 passes, 7 skips,
and one dependency-gated failure in 257.43 seconds. The single failure is the
healthy-Redis half of the combined expired/revoked-refresh and rate-limit test:
this host has no supported Redis service, and the application correctly raised
its fail-closed unavailable classification. The acceptance catalog separately
classifies that dependency as blocked. MyPy passed across 702 source files.
Backend-wide Ruff reports 111 pre-existing formatting/import/style findings in
unrelated historical files; this program did not mass-format protected
authority. The program diff passes whitespace/error checking and contains no
Python production change.

## Privacy and authorization result

- Foreign Company/Branch/object identities remain concealed at direct API
  boundaries.
- Role navigation does not substitute for server permission checks.
- Reopened and restored sessions reauthorize permission, Branch, Membership,
  and version state.
- Error surfaces use bounded recovery classifications and do not reflect
  provider, SQL, path, credential, or synthetic canary details.
- Communications retain consent and logical-delivery truth without contacting a
  provider.
- Financial, Payroll, Accounting, source-migration, and protected-document
  authority stayed outside this program.

## Defects and disposition

No product-semantic P0/P1 defect was reproduced. One dependency hygiene defect
was repaired: vulnerable transitive development-tool versions in
`frontend/package-lock.json` were advanced within the existing dependency
ranges. Runtime dependencies were already clean; post-repair full audit, tests,
lint, and build are clean.

The four deliberate external gates remain:

- healthy supported Redis integration (`DEPENDENCY_BLOCKED`);
- real email/SMS delivery (`PASSED_WITH_EXTERNAL_GATE`);
- physical mobile-device execution (`PASSED_WITH_EXTERNAL_GATE`);
- protected QBO/HCP migration source (`SOURCE_REQUIRED`).

These gates do not authorize substituting local in-memory authority, contacting
real providers, using protected identities, or entering Preview/Production.

## Integration

Integrate the evidence packet, this integration packet, and the dependency-safe
lockfile repair from `work/om2b-authenticated-operations-acceptance-1` after the
recorded qualification remains green. Local bounded acceptance is exhausted;
external gates retain their existing owners.
