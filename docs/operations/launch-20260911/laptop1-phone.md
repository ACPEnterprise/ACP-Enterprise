# LAPTOP1-PHONE launch checkpoint

Last meaningful progress: 2026-09-10 21:57 America/New_York.

## Mission pin and current authority

- Mission ref: `origin/work/launch-20260911-mission`
- Mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Mission file SHA-256: `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`
- Protected implementation base: `42a4f68087d76247269bd4c8388f556dd62a8b5c`
- Last reconciled protected authority: `f3d886d88f432953ea187d989583e068c46ff228`
- Mobile semantic candidate: `9af2a1113bed49d96cc93073768fa94deb0cac07`
- Owning branch: `work/mobile-overnight-phone-1`
- Worktree: `/Users/michaelfouse/Development/ACP-Enterprise-mobile-overnight-phone-1`

The mission was read with `git show` from its remote commit without switching the
Mobile branch. Protected authority advanced after the initial overnight packet. The
branch was reconciled by merging the current protected authority; there was no Mobile
path conflict.

## Completed client boundary

ACP Employee preserves the established login, protected session, permission-derived
navigation, My Day, assigned Job Workspace, field lifecycle, My Time, offline/stale,
reconnect, and mutation-reconciliation architecture.

This successor composes the newly authoritative OM2-A Job-clock contract:

- `GET /api/v1/timekeeping/me/job-clock`
- `POST /api/v1/timekeeping/me/job-clock`
- `GET /api/v1/timekeeping/me/timecard` `job_intervals`

The Job Workspace now shows the server-confirmed active Job clock and offers **Clock
On To This Job** or **Clock Off This Job** only when the Employee has both Job execute
and own-punch capability. A clock active on another Job blocks a contradictory start.
The request sends the assigned Job/Appointment reference and opaque Idempotency-Key;
it never sends Employee, Company, Branch, timestamp, or duration. The server remains
responsible for assignment, Branch, identity, clock, and interval authority.

Connectivity is checked after closing the local double-tap guard. An uncertain response
rehydrates `GET /me/job-clock`; retry retains the original logical key until the result
is established. Foreground and connectivity restoration refresh server truth. Offline,
stale, forbidden, session-expired, conflicting, and uncertain states disable mutation.
There is no offline mutation queue.

My Time now renders current server-persisted Job intervals separately from payable
time entries, including second-level duration and correction/validity state. Job clock,
My Time punch, and Job lifecycle remain three independent authorities.

## Defects repaired

1. A new Job-clock button could accept a second tap while the first tap awaited the
   connectivity check. The in-flight gate now closes before the first await.
2. Boot and session-verification screens render outside React Navigation. A root
   `SafeAreaProvider` was added after a large-text simulator run proved content could
   collide with the Dynamic Island. The repaired simulator view respects the top inset.

## Qualification classification

### Automated

- ESLint: passed.
- TypeScript: passed.
- Jest: 15 suites, 129 tests passed.
- Preview configuration: passed; API pinned to
  `https://preview.allcountyhomeservices.com`; Production inactive/fail-closed.
- iOS Expo/Hermes export: passed, 2.7 MB bundle.
- Android Expo/Hermes export: passed, 2.7 MB bundle.
- Job-clock tests cover start, stop-state presentation, duplicate taps, another active
  Job, offline fail-closed behavior, reconnect, lost response, authoritative recovery,
  stable retry identity, permission revocation, request minimization, and persisted
  timecard projection.
- Existing login/session, My Day, Job, Workday punch/break, stale 502, permission,
  logout, and secure-storage regressions remain green.
- Current protected backend Job clock, Job participation, and My Day projection:
  36 tests passed in a Python 3.12 dependency-complete container using an ephemeral
  read-only source copy. The copy was removed after qualification; the running service
  and databases were not altered.

The host Python remains 3.9 and cannot collect the current Python 3.11+ backend suite
directly. The dependency-complete container closes the focused compatibility gap. The
authoritative OM2-A packet separately records 18 focused and 290 affected backend tests
passing before protected integration.

