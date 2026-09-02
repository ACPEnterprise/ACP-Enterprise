# MOBILE.EMPLOYEE.FIELD.PRODUCT.PROGRAM.1

## Authority and product boundary

Starting authority: `origin/customer-management-v1@7b5a46e87a87832b0b0eb6bcdbe2d06a0233d196`. Mobile remains the existing Expo 54 / React Native 0.81 native project. ACP Enterprise remains the identity, tenant, Branch, assignment, lifecycle, completion, communications, and mutation authority. The client never supplies an Employee identifier and never broadens access from a role label.

The dependency-safe field product consumes only effective permission codes and assignment-scoped server contracts:

- `GET /api/v1/employee-operations/me/day` for privacy-bounded Customer/Location context;
- `GET /api/v1/technician/itinerary` and `/jobs/{job_id}` for assigned-technician versions and completion state;
- dispatch `arrival` for `en_route` and `arrived` with expected version and idempotency;
- Job `start`, `pause`, `resume`, and `complete` with server versions and lifecycle guards;
- existing self Timekeeping state/timecard/punch contracts.

## Capability audit

| Capability | State | Boundary |
|---|---|---|
| Permission shell | READY | Tabs/actions derive from permission codes; role labels have no effect |
| My Day / today list | READY | Server-resolved Employee and active assignment only |
| Upcoming/recent Jobs | SOURCE_REQUIRED | Current itinerary exposes active assignments by requested service date, not bounded completed history |
| Job detail | READY | Safe My Day projection plus assigned-technician state; no general Job detail or protected notes |
| Customer/Location | READY | Display name and service address only; system Maps handoff is explicit |
| On My Way / Arrive | READY | Exact authoritative dispatch states; no direct communication |
| Start/Pause/Resume/Complete | READY | Server-confirmed, permission/version/assignment guarded; completion requires server readiness |
| Completion requirements | READY | Exact missing requirement codes, commercial authority, and invoice handoff state |
| Work summary/customer disposition | READY | Explicit inputs use idempotent assigned-technician evidence contracts and server confirmation |
| Photos/documents | SOURCE_REQUIRED | No accepted attachment upload/store contract |
| Customer equipment | SOURCE_REQUIRED | ASSET.001 is Company/Branch asset authority, not assignment-scoped Customer equipment |
| Estimate presentation | SOURCE_REQUIRED | Existing Estimate read is Company/Branch scoped, not technician-assignment scoped |
| Invoice | STATUS_READY | Completion projection exposes handoff/status only; no Accounting authority |
| Payments | NOT_AUTHORIZED | No field Employee collection authority; no instrument handling |
| Communications | SEAM_READY | Dispatch/completion events remain server-owned; provider is not configured; Mobile sends no SMS/email |
| Breaks | READY | Existing Timekeeping state machine supports Start Break/End Break |
| Notifications | SOURCE_REQUIRED | No Employee notification center/push contract; app recovery uses authoritative refresh |
| Fleet/inspection | SOURCE_REQUIRED | ASSET.006 is not authoritative; Mobile creates no Fleet contract |

## Reliability and security

Every field mutation is disabled outside `LIVE`. Offline and transient failures retain minimum cached display as `LAST CONFIRMED — STALE`. Arrival reuses one opaque idempotency key while unresolved. Response loss for Job lifecycle mutations enters `MUTATION OUTCOME UNCERTAIN`, refreshes authoritative itinerary state, and forbids blind retry when the result cannot be proven. Reconciliation-required assignments are read-only.

Session/authorization is reconciled on connectivity restoration and foreground. A removed permission removes its tab/action after server refresh; 401 clears protected credentials and returns to authentication; invalid membership, Branch, or Employee linkage fails closed. Foreign/deep-linked Job identifiers must survive both membership-derived Employee assignment guards and Branch authorization. Strict response schemas reject unexpected fields. No Customer history, contact channel, protected note, financial instrument, Payroll, compensation, token, or filesystem path is cached or displayed.

## Accessibility and device contract

Critical state is textual and announced as an alert; color is supplementary. Actions use the existing minimum 48/56-point controls, explicit labels, safe-area scroll containers, Dynamic Type-compatible text flow, and no horizontal fixed-width content. Qualification viewports are 375×667, 430×932 (physical iPhone 13 Pro Max logical class), and 440×956. Primary actions remain in vertical flow and are disabled rather than hidden during uncertain authority.

## Physical-iPhone acceptance packet

Use only deterministic Preview synthetic data. Do not repeat already-proven authentication or baseline Timekeeping merely for activity.

| Screen | Action | Expected result / server evidence | Failure / retry |
|---|---|---|---|
| My Day | Pull to refresh | `LIVE`, only assigned work, safe Customer/Location fields | 401 reauth; 403 denied; 422 identity; 502/offline stale; no mutation |
| Job Workspace | Tap assigned card | Matching itinerary versions and completion state | Missing/reassigned item closes authority; no retry needed |
| Job Workspace | On My Way | Server confirms `en_route`; transactional communication remains provider-gated | Uncertain response reconciles with same key; never tap repeatedly |
| Job Workspace | Confirm Arrival | Server confirms `arrived` | Same idempotent recovery rule |
| Job Workspace | Start Work | Server confirms `in_progress` only after arrival | On uncertainty refresh; do not retry until state is known |
| Job Workspace | Pause/Resume | Server confirms accepted lifecycle state | Conflict refreshes; uncertainty forbids blind retry |
| Completion | Review blockers | Exact server missing requirements shown | No mutation while blocked |
| Completion | Complete Work | Offered only when `completion_ready`; server confirms completed | Never retry uncertain completion blindly |
| My Time | Observe/punch only when intended | Independent authoritative Timekeeping state | Existing idempotent recovery contract |
| Account | Review environment/access; sign out | Preview/version/access summary; protected session cleared | Local sign-out remains effective if server unavailable |

Direct denial qualification: attempt a foreign Job UUID and a removed/reassigned assignment in a synthetic test harness; expect not-found/forbidden without data. Remove Job Execute from a synthetic restricted identity; the field read may remain if Job Read exists, but every mutation control must disappear. Remove Job Read/My Day to remove the corresponding surface. Do not alter the physical acceptance identity during unattended execution.

## Apple, Expo, and integration readiness

Bundle identity and native project are preserved. Entitlements, EAS profiles, Preview environment pinning, privacy manifest, Pod lock, and shared Xcode scheme remain in place. Signing, certificates, App Store Connect, TestFlight, and builds are external owner gates and were not mutated.

Expo 54 is the current accepted physical-device baseline. Dependency audit findings are tracked, but no major Expo upgrade is justified inside this program without an Apple release compatibility decision. A bounded future upgrade must preserve secure storage, linking, network recovery, native identifiers, and the physical acceptance matrix.

Protected integration owns only `mobile/**` and this document. Enterprise must rebase/cherry-pick onto current authority, run Mobile qualification, and deploy Preview separately. No backend, schema, role, permission, fixture, Preview, Production, communications provider, or Apple state is changed by this lane.
