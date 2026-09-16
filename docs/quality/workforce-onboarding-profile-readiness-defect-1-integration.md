# Workforce onboarding profile readiness defect 1 — Enterprise handoff

## Authority and reproduction

- Starting protected SHA: `7ef569e5054083ebd6eb14ca3326c4e271b9db71`.
- Reproduced predicate: Identity Onboarding loads the generic Company role list,
  retains only active system roles, resolves the four approved operating profiles,
  and blocks the entire form when any required canonical role is unavailable.
- Required role compositions are:
  - Administrator: `COMPANY_ADMINISTRATOR`;
  - Office Manager: `OFFICE_MANAGER`;
  - Office Staff: `SERVICE_CSR`;
  - Field Technician: `TECHNICIAN` plus `ACP_EMPLOYEE_MOBILE`.

The protected canonical-role catalog and audited reconciliation API already own
registration and repair. The onboarding page previously discarded the exact
failure state and exposed only “Approved Employee operating profiles are
unavailable” plus a retry that repeated the same request.

## Root cause

Classification: **protected-role/profile registration issue plus frontend
contract mismatch**.

At least one required active system role is absent or represented by a non-system
Company role. The frontend correctly refuses to treat an arbitrary custom role as
approved authority, but it failed to consume the existing Company-scoped
canonical-role reconciliation contract. Missing canonical roles therefore had no
normal recovery path from onboarding, while an unsafe custom-code collision was
indistinguishable from a transient request failure.

## Fix

When approved profiles cannot be composed, onboarding now:

1. obtains the existing canonical-role reconciliation plan;
2. names the unavailable owner-facing profiles;
3. permits `COMPANY_PERMISSION_MANAGE` authority to apply only a plan marked
   `safe_to_apply` through the existing audited endpoint;
4. reloads roles and presents all four profiles after reconciliation;
5. refuses automatic replacement when the plan reports an identity collision;
6. routes unauthorized/conflicting cases to protected Administration review.

No new role definition, permission bundle, onboarding endpoint, or bypass was
created. Canonical apply retains Company scoping, optimistic plan digest checking,
idempotency, audit events, and authorization-version advancement.

Field Technician reconciliation creates/restores only canonical roles and their
permissions. It does not certify technician capability, availability, or Dispatch
readiness.

## Qualification

- Identity Onboarding UI: `7 passed`.
- Canonical least-privilege and roster composition: `21 passed`.
- Onboarding safety/key boundaries: `4 passed`.
- TypeScript production build: passed.
- ESLint: passed with zero warnings.
- PostgreSQL-backed canonical sync/onboarding tests could not start because this
  lane cannot resolve host `postgres`; protected suites were not changed.

## Enterprise deployment and owner retest

1. Integrate and deploy this candidate to Preview.
2. Open Employees & Time → Real employee activation.
3. Choose an unbound roster identity and select Create/onboard ACP Employee.
4. If canonical registration is safely incomplete, select **Prepare approved
   profiles** as an authorized owner administrator.
5. Confirm Administrator, Office Manager, Office Staff, and Field Technician are
   available.
6. Select the owner-certified profile, enter the unique login email, review the
   protected plan, and send the invitation.
7. Confirm the Employee establishes their own password.
8. Return to the source-certification workflow and bind only the exact created
   Employee.

If Preview reports a protected role identity collision, do not replace it during
acceptance; Enterprise must review the conflicting role and preserved assignments.

No Preview or Production data was modified by this lane.
