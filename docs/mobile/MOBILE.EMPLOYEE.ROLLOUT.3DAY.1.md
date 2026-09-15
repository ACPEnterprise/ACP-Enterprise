# ACP Employee controlled rollout

## Distribution candidate

- Product: ACP Employee
- Bundle: `com.acpenterprise.employee`
- Version/build: `0.2.0 (2)`
- Environment: ACP Preview only
- Preview API: `https://preview.allcountyhomeservices.com`
- Production activation: false
- Initial distribution: internal TestFlight only

Build 2 was accepted by App Store Connect transport on September 14, 2026 and
entered Apple processing. It must not be reused. The next candidate build is at
least 3, subject to the latest App Store Connect state at build time.

## Employee installation

1. On the employee's iPhone, install **TestFlight** from Apple.
2. Open the individually addressed ACP Employee internal-testing invitation.
3. In TestFlight, choose **Accept**, then **Install** beside **ACP Employee**.
4. Open ACP Employee and confirm the Account screen identifies the Preview beta
   environment during controlled acceptance.
5. Sign in using the same individual email address and password used for the ACP
   website. ACP Employee has no separate password or PIN.
6. Open **My Day**, select an assigned Job, and use only the actions shown by the
   employee's current permissions.
7. Open **My Time** to Clock On or Clock Off. Wait for the confirmed server result;
   if connectivity is interrupted, reconnect and refresh instead of repeatedly
   tapping the action.
8. Use **Account → Sign out** before giving the device to another person.

ACP Employee currently requests no location, notification, camera, contacts,
microphone, Bluetooth, or background permission. Employees should not be told to
grant permissions the shipped application does not request.

## Support and recovery

The owner must approve a live ACP-controlled HTTPS support URL before completing
store metadata. Until that URL is live, installation or login problems must be
reported through ACP's owner-approved internal support channel with app version,
build number, environment, and the safe correlation reference shown by the app.
Passwords, invitation links, tokens, customer details, and screenshots containing
protected information must never be sent in a support report.

For a forgotten password, use ACP's existing website account-recovery flow. For a
revoked or inactive account, an authorized ACP administrator must reconcile the
User, Membership, Employee, MAIN Branch, and `ACP_EMPLOYEE_MOBILE` role; Mobile
must not create replacement credentials or identities.

## Controlled acceptance

Lianne's protected readiness evidence records one active canonical User,
Membership, Employee, All County Plumbing & Leak Company context, MAIN Branch,
and effective `ACP_EMPLOYEE_MOBILE` permissions. Her email and password remain
outside this repository. A sanctioned MAIN assignment is still required to prove
an assigned Job. She enters her own existing ACP web credential directly.

The physical acceptance sequence is: install without developer tooling, launch,
sign in, verify Company and MAIN, inspect My Day and an assigned Job, Clock On once,
refresh/reconnect and verify the server-active interval, Clock Off once, verify the
completed interval in My Time and office time evidence, then logout/login. Payroll
calculation, payment, public App Store submission, and Production are excluded.

### TestFlight operator sequence

1. In App Store Connect, open **Apps → ACP Employee → TestFlight → iOS** and
   confirm `0.2.0 (2)` is **Ready to Test** or **Testing**. Processing alone is not
   an employee-install result.
2. Create or select an internal group such as **ACP Employee — Controlled Rollout**.
3. Add build 2 to the group. Answer any export-compliance question using the
   owner/legal-approved classification; do not guess.
4. Add only the owner's and explicitly authorized employees' Apple IDs. Do not
   store those addresses in Git or this acceptance packet.
5. Ask each tester to follow the Employee installation steps above and record only
   build, device/iOS class, safe result classifications, and approximate times.
6. For Lianne, rely on her existing canonical ACP identity and password. Do not
   issue a Mobile password. Confirm MAIN and the exact effective Mobile permission
   set before any Job or Timekeeping mutation.
7. Run Clock On/Off only during the sanctioned non-payable acceptance window and
   independently confirm the server interval and office readback.

The machine-readable acceptance form is
`mobile/operations/internal-testflight-acceptance.v1.json`.

## Rollback

Remove a defective build from the internal TestFlight group, communicate the hold
through the approved support channel, preserve server evidence, and issue a higher
build number after repair. Do not reuse build 2 and do not represent an app removal
as revoking an employee's ACP server session or permissions.
