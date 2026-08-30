# OM2-C Enterprise qualification evidence — 2026-08-30

## Authority and scope

- Starting protected authority: `72f969bac74a0bf4c741bdc98133b5c23f18d91e` (`origin/customer-management-v1`).
- Reconciled protected authority: `1fac637462b01869cc7962d7463af1dc12637a43`.
- Qualification branch: `work/om2c-quality-security-program-1`.
- The supplied OM2-A and OM2-B SHAs are not ancestors of starting authority. Their named remote branches were absent after `git fetch --prune`; no integration claim is made.
- This is non-production evidence. It is not Production release approval.

## Risk-weighted coverage map

| Domain | Current evidence | Highest-priority gap / limitation |
| --- | --- | --- |
| Platform / Auth / AuthZ | Strong unit, API, persistence, isolation, idempotency, provider reliability, security-output, header and permission-matrix suites (23 files) | Redis-backed authentication qualification requires an integrated Redis runtime; broad DB fixtures are not self-cleaning |
| Customers | Strong service/API/search/lifecycle/normalization coverage (10 files) | Cross-domain Customer→Location→Job object-binding rehearsal remains integration-level |
| Estimates | Pricing, workflow, conversion, normalized conversion replay, exactly-one Job/event replay, and list API coverage (5 files) | Deterministic multi-connection acceptance/conversion stress is blocked by the transaction-bound shared-connection fixture and remains a dedicated-suite gap |
| Jobs | API, permission, persistence, query and lifecycle service coverage (5 files) | Cross-branch lifecycle concurrency needs an explicit stress tranche |
| Scheduling / Dispatch | API, persistence and service coverage (5 files combined) | Assignment/reschedule race and large projection performance baselines are limited |
| Field Service | Contract, conformance and migration coverage (3 files) | Provider/storage failure composition is integration-only |
| Inventory / Purchasing | Foundation, adjustments, reservations, cycle counts, purchasing policy, replenishment, three-way match, current-authority replay enforcement, and deterministic concurrent replay coverage for movements/reservations/adjustments/cycle counts | Receipt and three-way-match concurrent-winner stress remains incomplete at current authority |
| Price Book | API and service coverage (2 files) | Scale/search and cross-tenant nested-ID abuse need expansion |
| Invoicing / Payments / AP | Contract, provider, AR and invariant coverage (7 files) | Response-lost-after-commit and cross-domain double-count rehearsal need broader end-to-end evidence |
| Accounting | Posting, API, contract and migration coverage (9 files including contract suites) | Full synthetic AR/AP/Payroll settlement balance rehearsal remains integration-level |
| Payroll | Strong policy, calculation, approval/finalization, payment, remittance, reporting and protected artifact coverage (23 files) | Redis/storage integrated failure injection and payment-provider restart replay remain pending |
| Migration | Extensive Customer and operational migration evidence (46 files) | Protected external source/storage rehearsal remains environment-dependent; no real provider contacted |
| Business Economics | Policy, admission, allocation, profitability, source-conformance, owner-workspace and explicit Company/Branch persistence enforcement | Cross-source economic double-counting still needs a consolidated rehearsal |
| Beacon | Evaluation, lifecycle, workflow, prioritization and acknowledgement coverage (16 files) | Read-only versus operational mutation matrix should be expanded at API level |
| Mobile-facing APIs | Backend employee/engineering APIs and separate mobile Jest suite exist | Native mobile was not changed in this tranche; integrated device accessibility remains external |
| Administration / frontend | Route/component tests cover authorization and representative loading/error states | Automated accessibility tooling and responsive viewport regression are not comprehensive |

## Qualification results

- Frontend after authority reconciliation and repairs: 88 test files / 263 tests passed; ESLint passed; TypeScript and production Vite build passed.
- Backend focused security tranche: isolation, authorization composition, idempotency, provider uncertainty and safe-output tests passed after repairing a stale catalog fingerprint.
- Backend broad run: 2,109 passed, 7 skipped, 12 failed. Classification: 10 `TEST_ISOLATION` failures caused by reusing a database containing focused-test fixtures (all 10 passed on a fresh schema); 1 `ENVIRONMENT` Redis test (failed closed because `redis` hostname/runtime was unavailable); 1 `STALE_FIXTURE` external-adoption test repaired and requalified.
- Static: Python 3.12 compilation passed; MyPy passed across 621 source files. Repository-wide Ruff is not a clean gate at starting authority (246 findings, predominantly pre-existing import-order findings); no mass formatting was performed.
- Database: PostgreSQL 16.15 fresh upgrade passed, followed by successful authority-advance upgrade; exactly one Alembic head `b0ff279c5aeb`; `current=head`; `alembic check` reports no drift.
- Secret scan: only intentional synthetic canary tests matched the high-confidence token/private-key patterns; no discovered secret value was emitted.

