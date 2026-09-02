# MOBILE.PHYSICAL.FIELD.ACCEPTANCE.PROGRAM.3

## Authority and outcome

Starting authority: `648faa17a6c9dba60d17ec5a2a15abac26c118f4`. Program 2 successor contracts are already integrated under protected-integration commits `dc44850`, `b32b80f`, and `29fe9a1`. This lane changes no server contract or data. The separate Apple distribution lane is not integrated.

ACP Employee now presents a clearer field-day sequence: My Day says what to do next; live Jobs open directly; Job Workspace refreshes assignment, workflow, equipment, Fleet, and Estimate context together; reconnect refreshes field context; server-confirmed mutations distinguish confirmed, reconciled, not sent, and still unconfirmed outcomes; completion blockers use technician language; Estimate totals are customer-readable; equipment shows bounded history; and My Time explicitly remains independent from Job state.

## Owner observation packet — iPhone 13 Pro Max / Preview

Use only `acp-employee-beta-v1` and its synthetic assigned Job. Do not repeat a mutation when the app says it cannot confirm the result.

1. **Launch:** open ACP Employee. Expect session restoration or the Sign In screen. If it fails, return one screenshot of the message.
2. **My Time:** if already clocked in, do not create another punch. Otherwise tap **Clock In** once and expect **Clocked in** plus “confirmed.” If it fails, return the screenshot and approximate tap time.
3. **My Day:** confirm the first card answers when, Customer, address, service, Job state, and next action. Tap it once. If information is unclear, return one full-screen screenshot.
4. **Job Workspace:** confirm **NEXT STEP**, address/directions, equipment and warranty evidence, and Estimate total are readable. Report only the missing section if one is absent.
5. **Travel/work:** on the synthetic Job only, tap **On My Way**, **Mark Arrived**, then **Start Work**, waiting for **Action confirmed** after each. If “couldn't confirm” appears, stop and return the screenshot plus approximate tap time; do not tap again.
6. **Evidence and pause:** save a clearly synthetic work summary and synthetic customer outcome. Tap **Pause Work**, then **Resume Work**, waiting for confirmation each time.
7. **Completion:** read **Before completion**. Satisfy only sanctioned synthetic requirements, then tap **Complete Work** once when **Ready to complete** appears. Confirm completion does not clock out My Time.
8. **Jobs/Fleet:** open **Jobs**, open a live Job card, return, review **Completed/recent** and **My vehicle & field readiness**. Expect only assigned/own records.
9. **Recovery:** after a successful refresh, enable airplane mode and pull to refresh. Expect stale/offline wording and disabled mutations. Disable airplane mode; expect automatic recovery or one pull-to-refresh, without reinstall.
10. **Finish:** open **My Time**, tap **Clock Out** once only if clocked in, confirm **Clocked out**, then sign out. If any step fails, return only its screenshot and approximate time.

Permission, Branch, membership, Employee, and session revocation exercises require an Enterprise-controlled synthetic authority operator. Michael should only foreground/pull-to-refresh and verify that removed data/actions disappear; he should not administer those changes from the phone.

## Mutation and recovery truth table

| Phone message/state | Meaning | Retry |
|---|---|---|
| Action confirmed | Server response and refreshed state agree | Do not repeat |
| Latest Job state is shown | Initial response failed; reconciliation succeeded | Review state first |
| Action was not sent | Offline check failed before request | Safe after live refresh |
| Couldn't confirm that action | Request outcome and refresh are unavailable | Do not retry; preserve time/screenshot |
| Permission/assignment changed | Current server scope denies the resource | Do not retry |
| LAST CONFIRMED — STALE | Cached display only | Read-only; wait for LIVE |

Timekeeping retains its deterministic idempotency key across an uncertain retry. Job/Dispatch operations reconcile authoritative versions and keep actions disabled until current state is readable. There is no offline mutation queue.

## Product-quality qualification

- Login retains generic bad-credential, offline, throttling, backend-unavailable, restoration, and sign-out behavior without exposing credentials. Keyboard avoidance and scroll dismissal now protect smaller/Dynamic Type layouts.
- My Day prioritizes window, Customer, address, service, Job state, and next action. Job cards remain at least 48 points and use non-color-only state.
- Job Workspace corrects the Start Work gate for authoritative `ready` Jobs. A single refresh now covers all constituent projections.
- Estimate presentation uses locale currency formatting, prominent total, issued revision evidence, and explicit no-edit/no-acceptance wording. It projects no internal cost or margin.
- Equipment history remains explicit Job↔Asset only and bounded by the server contract. Warranty is always labeled evidence, not coverage.
- Jobs uses a nested stack so Today/Upcoming cards open without routing through My Day. Completed history remains bounded/read-only.
- Fleet/custody readiness is visible from Jobs and Job Workspace only with Asset authority; there is no Fleet administration.
- Completion codes are translated to work summary, customer outcome, and Estimate/non-billable instructions.
- My Time states explicitly that punch and Job lifecycle are separate. Existing Clock/Break idempotency and reconciliation remain unchanged.
- Attachments, Employee notifications, push, technician Estimate decision/delivery, and communications delivery proof remain truthful gates. No controls pretend these operations exist.

## Physical and performance boundary

Component tests cover phone-sized scrollable layouts, accessibility roles/labels, disabled duplicate taps, stale behavior, and customer-readable successor context. Expo/Hermes export is the available cold-bundle proxy. Actual iPhone launch/navigation/network timings and VoiceOver/Dynamic Type observation require Michael's device pass above; no Production SLO is invented.

## Apple and Expo

Apple classification: **NEEDS_RECONCILIATION**. The distribution lane is based on older authority, is not an ancestor of current protected authority, and contains six distribution-only files. Its product analysis remains useful, but it must be rebased/requalified separately; this lane does not integrate it. Signing, App ID/App Store Connect, live AASA, archive upload, and TestFlight remain **EXTERNAL_APPLE_GATE**.

Current baseline remains Expo `57.0.19`, React Native `0.86.3`, and React `19.2.3`. No major upgrade or forced audit remediation is performed. Native folders are preserved.

## Remaining gates

- `SOURCE_REQUIRED`: attachment upload/download custody, Employee notification inbox, technician Estimate decision/delivery, field communication delivery evidence.
- `POLICY_REQUIRED`: technician inspection checklist/cadence/admission.
- `PROVIDER_REQUIRED`: real SMS/email/push delivery.
- `EXTERNAL_APPLE_GATE`: distribution signing, live AASA, App Store Connect, TestFlight.
- `PHYSICAL_OWNER_OBSERVATION`: device timings, VoiceOver/Dynamic Type, real interruption behavior, and the sanctioned synthetic mutation sequence.

Preview was not changed by local engineering. Production was untouched.
