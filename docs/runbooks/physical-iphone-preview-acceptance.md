# Physical-iPhone Preview acceptance

This runbook is server/admin preparation only. It does not authorize Xcode signing,
Production, real Employee data, or recording invitation/activation secrets.

1. Bind the run to the integrated Git SHA, Alembic head, frontend build, permission
   catalog fingerprint, persona-fixture digest, and contract version.
2. Create six synthetic Users and active Company Memberships. Link Employee records
   only for Technician and OWN_DATA_ROLE unless another accepted contract requires it.
3. Grant one synthetic Branch and exactly one canonical role per persona.
4. Complete Preview invitation claim through the accepted onboarding flow. Keep the
   activation secret out of logs, screenshots, and evidence.
5. Authenticate on the device; record only safe User/Membership fixture references and
   authorization version.
6. Execute each allow and denial in `physical-iphone-personas.v1.json`, including direct
   APIs. Hidden UI is not proof of denial.
7. For OWN_DATA_ROLE, use only `/me` APIs and attempt Employee-ID substitution against
   any parameterized administrative endpoints. All substitutions must fail.
8. Remove the role, Branch grant, and Membership in separate cases. Verify old access
   tokens fail according to authorization-version/session semantics, then reauthenticate.
9. Restore only the intended authority and repeat the positive case.
10. Record PASS, FAIL, or BLOCKED with safe evidence. A pending Preview deployment or
    unavailable integrated database is BLOCKED, never PASS.

No device test may call a real provider, communicate with a real Customer, execute a
payment or Payroll action, or modify Production.
