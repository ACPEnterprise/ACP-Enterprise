# TwelveHats Sunday device readiness — November 15, 2026

This is the operator acceptance sheet for the clean-Beta HTTPS web application. Do not record passwords, reset tokens, or session tokens on this sheet. TwelveHats currently requires network connectivity; offline work is not supported.

## Release candidate

- Integration baseline: `d1e00c6aabbf635f9c6b76765509973a14edf57b`
- Candidate branch: `work/om2c-current-product-acceptance-1`
- Candidate SHA: record after OM2C commit and MASTER admission: `________________`
- Stable HTTPS URL: `________________`
- Current/future clean-Beta appointment: `________________`

## Active workforce device matrix

Automated values below are backed by the canonical seven-person cutover contract, Python 3.12 authorization/authentication tests, and WebKit iPhone acceptance. `PHYSICAL CHECK REQUIRED` is reserved for the employee's real phone and credential.

| Employee | Canonical role | Login backend | Role/permissions | Mobile routes | Dispatch eligibility | My Day eligibility | Session behavior | Physical device |
|---|---|---|---|---|---|---|---|---|
| Michael Fouse | Administrator | PASS | PASS | PASS | PASS (office authority) | PASS (role-appropriate landing) | PASS | PHYSICAL CHECK REQUIRED |
| Lianne Hernandez | Office Manager | PASS | PASS | PASS | PASS (office authority) | PASS (role-appropriate landing) | PASS | PHYSICAL CHECK REQUIRED |
| Alex Donahue | Field Manager | PASS | PASS | PASS | PASS | PASS | PASS | PHYSICAL CHECK REQUIRED |
| Malcolm Calci | Helper / active field employee | PASS | PASS | PASS | PASS | PASS | PASS | PHYSICAL CHECK REQUIRED |
| Melvin Santiago | Technician | PASS | PASS | PASS | PASS | PASS | PASS | PHYSICAL CHECK REQUIRED |
| Dakota Wilcox | Technician | PASS | PASS | PASS | PASS | PASS | PASS | PHYSICAL CHECK REQUIRED |
| Jason Calci | Technician | PASS | PASS | PASS | PASS | PASS | PASS | PHYSICAL CHECK REQUIRED |

## Inactive access

| Employee | Login denied | Dispatch denied | My Day denied |
|---|---|---|---|
| Dareis Montgomery | PASS | PASS | PASS |
| Kamen Wilmington | PASS | PASS | PASS |

## Per-device operator checklist

Run every step on the employee's physical phone. Use a current/future clean-Beta appointment. Do not write to HCP or Production.

1. Write the employee name and phone model at the top of a blank copy of this checklist.
2. Confirm the login identifier/company email with the employee; do not write the password.
3. In Employees, have Michael or Lianne confirm the account is active and the canonical role is correct.
4. Open the stable HTTPS TwelveHats URL in Safari. Confirm no certificate warning appears.
5. Sign in. For an intentionally wrong password, confirm a generic error appears and no account/security detail is disclosed; then sign in correctly.
6. Confirm the expected landing view and navigation. Verify effective access, not the employee's title.
7. For field users, open My Day and confirm appointment time, customer, address, Job, and status. For office users, verify customer search/detail, Jobs, estimates, schedule/dispatch, employee lookup, alerts, and permitted LIA/discrepancy visibility.
8. Using one sanctioned current/future clean-Beta appointment, have the office assign the employee and confirm it appears in My Day.
9. Open the Job. Confirm customer/contact, service address, Job details, notes, estimate/invoice status appropriate to the role, and only permitted actions.
10. Perform one permitted status action or work-summary action. Confirm the office sees the same state.
11. Refresh, navigate away and back, then fully close and reopen Safari. Sign in again if policy requires it and confirm the state persisted.
12. Use the sanctioned password-reset/change flow. Confirm the new credential works and the old credential is rejected. Never record either password.
13. Sign out. Confirm a protected page cannot be reopened with Back or a saved URL without authentication.
14. Mark every matrix cell `PASS` or `FAIL`, record only a safe defect summary/correlation identifier, and mark the device overall `PASS` only when all role-required checks pass.

## Acceptance appointment sequence

Office assigns technician → technician refreshes mobile My Day → appointment is visible → technician opens customer/Job → technician performs a permitted state change → technician starts a fresh browser session → state remains correct → office confirms the same state.

## Monday release-critical failure rule

Stop rollout only for authentication failure, wrong security/role, missing My Day, assigned work not reaching the phone, a field change not persisting, office/field divergence, required mobile UI being unusable, unavailable secure HTTPS, or operationally unusable sessions. Record cosmetic or optional home-screen issues for follow-up without blocking field operation.
