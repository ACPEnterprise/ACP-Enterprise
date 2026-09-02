# OM1 Mobile authority gap closure 1

## Authority and ownership

- Mobile qualification SHA: `428dcbddd7d072b5b8d9edff489efcd4373960b5`.
- Fetched Enterprise authority: `fd2af4057a8dc1ba14777e3c052dd6ed39656404`.
- The three intervening commits add only HCP operational-measurement backend tests,
  implementation, and documentation. They change no Mobile, authentication, API,
  schema, migration, Preview, native, or Apple contract. Reconciliation by merge or
  rebase is not required for this acceptance.
- OM1 owns repository integrity, contract/static/synthetic qualification, and bounded
  defect support. Laptop1 retains the iPhone 13 Pro Max and all physical observation.

## Physical acceptance gap matrix

| Physical observation or gate | Classification | Mechanical disposition |
|---|---|---|
| Prior customer-list/detail crash acceptance (`PHONE-BUG.1`) | `ALREADY_ACCEPTED` | Physical iPhone acceptance is recorded at deployed commit `7d55ba5e76592a81dd42c7e2b77f60729f8848c2`. |
| Expo 57 development-signed physical baseline | `ALREADY_ACCEPTED` | Current accepted Mobile documentation records physical-device and native qualification. |
| Launch ACP Employee and verify Preview build identity, session restoration, and safe sign-in state | `READY_FOR_LAPTOP1` | Preview and bundles qualify; use only the established Laptop1 build. |
| My Day, assigned Job opening, minimum Customer/Location detail, equipment, warranty evidence, Estimate, Fleet, and completed history | `BLOCKED_PREVIEW` | Ready in the client; execution requires Enterprise confirmation that the sanctioned `acp-employee-beta-v1` synthetic fixture and login are live. |
| Clock in/out, breaks, On My Way, Arrive, Start, evidence/disposition, pause/resume, completion, and Invoice handoff | `BLOCKED_PREVIEW` | Mutation contracts qualify, but no mutation may begin until the isolated synthetic fixture is admitted and reset to its declared starting state. |
| Offline/stale and reconnect observation after a live refresh | `BLOCKED_PREVIEW` | Requires the same authenticated synthetic context; Laptop1 performs airplane-mode observation. |
| Permission removal/restoration and foreground refresh | `BLOCKED_ENTERPRISE` | An Enterprise operator must mutate only the synthetic authority while Laptop1 observes. |
| Branch/assignment/membership/Employee revocation and known-link denial | `BLOCKED_ENTERPRISE` | Requires an Enterprise synthetic authority operator; the phone must not administer it. |
| Attachments, Employee notification inbox/push, Estimate decision/delivery, and communications delivery proof | `BLOCKED_SOURCE` | No accepted source/provider contract exists; these are excluded from the physical pass. |
| Technician inspection execution | `BLOCKED_SOURCE` | Accepted policy/admission source is absent; readiness is read-only. |
| Distribution signing, live AASA, App Store Connect, and TestFlight | `BLOCKED_APPLE` | External Apple authority; excluded from Laptop1 Preview acceptance. |

Preview infrastructure itself is reachable and healthy. `BLOCKED_PREVIEW` above means
fixture/login admission is not mechanically provable from OM1 without credentials; it
does not mean the Preview service is down.

## Laptop1 handoff packet

### Admission prerequisites

Enterprise confirms, without sending secrets to OM1, that `acp-employee-beta-v1` is
present, isolated, reset, and provides one synthetic Technician, Branch, assigned Job,
Appointment, Customer/Location, equipment, issued Estimate, own Fleet custody, and the
minimum completion inputs. Laptop1 uses its preserved development-signed app/runtime.

### Owner sequence

1. Launch and confirm Preview identity; restore the synthetic session or sign in.
2. In My Time, avoid duplicate punches; clock in once only when currently clocked out.
3. Open My Day and its assigned Job. Verify schedule, Customer/Location minimum detail,
   service, Job state, next step, equipment/warranty history, issued Estimate total, and
   own Fleet readiness.
4. On the synthetic Job only, perform On My Way, Arrive, Start, synthetic work summary,
   synthetic customer disposition, Pause, Resume, Complete, and Invoice handoff. Wait
   for confirmed authoritative state after each command. Never retry an uncertain command.
5. Verify Completed/recent is bounded and My Time remains independent from Job completion.
6. After a successful refresh, observe airplane-mode stale state and disabled mutations;
   reconnect and refresh without reinstalling.
7. With an Enterprise operator, separately observe permission removal/restoration and
   Branch/assignment revocation against previously known navigation.
