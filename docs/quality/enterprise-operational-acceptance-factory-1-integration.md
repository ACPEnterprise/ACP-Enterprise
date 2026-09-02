# Enterprise Operational Acceptance Factory 1

## Authority and classification

- Starting protected authority: `66d22691d09598312ab83d9560013c64b82ec6f3`.
- Candidate schema head: `k7l5n83d0q6r`.
- Branch: `work/enterprise-operational-acceptance-factory-1`.
- Classification: **NON_PRODUCTION_READY_WITH_EXTERNAL_GATES**.
- No Preview, Production, real Customer/Employee, real email/SMS, real payment, real QBO/HCP, Payroll/tax execution, Accounting posting, or source freeze was used.

## Acceptance harness

`backend/scripts/operational_acceptance_factory.py` is a reusable scenario orchestrator. Versioned scenarios bind persona, expected result, exact repository test nodes, authority SHA, schema head, actual classification, duration, and a SHA-256 digest of captured test output. Raw output is not retained in the packet. Executable scenarios use existing application/router/service contracts; explicit provider, source, device, Redis, and policy gates are recorded without pretending execution occurred.

The generated packet is `docs/quality/enterprise-operational-acceptance-factory.v1.json`. On isolated PostgreSQL database `acp_acceptance_factory_r2` it recorded **51 scenarios: 46 passed, 5 gated, 0 failed** in 105.153 seconds. This is a deterministic component-composed operating day; it does not claim one Production-like transaction or real-provider rehearsal.

## Capability matrix

| Capability | Classification | Evidence / gate |
| --- | --- | --- |
| AUTHENTICATION | READY_WITH_EXTERNAL_GATE | Server authentication/negative authority passed; healthy Redis integration unavailable |
| EMPLOYEE_ADMIN / ACTIVATION | READY | Canonical role, Branch, Membership and readiness contracts passed |
| CUSTOMERS / LOCATIONS | READY | New/existing Customer intake, duplicate replay, scoped search/context passed |
| JOBS / SCHEDULING / DISPATCH | READY | Creation, replay, lifecycle, reschedule, cancel, assignment/readiness passed |
| MOBILE_MY_DAY / FIELD_JOB | READY_WITH_EXTERNAL_GATE | Server and Jest contracts passed; physical device external |
| TIMEKEEPING | READY | Employee-owned punch, manual authority and Payroll snapshot separation passed |
| ASSETS_EQUIPMENT / FLEET | PARTIAL | Current authority and replay passed; readiness/warranty policy remains owner-controlled |
| PRICE_BOOK / ESTIMATES | READY | Scoped snapshot, revision, stale and decision outcomes passed |
| ESTIMATE_DELIVERY / COMMUNICATIONS | READY_WITH_EXTERNAL_GATE | Exact artifact/logical intent and synthetic provider truth passed; real provider prohibited |
| JOB_COMPLETION | READY | Field evidence, blocker, stale and replay contracts passed |
| INVOICES / OPERATIONAL_AR | READY | Scoped receivable, stale rejection, partial/open balance distinction passed |
| PAYMENTS | READY_WITH_EXTERNAL_GATE | Synthetic collection/application/uncertainty passed; no real movement |
| PURCHASING / OPERATIONAL_AP / INVENTORY | READY | Obligation, application, movement, conservation and Branch scope passed |
| SERVICE_AGREEMENTS | READY | Versioned lifecycle/idempotency evidence passed |
| OWNER_OPERATIONS / ECONOMICS | READY | Supported owner projection and obligation/cash distinctions passed |
| LUMINARY / BEACON / LIA | READY | Read authority, replay, evidence binding and bounded non-mutating answers passed |
| AUDIT | READY | Event/audit tenant scope and payload safety passed |
| MIGRATION READINESS | READY_WITH_EXTERNAL_GATE | Synthetic manifest/readiness passed; real protected sources external |
| BACKUP_RECOVERY | PARTIAL | Transaction rollback/replay and restart-oriented contracts passed; infrastructure restore rehearsal external |

## Operating-day and persona results

- **Company Administrator:** positive owner/readiness/Economics authority passed; protected provider/source and policy decisions remain gated.
- **Office Manager:** Invoice, Payment, AP, Inventory, Service Agreement, Communications and owner-operational reads passed; unsupported Accounting/Payroll authority remains denied by the canonical matrix.
- **CSR:** Customer intake/search, Job orchestration, Estimate and Communications intent passed; Payroll/Accounting/Admin attack coverage remains denied.
- **Dispatcher:** scheduling, reschedule, cancellation, assignment, Branch and stale-version paths passed.
- **Technician:** My Day, assigned arrival, field evidence, Assets view and Timekeeping passed; unassigned and administrative actions fail closed.
- **Restricted Employee:** tenant, Branch, other-Employee, protected authority and safe-error attacks passed.

## Scenario disposition

