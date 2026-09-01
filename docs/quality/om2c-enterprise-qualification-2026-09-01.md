# OM2-C Enterprise qualification evidence — 2026-09-01

## Authority, boundary, and classification

- Starting protected authority: `a86daa79bd5700f028849546a12fa867a05f5fd7`; final reconciled protected authority: `6ef1f10f4ed125feef3c2e27403908ce3a2027e8` (`origin/customer-management-v1`). The late bounded-QBO snapshot and deterministic-resume advances were merged without collision.
- Isolated worktree: `/Users/michaelfouse/Development/ACP-Enterprise-OM2C2`.
- Qualification branch: `work/om2c-quality-security-program-2`.
- Candidate schema head: `i5h3g51b8z4x`.
- Classification: **NON_PRODUCTION_CONDITIONALLY_QUALIFIED**. No P0/P1 product defect was found. Redis-backed authentication qualification, real-provider behavior, physical-device acceptance, active-owner semantic work, and Production release authority remain external gates.
- Preview, real-QBO evidence, real providers, real money/journals, and Production were untouched.

## Risk-weighted qualification inventory

| Domain | Status | Evidence / remaining gate |
| --- | --- | --- |
| Platform, Identity, AuthZ | QUALIFIED | Broad persistence, API, canonical-role, tenant, Branch, permission, idempotency, safe-output, readiness, and replay suites; Redis integration is EXTERNAL_GATE |
| Customers / CRM | QUALIFIED | Customer, Location, search, lifecycle, migration identity, Customer Context and LIA composition suites |
| Scheduling / Jobs / Dispatch / Field Service | QUALIFIED | API, lifecycle, assignment, replay, stale-winner, safe-failure, relationship and field evidence suites |
| Price Book / Estimates / Invoicing / Payments | QUALIFIED | Snapshot, revision, conversion, receivable, collection/refund, uncertainty, idempotency and balance suites; no provider contacted |
| Accounting / AP | QUALIFIED | Balance, posting, SOD, immutable authority, AP admission, settlement and replay suites; synthetic only |
| Purchasing / Inventory | QUALIFIED | PO, receipt, return, movement, count, transfer, reservation, three-way match and document custody suites |
| Service Agreements | QUALIFIED | Version, enrollment, entitlement, correction, renewal and replay suites |
| Workforce / Employee administration | ACTIVE_OWNER | Existing projection and authorization tests passed; OM2-B owns semantics |
| Timekeeping / Payroll | QUALIFIED | Punch, break, correction, immutable interval, calculation, approval, remittance, reporting, Pay Statement and own-data suites |
| Migration | PARTIAL | Extensive synthetic Customer/operational/HCP/QBO code suites passed; protected real acquisition remains EXTERNAL_GATE and untouched |
| Economics / Luminary | QUALIFIED | Admission, missing-evidence truth, immutable results, Branch lineage, briefing and safe-failure suites; ECO owns expansion semantics |
| Beacon / LIA | QUALIFIED | Signal lifecycle/replay and governed retrieval, injection/refusal, tenant, permission and Customer Context suites |
| Mobile contracts | QUALIFIED | 93 Jest tests, lint and TypeScript passed; physical device is EXTERNAL_GATE and Expo major upgrade is ACTIVE_OWNER |
| Communications / onboarding | QUALIFIED | Invitation, role readiness, owner claim, token destruction, Branch scope and delivery-truth suites |
| Assets / Fleet | ACTIVE_OWNER | OM2-A owns semantics; no competing changes made |
| Frontend / Administration | QUALIFIED | 104 files / 340 tests, ESLint, TypeScript and production Vite build passed |

## Regression, migration, and static evidence

