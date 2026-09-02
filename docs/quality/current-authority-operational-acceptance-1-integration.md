# CURRENT.AUTHORITY.OPERATIONAL.ACCEPTANCE.1 integration packet

## Authority and boundary

- Starting protected authority: `428dcbddd7d072b5b8d9edff489efcd4373960b5`.
- Final protected authority observed and reconciled:
  `fd2af4057a8dc1ba14777e3c052dd6ed39656404`.
- Qualification branch: `work/om2c-current-product-acceptance-1`.
- Product authority, merge authority, Preview deployment authority, and Production
  authority remain with Enterprise.
- All runtime evidence used synthetic identities and an isolated loopback
  PostgreSQL database. No real Customer, Employee, communication, payment,
  Accounting posting, Payroll/Tax execution, Preview mutation, or Production
  access occurred.
- Price Book was inspected only at its integration/readiness boundary. This lane
  did not duplicate All County catalog construction.

## Recovery preservation

The historical `~/Development/ACP-Enterprise` checkout remains preserved as
recovery evidence at local `customer-management-v1` commit
`303548a7ecba9bc8b5a788237cc3a81a233c0d48`, with interrupted cherry-pick
`01b4dcb3c7aece8e4a0f222ecc8c71d3a1aa153e`. Its recovery status fingerprint
remained `d2cdafba84432e769d03c4400455bc70003798b2ed3e21b7b14983f68a91362a`
through this program. No conflict, index, worktree, or operation state there was
changed.

## Launch-readiness findings

### HCP partial-data resilience

Current contracts preserve missing relationships, missing timestamps, competing
source assertions, unresolved technician identities, canceled history, and
partial source provenance as explicit unavailable, partial, rejected, held, or
reconciliation-required evidence. They do not promote names or source numbers
to native identity and do not coerce missing financial evidence to zero.
Scheduling admission requires valid timing and parent identity; unsupported or
undated source rows remain evidence/gates rather than fabricated Appointments.

Representative qualified contracts include authoritative acquisition,
SOURCE.4 layouts and application, hybrid Customer projection, Appointment
sequence correction, open-work cutover, product projection, and Accounting
opening-state reconciliation.

Protected authority advanced during qualification with the HCP operational
measurement readiness tranche. The isolated branch merged that protected
authority without conflict. Its 16 focused tests, Ruff, MyPy, and Python
compilation pass, including explicit rejection of contradictory lifecycle
evidence. The measurement handoff remains evidence/readiness authority and does
not fabricate operational completion.

### Scheduling and Dispatch

The current Scheduling and Dispatch surfaces preserve separate read/manage
permissions, Branch scope, truthful empty/loading/error states, unassigned work,
unknown duration, missing availability, no-routing limitations, deterministic
proposal ranking, and explicit dispatcher approval. Dispatch Intelligence has
no mutation authority. Existing idempotency and concurrency tests bind one
authoritative assignment/schedule effect and safe stale-state conflicts.

### Price Book readiness

Read, manage, and activate authorities remain independent. Activation and
snapshot evidence are immutable, replay-safe, Company/Branch scoped, and
stale-version protected. Owner-facing command failures preserve entered
commercial evidence without reflecting backend details. Real All County content
configuration and the existing paged-read-model gate remain outside this lane.

### Migration and Accounting truth

Current source evidence retains the `850.00_SOURCE_VERSION_CONFLICT`; no amount
is forced to zero. Missing opening evidence, unresolved mapping policy,
Undeposited Funds control, bank/card gates, Inventory opening completeness, and
AP evidence remain explicit gates. An unavailable/blocked candidate is not
presented as complete or as a zero balance. The repository evidence still records
the 92 unresolved COA mappings as Migration authority, not native completion.

### Authorization, privacy, and recovery

Current backend coverage exercises foreign Company, Branch, Customer, Job, and
Employee scope; revoked and expired identities; stale authorization/version
state; missing permissions; direct API attempts; concealed cross-tenant objects;
and transaction rollback. HTTP and UI recovery contracts cover authentication,
authorization, validation, absence, conflict, unexpected failure, provider
unavailability, network uncertainty, stale state, and session expiry without
granting authority or assuming a mutation succeeded.

One current-head P2 privacy defect was found: the legacy frontend
`getApiErrorMessage` helper reflected raw string/validation response details and
was still used by Customer timeline, Customer communication history, and
Communications Administration. A synthetic 500/502/503 response could therefore
surface an internal path, traceback text, or provider detail. The helper now
uses the shared fixed operator-safe recovery contract. Shared and component-level
regressions prove protected canaries are absent for unexpected, network, 500,
502, and 503 failures.

### Cross-domain contracts

The qualified suite exercises the current Customer-to-Job,
Job-to-Scheduling, Scheduling-to-Dispatch, Dispatch-to-Mobile,
Job-to-Estimate, Estimate-to-Job/Invoice, Invoice-to-Payment evidence,
Price-Book-to-Estimate snapshot, Asset-to-Job, Workforce-to-Dispatch,
Migration-to-native projection, and Economics-to-Luminary/Beacon/LIA
boundaries. No autonomous communication, posting, payment, Payroll, or dispatch
mutation was introduced.

## Qualification evidence

- Backend broad suite, Python 3.12, `ENVIRONMENT=test`, isolated PostgreSQL:
  **2,533 passed, 7 skipped, 1 environment-gated failure**. The only failure is
  authentication rate-limit integration because no supported Redis runtime is
  installed or running; the application correctly raised
  `RateLimitUnavailableError` instead of bypassing enforcement.
- Post-reconciliation HCP operational-measurement delta: **16 tests passed**;
  focused Ruff, MyPy, and Python compilation passed.
- Frontend after repair: **108 files / 361 tests passed**; repository ESLint,
  TypeScript, and production Vite build passed.
- Mobile (unchanged by repair): **14 suites / 118 tests passed**; TypeScript and
  ESLint passed. One initial timeout occurred only under concurrent host load and
  passed both isolated and full serial reruns.
- Database: fresh PostgreSQL 16.15 zero-to-head upgrade passed; exactly one
  Alembic head/current revision `m9n7q05f2s8t`; `alembic check` reports no drift.
- Python: compilation passed; MyPy passed across **702 source files**.
- Ruff: no Python file changed in this program. Repository-wide baseline remains
  non-clean with 111 pre-existing findings, primarily import ordering; no mass
  formatting was performed.
- Diff and protected-data checks: `git diff --check` passed. High-confidence
  protected-data filename scan found only four intentional synthetic canary test
  files; no discovered value was emitted.
- Dependency review: frontend production dependency audit reported zero known
  advisories. Mobile reported 17 moderate Expo/React Navigation/transitive
  advisories, including no-fix and major-version-only paths; this remains the
  established Mobile dependency/Expo owner gate.

## Remaining gates

- P0: none found.
- P1: none found in current application behavior.
- Release gates: supported Redis integration; real-provider/Migration
  acquisition; physical-device acceptance; Mobile dependency/Expo remediation;
  owner authority for real Price Book, Assets/Workforce/Economics policy and
  partial-data disposition; Preview approval; Production approval.

## Classification

`NON_PRODUCTION_CONDITIONALLY_QUALIFIED`

The branch is locally exhausted for dependency-safe current-head P0/P1/P2
application defects within this mission. Enterprise must review and integrate
the bounded privacy repair before any deployment decision.