## Defects and repairs

1. `STALE_FIXTURE`: sensitive-output catalog expansion changed the deterministic fingerprint without updating its qualification assertion. The assertion now binds the expanded catalog.
2. `STALE_FIXTURE`: external-adoption successor evidence did not satisfy newly integrated execution-head and repository-readiness admission. The test now supplies matching authoritative-head evidence and isolates the orthogonal readiness adapter with an explicit mock.
3. `DEPENDENCY`: direct `react-router` 7.18.1 fell within the lockfile audit's affected CSRF-bypass range. It was advanced only to the patched 7.18.3 line. Remaining audit findings are transitive and require separate applicability/upgrade qualification.
4. `AUTHORIZATION/DURABLE_INTEGRITY`: Economics execution checked Company identity but accepted a result tagged to a different or nonexistent Branch, and the durable result table lacked a Company+Branch foreign key. Persistence now rejects active-branch escape and nonexistent Company branches before mutation; migration `c1a0e38d6bfc` enforces the same invariant in PostgreSQL. All 140 Business Economics tests pass, and the new migration passed fresh upgrade, downgrade/re-upgrade, current-head, and drift qualification.
5. `FRONTEND_AUTHORIZATION/RECOVERY`: the Economics route initiated its protected workspace request even when the current user lacked read authority, and its temporary-unavailable state had no recovery action. The query is now disabled unless read permission is present, and the safe error state exposes a tested retry without rendering backend details.
6. `OBJECT_AUTHORIZATION/IDEMPOTENCY`: Purchasing resolved PO-scoped durable receipts before checking the caller's current Branch authority. Possession of an exact key and request could therefore replay a Branch A PO mutation result to a same-Company caller restricted to Branch B. The shared Purchasing replay boundary now reauthorizes the parent PO before receipt lookup for update, line, lifecycle, receipt, discrepancy, return, disposition, and change operations. The adversarial cross-branch replay fails closed, and 76 Purchasing/Procurement/Inventory tests pass.
7. `CONCURRENCY/IDEMPOTENCY`: Inventory movement, reservation, adjustment, cycle-session and cycle-entry creation used read-before-insert replay checks without serializing same-key transactions. Concurrent exact replay could expose raw unique-constraint failures, and adjustment replay could create a movement before losing the adjustment race. Each Company+operation+normalized-key now takes a transaction-scoped PostgreSQL advisory lock before authoritative lookup. Deterministic two-transaction tests prove one returned identity and one durable record; all 28 Inventory tests, focused Ruff, MyPy, and diff checks pass.
8. `CONCURRENCY/IDEMPOTENCY`: The shared Purchasing replay boundary performed a read-before-insert lookup without serializing Company+key. PO mutations happened to gain protection from parent-row locks, but create-style commands could race into the command-receipt unique constraint; the Vendor test labeled concurrent only exercised sequential replay. The shared boundary now takes a transaction-scoped PostgreSQL advisory lock after any required current-authority check and before receipt lookup. True concurrent Vendor replay returns one authority, competing receipt commands retain one typed winner, and 80 Purchasing/procurement-matching/Inventory tests pass.
9. `IDEMPOTENCY`: Estimate conversion validated and persisted a trimmed idempotency key but compared replay evidence to the untrimmed request. A whitespace-bearing key therefore succeeded once and falsely conflicted on exact replay. Conversion now normalizes once before validation, comparison, and persistence; replay produces one Job, one conversion, and one Business Event. All 32 Estimate tests pass. The existing Estimate fixture binds sessions to one transaction-scoped AsyncConnection, so it cannot truthfully execute concurrent driver operations; multi-connection stress remains an explicit qualification gap.

## Release-readiness projection

- Release SHA: starting authority above plus the OM2-C qualification commit recorded on this branch.
- Schema head: OM2-C candidate `c1a0e38d6bfc` over protected `b0ff279c5aeb`; fresh-upgrade, downgrade/re-upgrade and drift clean.
- Backend: broad functional coverage is high, but the integrated Redis test and a clean one-pass fresh-database rerun remain external gates.
- Frontend: tests/lint/build qualified again after the bounded dependency repair.
- Security: focused authorization/isolation/idempotency/safe-output suite qualified; dependency transitive findings and expanded direct API object-binding remain open work.
- Known P0/P1 defects discovered in this tranche: none.
- Projection: **NON_PRODUCTION_CONDITIONALLY_QUALIFIED**. Enterprise retains deployment and release authority.

## Reproduction methodology

Host pressure was checked before heavyweight work. Tests used Python 3.12 and an isolated local PostgreSQL 16 database created only for OM2-C. The standard container hostname `postgres` was replaced through `DATABASE_URL`; no shared lane database was modified. Broad backend invocation required `ENVIRONMENT=test PYTHONPATH=.`. No Production load, provider calls, real journals, real payments, or real data were used.
