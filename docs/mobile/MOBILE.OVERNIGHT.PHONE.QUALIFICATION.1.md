# MOBILE.OVERNIGHT.PHONE.QUALIFICATION.1

## Authority and recovered lane

Qualification started and ended at protected authority
`36cae7427d65130cbba38b77e66b881ddc8c828f` on branch
`work/mobile-overnight-phone-1`. The primary worktree's unrelated documentation
changes were preserved. The previous physical-phone Metro lane was inspected before
its Metro process was replaced with a current-authority process; its source differed
from protected authority only in the now-authoritative Preview fixture packet.

The current Metro server runs from this isolated worktree on port `8081` with:

- `EXPO_PUBLIC_APP_ENV=preview`
- `EXPO_PUBLIC_API_BASE_URL=https://preview.allcountyhomeservices.com`
- `EXPO_PUBLIC_PRODUCTION_ACTIVATED=false`

Production has no active endpoint. No Preview or Production data was mutated.

## Qualification evidence

### Automated

- Jest: **14 suites / 119 tests passed**.
- TypeScript, ESLint, Expo configuration validation: **passed**.
- iOS and Android Expo/Hermes exports: **passed** (1,142 modules; approximately
  2.7 MB JavaScript bundle on each platform).
- Preview fixture contract dry-run: **passed**, digest
  `1efc12ceaec700fbda3ca91caa6af11e581a24ffea0114ac3bcc0087afd989ca`,
  30 scenarios, `mutationPerformed=false`.
- The test inventory covers generic login failure, verified session restoration,
  logout/secure clearing, permission-derived navigation, My Day, assignment detail,
  Job Workspace, Clock In/Out and breaks, 502 stale-state recovery, reconnect,
  duplicate-tap protection, and lost-response reconciliation with a stable logical
  idempotency key. Punch requests contain neither Employee identity nor client time.
- Unauthenticated live Preview probes returned `401` for `/timekeeping/me/state`
  and `/employee-operations/me/day`, confirming HTTPS reachability and fail-closed
  authentication rather than fabricated empty data.

The local Python environment does not contain the backend dependency set, so no
backend pytest result is claimed. Mobile request/response contracts compile and the
current authoritative Mobile regression suite passes against the same source tree.

### Simulator

- Xcode `26.6` (`17F113`), iOS Simulator SDK `26.5`, CocoaPods `1.17.0`.
- `ACPEmployee.xcworkspace`, scheme `ACPEmployee`, Debug simulator build with code
  signing disabled: **BUILD SUCCEEDED**.
- The app installed and launched on a booted iPhone 17 simulator; the current Metro
  bundle completed successfully. Authentication and sanctioned Employee business
  flows were not executed in the simulator because no credential or live operational
  fixture was injected.

### Physical device

- CoreDevice reports the paired device named `Michael's 13 promax` available over
  the local network. Its mechanical model report is iPhone 17 Pro Max (`iPhone18,2`);
  this discrepancy is retained rather than silently relabeled.
- The already-installed development build, bundle `com.acpenterprise.employee`,
  launched successfully from the current Preview Metro endpoint and remained a live
  process on the phone.
- This overnight run did not clear the existing SecureStore session, impersonate a
  real Employee, create a punch, or execute Job mutations. Consequently it does not
  claim a fresh hands-off pass for credential entry, session restoration, My Day,
  Job detail, or Timekeeping. Those need an owner-observed pass with sanctioned
  Preview authority. Prior repository evidence remains historical evidence and is
  not represented as a new physical run.

An Expo development installation requires the Laptop and phone to remain mutually
reachable and Metro to remain running. It is **not employee-distribution-ready**.

## Fixture and server/office consistency boundary

`acp-employee-beta-v1` is the sanctioned synthetic identity contract. Current
repository tooling intentionally supports deterministic local dry-run only. The
identity domain adapter has no live HTTP/CLI apply transport, and the complete field
day cannot safely apply/reset because Service Location creation and cross-domain
teardown lack fixture ownership/idempotency guarantees. No direct SQL or broad
administrative substitute is permitted.

For a live owner-observed pass, OM1 Phone must confirm a sanctioned active Preview
User → Membership → Employee → MAIN Branch context and the exact restricted Mobile
permissions. Enterprise must supply or authorize an idempotent assigned-Job fixture
before Job mutation acceptance. OM2-A remains owner of Asset/Fleet truth; Mobile
must consume its assignment-scoped projections and must not create fixture Asset
authority.

## Build/install readiness and distribution gates

Engineering install readiness is **ready** for a local development client and an
unsigned simulator build. Distribution readiness is **not ready** because this pass
does not authorize or establish Apple distribution signing, provisioning, an App
Store Connect record, live AASA hosting, archive upload, TestFlight processing, or
an independent install that does not rely on Metro.

Remaining distribution prerequisites are:

1. active Apple Developer team and registered `com.acpenterprise.employee` App ID;
2. Associated Domains capability and live, validated AASA for
   `employee.acpenterprise.com`;
3. owner-controlled distribution certificate/profile or managed EAS credentials;
4. App Store Connect record, unique build number, signed Preview archive, upload and
   TestFlight processing;
5. sanctioned synthetic Preview identity and deterministic assigned-Job fixture;
6. owner-observed physical pass for login/session, My Day, Job Workspace,
   Timekeeping, disconnect/reconnect, lost-response recovery, and server/office
   consistency;
7. independent security/release approval before employee distribution.

No Apple account, signing, TestFlight, Preview deployment, real identity, customer
communication, Payroll, or Production operation occurred.