- Final backend release run after authority reconciliation on freshly created PostgreSQL database `acp_om2c2_r4`: **2,375 passed, 7 skipped, 1 deselected** in 228.64 seconds. The sole deselection requires Redis and independently fails closed with `RateLimitUnavailableError` because the repository-standard `redis:6379` service is unavailable locally.
- The discovery run before repairs produced 2,372 passes, 7 skips, two failures and six teardown errors. Both actionable failures and all teardown errors were repaired. A deliberate second run on its already-populated database exposed 34 repeat-run fixture collisions; a third entirely fresh database passed, proving those collisions are test-isolation debt rather than product-authority failures.
- Frontend: **104 files / 340 tests passed**; repository ESLint passed; `tsc -b` and Vite production build passed.
- Mobile: **9 suites / 93 tests passed**; ESLint and `tsc --noEmit` passed.
- Alembic: exactly one head; three fresh zero-to-head upgrades completed; `current=head`; `alembic check` reported no drift. Published migration history was not rewritten.
- Python 3.12 compilation and `pip check` passed. Focused Ruff for every changed Python file passed; repository-wide Ruff retains 94 pre-existing findings and was not mass-formatted.
- Git diff whitespace validation passed.

## Adversarial program results

1. **Immutable authority / direct SQL:** current migrations protect immutable Migration cutover, Customer/Location source identity, Economics lineage, Luminary lineage, Timekeeping authority, Business Events and audit scope. Broad direct-constraint and history tests passed. No trigger was added to mutable configuration.
2. **Tenant and Branch isolation:** cross-Company/Branch suites across Platform, Customer, Jobs, Scheduling, Purchasing, Inventory, Payroll, Migration, Economics, Luminary, Beacon, LIA and onboarding passed. Foreign identities remain concealed or rejected before mutation.
3. **Authorization and own-data:** canonical personas, permission composition, canonical-role synchronization, authorization versioning, Membership state and employee self-resolution suites passed. UI visibility was qualified in the frontend suite; server authorization remains authoritative.
4. **Identity collision:** unique User/email, Employee, Membership, role, activation and tenant identity constraints passed. A globally fixed test Permission identity was made unique to preserve repeatability.
5. **Idempotency and response loss:** the OpenAPI audit now classifies all **265** POST/PUT/PATCH/DELETE operations. Canonical-role reconciliation is naturally idempotent; Workforce eligibility POST is explicitly read-only. Replay, changed-request, concurrent and after-commit suites passed across representative economic and operational mutations.
6. **Concurrency:** deterministic winner/replay suites passed for Customer, Appointment, Job, Estimate conversion, Invoice, Payment, Accounting, AP, Purchasing, Inventory, Payroll, Timekeeping, Service Agreements and Economics. No raw SQL/constraint error was observed on a clean run.
7. **Provider uncertainty and incomplete deployment:** synthetic accepted/rejected/transport/uncertain/reconciliation paths passed. Uncertain state never blindly retries. Mobile stale-state and Timekeeping retry contracts passed; no provider was called.
8. **Audit, log and API failure safety:** sensitive-output, event/audit scope, structured/plain log redaction, correlation, safe headers and recovery-envelope suites passed. Canonical-role reconciliation no longer reflects its internal exception; it returns fixed `resource_state_conflict` / `RETRY_AFTER_REFRESH` evidence.
9. **Readiness and degradation:** health/live/ready and dependency classification suites passed. Authentication rate limiting fails closed without Redis; integrated healthy-Redis execution remains pending rather than falsely passed.
10. **Domain integrity:** Timekeeping immutable intervals, Payroll boundaries, balanced Accounting journals, Payment distinction, procurement/Inventory quantity truth, Customer/CRM identity, Estimate stale revision, Service Agreement successor lineage, Economics non-double-counting, Luminary non-fabrication, Beacon lifecycle, LIA protected retrieval and synthetic Migration succession all passed in the broad run.
11. **QBO GET-only:** all 116 synthetic QBO tests passed after reconciling Enterprise's bounded accounting-snapshot and deterministic-resume authority; business writes remain rejected and environment roots/token access remain separated. No token value or protected source evidence was read.
12. **Artifacts and retention:** Pay Statement, Estimate, purchasing document and Migration artifact authorization/digest/path tests passed. No automatic destructive deletion was enabled; unconfigured retention defaults to preservation.
13. **Performance and query paths:** existing deterministic pagination, bounded-list and N+1 regression suites passed. The complete backend run was 231.38 seconds on the local non-production host with zero host-throttled pages; this is a gross regression baseline, not a Production SLO or load test.
14. **Responsive/accessibility/frontend recovery:** representative authorization, loading, empty, validation, stale, forbidden and safe error states passed automated component coverage. Physical viewport/device and comprehensive contrast acceptance remain external/manual gates.
15. **Business Events and correlation:** Company/Branch durable scope, replay staging, safe payload, consumer evidence and request-correlation propagation suites passed. Correlation remains distinct from authorization and idempotency.
16. **Synthetic owner day:** the broad suite covers the component workflows Customer→Estimate→Job→Invoice→Payment, Purchasing→Receipt→Inventory→AP, Timekeeping→Payroll→Accounting and Facts→Economics→Luminary/Beacon/LIA. It is component-composed synthetic evidence, not one Production-like external-provider rehearsal.

