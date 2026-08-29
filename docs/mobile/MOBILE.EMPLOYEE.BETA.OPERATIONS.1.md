# ACP Employee Preview beta operations

This contract finishes unsigned operational preparation. It never provisions Preview, signs a build, or touches Production.

## AASA and hosting

After Apple membership supplies the ten-character Team ID, generate the extensionless document with `APPLE_TEAM_ID=XXXXXXXXXX npm run beta:aasa`. Publish the exact bytes at `https://employee.acpenterprise.com/.well-known/apple-app-site-association` with `Content-Type: application/json`, `Cache-Control: public, max-age=3600`, HTTP 200, no redirect, no authentication, and no content transformation. DNS must point the ACP-controlled hostname to an HTTPS service with a publicly trusted certificate. Verify with `curl --fail --silent --show-error --dump-header -` and compare SHA-256 to the generated file. Roll back by restoring the last accepted AASA bytes; never broaden paths to recover a bad link.

Android later uses the same host for `/.well-known/assetlinks.json`; its signing fingerprint remains separately gated.

## Synthetic fixture gate

`npm run beta:fixture` validates and prints the deterministic Preview-only plan without mutation. The fixture key is stable and every record must carry the synthetic marker/external key. Apply requires both `ACP_ENVIRONMENT=preview` and `ACP_BETA_FIXTURE_AUTHORIZED=true`, plus a separately accepted domain provisioning adapter. The command deliberately refuses `--apply` in this milestone. Contradictory existing keys must fail; idempotent reruns must return existing matching records. Reset must revoke invitations/sessions, remove active assignment/time evidence in domain-safe order, and then remove only records bearing the fixture key. Never use direct SQL, Production, realistic identities, compensation, Payroll, bank, or tax data.

## Release preflight

Run `npm run beta:qualify` from `mobile/`. The deterministic wrapper performs locked dependency installation, operational preflight, iOS/Android Preview Hermes exports, CocoaPods reconciliation, and an unsigned generic-iPhone Release build when full Xcode is selected. The generated, unsigned manifest binds Git/mobile tree SHAs, version/build, bundle ID, Expo/native dependency versions, Preview channel/API, entitlements, AASA/release contracts, and pinned EAS CLI version. Retain it with CI evidence, not secrets.

EAS is intentionally not installed globally. After account authorization, use a repository-reviewed pinned CLI version: `npx eas-cli@16.28.0 login`, `npx eas-cli@16.28.0 credentials --platform ios`, `npx eas-cli@16.28.0 build --platform ios --profile beta`, then `npx eas-cli@16.28.0 submit --platform ios --latest`. Account-authenticated commands require separate authorization. Native fallback: open `mobile/ios/ACPEmployee.xcworkspace`, select `ACPEmployee` Release, Team/App ID/Associated Domains, archive, validate, and export/upload with Xcode-managed signing.

## Physical iPhone acceptance

Record build manifest and Preview server evidence for every step:

1. Install the approved TestFlight build; verify ACP Employee, version/build, and Preview channel.
2. Open the protected activation URL, activate, sign in, and confirm Membership/Employee resolution.
3. Kill/relaunch for restoration; logout and confirm protected state clears; sign in again.
4. Clock In, Start Break, End Break, and Clock Out. Read server state after each and prove no duplicate punch.
5. Verify My Time chronology without fabricated evidence.
6. Verify one My Day assignment, bounded customer/location fields, window, and assignment state.
7. Open read-only Job Workspace, prove no mutation, and explicitly hand off to system Maps.
8. Enable airplane mode; prove mutations fail and cached reads are stale. Restore connectivity and prove reconciliation/no duplicate operation.
9. Inspect task switcher, device logs, and safe errors for secrets, tokens, PII, Payroll, and compensation.
10. Confirm network evidence contains zero Production requests or endpoint selection.

Exercise fixture scenarios for no shift, clocked in, active break, clocked out/history, assignment/workspace, reassignment, session expiration, permission denial, offline stale, and recovery.

## Diagnostics and recovery

Safe runtime build identity is provided by `safeBuildIdentity`: product, version/build, environment/channel, and compatibility version only. Operational diagnostics may additionally contain HTTP status class, operation name, connectivity state, and redacted correlation category. Never record URL query strings, invitation/session tokens, login identity, address/customer payloads, punch payloads, or Payroll data.

- Bad TestFlight build: stop testing, expire/remove it from tester availability, increment build number, repair, and requalify; never reuse a distributed build number.
- Invalid signing: revoke only the affected credential/profile through the authorized Apple team, regenerate, and rebuild; commit no signing material.
- AASA defect: restore last accepted bytes, purge hosting cache where supported, verify HTTP/DNS, then issue a successor build only if entitlements changed.
- Fixture defect: revoke invitations/sessions and run the domain-safe fixture reset after explicit Preview authorization.
- Activation exposure: revoke/supersede the invitation immediately; never reuse the reference.
- Preview API incompatibility: halt beta, preserve evidence, repair the authoritative contract, increment the build when client changes, and re-run preflight. Production rollback is out of scope.

## Authorized TestFlight sequence

Membership active → capture Team ID → register `com.acpenterprise.employee` → enable Associated Domains → deploy/verify AASA → create App Store Connect record → establish managed credentials → generate signed Preview build → upload/process in TestFlight → authorize internal tester → separately authorize/provision synthetic fixture → execute acceptance → classify defects → record acceptance.