8. Clock out once only if still clocked in, then sign out.

For any failure, Laptop1 returns the step, approximate time, displayed recovery wording,
connectivity state, and one redacted screenshot. It must not include credentials, tokens,
Customer payloads, Payroll values, or field-note content.

## Contract qualification

| Contract | Automated evidence | Result |
|---|---|---|
| Login/session and dynamic authorization | authentication, navigation, foundation tests | PASS |
| My Day, Jobs, Job detail, Customer/Location minimum projection | My Day, assignment-detail, field-product tests | PASS |
| Equipment, warranty/history, Estimate presentation, Fleet/readiness | field-product and field-workflow tests | PASS |
| Arrival and Job lifecycle | field-product and field-workflow tests | PASS |
| Completion blockers and Invoice handoff | field-workflow and employee-workflow client tests | PASS |
| Timekeeping and breaks | timeclock, foundation, navigation tests | PASS |
| Offline/stale, reconnect, uncertainty, and duplicate prevention | assignment-detail, timeclock, My Day, field tests | PASS |
| Privacy, diagnostics, app-switcher shield, and activation links | logger, beta-readiness, authentication, beta-operations tests | PASS |

Mobile qualification passed 14 suites and 118 tests, TypeScript, ESLint, Preview
configuration validation, deterministic fixture validation, and fixture dry-run with
`mutationPerformed: false`. Preview-pinned iOS and Android Hermes exports passed.

Affected backend authentication, authorization, Employee My Day, Field Service,
Timekeeping, Dispatch, and Invoice modules/tests all parse under static qualification
(69 files). Runtime pytest is an OM1 environment gate: system Python 3.9 is below the
repository language baseline, and installed Python 3.12 has no pytest environment. No
backend dependency installation was authorized or performed.

## Preview, Apple, and dependency disposition

- Preview URL is exactly `https://preview.allcountyhomeservices.com` in `.env.preview.example`,
  EAS Preview/beta profiles, runtime validation, and the beta manifest. Root, `/healthz`,
  and `/backend-health` return HTTP 200 with valid TLS; protected routes return 401 without
  credentials as required. Production remains inactive and points to `.invalid`.
- `READY_FOR_LAPTOP1_PHYSICAL_ACCEPTANCE`: preserved Laptop1 development-signed setup,
  accepted native baseline, valid bundles, and healthy Preview.
- `READY_FOR_SIGNING_REQUALIFICATION`: no. Distribution requalification has not occurred.
- `NEEDS_RECONCILIATION`: Apple distribution lane versus current Enterprise authority.
- `EXTERNAL_APPLE_GATE`: Team/App ID authority, live AASA, signing, upload, and TestFlight.
- Plists, privacy manifest, and entitlements parse. Bundle `com.acpenterprise.employee`,
  version `0.2.0`/build `2`, iOS 16.4 target, arm64, no arbitrary transport loads, and the
  single associated domain remain aligned.
- Expo `57.0.19`, React Native `0.86.3`, and React `19.2.3` are preserved. Expo dependency
  check passes. Expo Doctor remains 19/21 because OM1 lacks CocoaPods and committed native
  configuration requires explicit synchronization ownership. Audit reports 17 moderate
  transitive advisories, zero high, and zero critical; no compatible bounded fix exists.

## Bounded physical-failure reproduction map

| Laptop1 symptom | Immediate OM1 reproduction |
|---|---|
| Sign-in/session restoration or permission change | `authentication.test.tsx`, `navigation.test.tsx`, then API failure mapping tests |
| My Day/card/detail or Customer/Location omission | `myDay.test.tsx`, `assignmentDetail.test.tsx` with the reported response class |
| Equipment/Estimate/Fleet/history missing or overexposed | `fieldProduct.test.tsx`, `fieldWorkflow.test.tsx`, schema boundary fixture |
| Incorrect arrival/lifecycle/completion/handoff state | `fieldWorkflow.test.tsx`, `employeeWorkflowClients.test.ts`, expected-version and idempotency reproduction |
| Duplicate or uncertain punch/lifecycle action | `timeclock.test.tsx`, `foundation.test.ts`, response-loss/409/502/503 case |
| Offline content not stale or mutation remains enabled | assignment-detail, My Day, field, and timeclock offline cases |
| Layout, Dynamic Type, keyboard, or app-switcher exposure | phone-viewport component case plus `betaReadiness.test.tsx`; physical observation remains Laptop1 evidence |

No product defect was demonstrated in this audit, so no source repair or dependency change
was made. Preview and Production were untouched.