## Defects repaired in this tranche

1. `IDEMPOTENCY_REGISTRY_DRIFT`: classified the canonical-role reconciliation mutation and read-only Workforce eligibility POST; regenerated fingerprint `f5277548b18cafcbecf9d8a1a0e014c17884b83728909356817575e2cfac3f4d` and bound the 265-operation assertion.
2. `API_FAILURE_SAFETY`: replaced reflected canonical-role synchronization exception text with the standard fixed recovery envelope and added a protected-connection-string canary regression test.
3. `TEST_ISOLATION`: made Company Administration's synthetic Permission code unique.
4. `TEST_ARCHITECTURE`: packaged Accounting and Luminary test directories so duplicate `test_api_boundary.py` basenames cannot poison broad collection.
5. `TEST_ISOLATION / EVENT_INTEGRITY`: Jobs teardown now removes its own Business Events before tenant authority, respecting the protected Company/Branch FK.
6. `STALE_FIXTURE`: procurement vendor-performance evidence no longer uses a hard-coded evaluation date that moved behind newly created evidence on 2026-09-01.
7. `STATIC_QUALIFICATION`: mechanically corrected import ordering in Enterprise's newly integrated QBO snapshot-policy test; its 115-test synthetic boundary and final broad suite remain green.
8. `STATIC_QUALIFICATION`: mechanically corrected import ordering in Enterprise's late QBO deterministic-resume evidence test; the full 116-test synthetic QBO boundary passes.

## Dependency and secret security

- Backend requirement hashes were unchanged from the previously qualified environment; `pip check` reports no broken requirements. No uncontrolled upgrade was performed.
- Frontend runtime audit reports zero vulnerabilities. Four development-only transitive advisories remain in ESLint/minimatch, jsdom/undici, and Vite/postcss/nanoid dependency chains.
- Mobile runtime audit reports 24 advisories (15 moderate, 9 high); the full tree reports 25. Remediation primarily requires Expo 57 and related major-version movement or packages with no current automatic fix. This is an exact Mobile-owner handoff, not an OM2-C major upgrade.
- High-confidence tracked-file scanning found only four intentional synthetic canary test files. No secret value was printed or retained.

## Integration packet and exact gates

- Enterprise may integrate the coherent repair commit from `work/om2c-quality-security-program-2` after protected-branch review.
- Required external gates: supported Redis-backed authentication test; real-provider and protected Migration acquisition owned by Migration; physical-device acceptance owned by Mobile; Preview deployment owned by Enterprise; Production authorization remains prohibited.
- Active-owner gates: Assets/Fleet semantics (OM2-A), Workforce administration semantics (OM2-B), Economics/Luminary expansion (ECO), and Expo major upgrade/physical acceptance (Mobile).
- Quality debt, not a release-authority defect: broad DB suites are clean on a fresh database but are not globally repeatable on one populated database; 34 second-pass tests rely on fixed global fixtures or absolute table counts.
- Locally exhausted: **YES** for collision-free repository qualification available on this host. External and owner gates above remain.