1. New and existing Customer calls: **PASSED** — duplicate-safe intake, Location, bounded search/context and tenant evidence.
2. Job, Scheduling and Dispatch: **PASSED** — one Job authority, versioned reschedule/cancel, readiness-aware assignment and stale rejection.
3. Employee readiness and Mobile/My Day: **PASSED_WITH_EXTERNAL_GATE** — server composition passed; physical device remains external.
4. On My Way, arrival/start and Communications: **PASSED_WITH_EXTERNAL_GATE** — idempotent arrival and logical delivery truth passed; real provider prohibited.
5. Timekeeping: **PASSED** — independent punch/break/workday authority; no implicit Job-driven time mutation.
6. Assets/equipment and Fleet: **PASSED / POLICY_REQUIRED** — identity, replay and fail-closed readiness passed; no readiness/warranty policy invented.
7. Price Book, Estimate, delivery and decline: **PASSED** — immutable snapshot, revision, artifact digest, stale and decline-without-conversion behavior.
8. Field evidence and Job completion: **PASSED** — snapshot, stale, blockers, event rollback and response-loss convergence.
9. Invoice, delivery and Payment: **PASSED_WITH_EXTERNAL_GATE** — one receivable, stale rejection, same-day/partial/uncertain application; real money prohibited.
10. Cash/AR, Vendor/AP and credit-card composition: **PASSED** at current synthetic contract boundaries — obligations, settlement and cost/cash distinctions remain separate; no real posting.
11. Inventory/material and Service Agreements: **PASSED** — quantity conservation, Branch scope, lifecycle and replay evidence.
12. Customer communication history: **PASSED** — bounded tenant/Branch/Customer history with truthful provider states.
13. Owner Operations, Economics, Luminary, Beacon and LIA: **PASSED** — supported evidence is visible without fabricated totals, causality or mutation.
14. Audit/Business Events: **PASSED** — scoped traceability and protected-payload controls.
15. Same-day residential, Net-30 Customer, partial-payment, Net-30 Vendor and card-purchase scenarios: **PASSED** as component-composed synthetic contracts; external settlement/posting remains prohibited.
16. Reschedule, cancellation and declined Estimate: **PASSED** — stale commercial/communication authority cannot replace current state.
17. Backend outage and response loss: **PASSED** — staging failures roll back and exact retries converge.
18. Redis failure: **DEPENDENCY_BLOCKED** — fail-closed behavior is established; no supported healthy local Redis exists.
19. Permission, Branch and Membership revocation: **PASSED** — reauthorization and inactive-context tests reject stale authority.
20. Provider outage: **PASSED_WITH_EXTERNAL_GATE** — synthetic failure cannot corrupt Scheduling, Job, Estimate, Invoice or Payment authority.
21. Rapid-action stress: **PASSED** — Customer, Job, scheduling, lifecycle and application concurrency return one authority.
22. Tenant/persona attacks and error safety: **PASSED** — no foreign existence leakage or reflected SQL/path/secret payload.

## Qualification totals

- Acceptance factory: **46 passed, 5 gated, 0 failed** across 51 scenarios.
- Backend fresh-database regression: **2,469 passed, 7 skipped, 1 deselected** in 250.42 seconds. The deselection is the known Redis-dependent rate-limit integration test.
- Frontend: **105 files / 345 tests passed**; ESLint, TypeScript and production Vite build passed.
- Mobile: **10 suites / 97 tests passed**; ESLint and TypeScript passed.
- QBO synthetic affected boundary: **131 tests passed**; focused malformed-manifest regression: **17 passed**.
- Database: exactly one head `k7l5n83d0q6r`; three fresh upgrades used by this program; current=head and drift clean.
- Static: Python compilation and `pip check` passed; MyPy passed across **684 source files**; changed harness/tests pass Ruff; diff check passed.
- Dependencies: frontend runtime audit clean; Mobile runtime audit retains 24 advisories (15 moderate, 9 high) behind the Mobile/Expo owner gate.
- Secret scan: four matches, all intentional synthetic test canaries; no value emitted.
- Performance baseline: acceptance catalog 105.153 seconds; broad backend 250.42 seconds; My Day query shape, bounded history/list and N+1 regression tests passed. These are local non-production gross-regression measurements, not SLOs.

## Defects and repairs

1. `TEST_ISOLATION / COLD_MODEL_REGISTRATION`: the new Assets action test imported Jobs through Asset service without registering Appointment, so a cold process failed mapper configuration. The test now explicitly registers Scheduling models; the affected scenario passes 2/2.
2. `STATIC / FAIL_CLOSED_MANIFEST_VALIDATION`: QBO Accounting admission treated an `object`-typed bounded entity collection as iterable. It now requires a list and raises a fixed type error before source evidence traversal. A malformed-manifest regression passes; all 131 QBO tests and MyPy pass. This changes no source authority or Accounting policy.

No domain-semantic defect was taken from an active owner.

## Recovery contract

- Validation or malformed evidence: user correction or owner/admin action.
- Stale version/permission/Branch context: refresh and reauthenticate; never retry stale authority blindly.
- Response loss: exact idempotency replay.
- Provider uncertainty: wait/reconcile; never blind resubmit.
- Redis unavailable: authentication/rate limiting remains fail closed; restore required dependency.
- Event/storage transaction failure: retry only after rollback/health recovery.
- Policy/source gate: owner decision or authorized source acquisition; preservation remains default.

## Integration packet and remaining gates

Integrate the acceptance harness, machine evidence, two bounded repairs, and this packet from `work/enterprise-operational-acceptance-factory-1`. Remaining gates are healthy Redis integration, real communications/payment providers, physical-device acceptance, protected Migration sources, infrastructure backup/restore rehearsal, Assets readiness/warranty policy, Mobile dependency-major ownership, Preview deployment, and Production authorization.

Local collision-free acceptance work is exhausted. Preview and Production remain untouched.