### Simulator/native

- Xcode 26.6 / iOS 26.5 SDK / CocoaPods 1.17.0.
- Unsigned `ACPEmployee` simulator build: passed.
- Install and launch: passed.
- Large-text safe-area regression: visually reproduced, repaired, and rechecked.

### Preview runtime

Unauthenticated HTTPS probes return `401` for My Day, Workday state, and the new Job
clock. This proves the deployed route exists and remains authentication-protected. It
does not prove an authenticated mutation or office projection.

### Physical device

The paired device named `Michael's 13 promax` was available over USB during
qualification; Apple mechanically reports model `iPhone18,2` / iPhone 17 Pro Max. The
existing development installation launched, received a current Metro reload, and
retained its device storage. At the final reconciliation check the device had become
unavailable, so no later physical claim is made. No session was cleared and no
additional punch or Job mutation was performed.

Fresh physical acceptance of Clock On/Off and office consistency remains
`HUMAN_ACCEPTANCE_PENDING`. A Metro-dependent development installation is not a signed
distributable build and must not be labeled employee-distribution-ready.

## Cross-lane handoff

### Enterprise

Protected-integrate this branch, deploy the coherent backend/client release through the
normal controlled path, and report the exact deployed SHA. No Mobile lane deployment is
authorized.

### OM1 Phone

`ACP_EMPLOYEE_MOBILE`, MAIN Branch defaulting, and the audited owner-claim path are in
protected ancestry through `8a9f4d8`. Confirm one sanctioned Preview acceptance identity
is active and linked without exposing its password or activation secret. Real Employee
activation remains OM1 Phone/Enterprise work; Laptop1 Phone must not impersonate Lianne.
The current OM1 Phone checkpoint confirms the intended real invitation remains pending,
the live Membership does not yet have `ACP_EMPLOYEE_MOBILE`, and the definitive-delivery
retry awaits Enterprise deployment/execution. These facts gate real-Employee physical
acceptance only; they do not invalidate synthetic client qualification.

### OM2-A

The backend Job-clock authority is in protected ancestry through `f4fa8fe`, and the
deployed endpoint exists. After client integration, run the sanctioned phone → server →
office check: active clock visibility, clock-off interval, exact persisted seconds,
single logical events after response loss, and correction lineage. The current office
employee `WorkdayRoute` does not separately render raw Job intervals, while the office
`WorkforceRoute` already renders reconciled worked intervals with Job attribution,
review state, and audit evidence. OM2-A should verify that existing office projection
against the phone interval rather than add a duplicate surface. Do not substitute
scheduled time or payable Workday punches.

### OM2-C

Independently observe the physical workflow and office consistency after deployment.
A 200/401 route probe, simulator build, or Mobile unit test is not physical acceptance.

## Next executable acceptance

After protected integration and Enterprise deployment, use only a sanctioned assigned
Preview fixture:

1. Open the existing development app with Laptop and phone connected; confirm Preview.
2. Restore the sanctioned Employee session; confirm My Day and the assigned Job.
3. Open Job Workspace and observe **Not clocked onto a Job**.
4. Tap **Clock On To This Job** once; wait for ACP confirmation.
5. Background/foreground and refresh; confirm the same active clock remains.
6. Coordinate one response-loss rehearsal with OM2-A; do not blindly repeat.
7. Tap **Clock Off This Job** once; confirm the interval in My Time.
8. OM2-A/office refreshes the same Employee Timecard and verifies exact interval and
   audit lineage; OM2-C records independent evidence.
9. Confirm Workday Clock In/Out did not change automatically and no duplicate evidence
   exists.

Remaining gates: protected integration, coherent Preview deployment, sanctioned
assigned fixture/identity, phone-to-office interval inspection, and owner/OM2-C
physical observation. Apple signing, provisioning,
App Store Connect, live AASA, and TestFlight remain unauthorized external gates.

Preview data was not mutated. Production, Apple signing, TestFlight, real Customer
communication, real Payroll, HCP, and QBO were untouched.
