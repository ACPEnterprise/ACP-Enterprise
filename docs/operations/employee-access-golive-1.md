# EMPLOYEE.ACCESS.GOLIVE.1

## Authority prepared

`ACP_EMPLOYEE_MOBILE` is a canonical, Branch-scoped role with exactly:

- `COMPANY_TIMEKEEPING_OWN_READ`
- `COMPANY_TIMEKEEPING_OWN_PUNCH`
- `COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ`
- `COMPANY_JOB_READ`
- `COMPANY_JOB_EXECUTE`

It grants no Customer administration, Scheduling administration, Dispatch
administration, Payroll, Accounting, payment, Communications, or Company
administration authority. Canonical role reconciliation creates or repairs it
idempotently for an existing Company.

The accepted non-Production owner-claim endpoint is exposed through the Identity
Onboarding UI only after an invitation is created. The activation token is never
rendered, logged, or persisted by the frontend. The owner action immediately opens
`acpemployee://activate` on the same device; ACP Employee then collects the
Employee's password directly.

## Minimum owner UI sequence

The owner must first confirm the real Employee's exact legal/display name and unique
login email directly with that Employee. Do not infer or reuse an administrator
identity.

1. In ACP Preview, open **Administration → Canonical role readiness** and apply the
   safe reconciliation. Confirm `ACP_EMPLOYEE_MOBILE` is **already conforming**.
2. On the iPhone that has ACP Employee installed, open ACP Preview in Safari and go
   to **Administration → Identity Onboarding → Add Employee**.
3. Enter the owner-confirmed Employee name and login email. Select **MAIN** (never
   `SYNMAIN`) and **ACP Employee Mobile**. Select no additive permissions.
4. Choose **Review Employee plan**. Confirm the plan is safe, Branch is MAIN, the
   role is `ACP_EMPLOYEE_MOBILE`, and the effective permission list is exactly the
   five codes above. Resolve any existing-identity or duplicate blocker; do not
   create a second User.
5. Choose **Apply reviewed Employee onboarding** once.
6. Choose **Activate in ACP Employee on this device** once. This consumes the
   non-Production protected owner claim and opens ACP Employee without displaying
   the secret.
7. Hand the unlocked phone to the Employee. The Employee enters and confirms their
   own password in ACP Employee. The owner does not see, choose, store, or share it.
8. After activation, sign the owner out of ACP Enterprise in Safari. In ACP Employee,
   verify authenticated User → Membership → Employee, MAIN, permission-derived
   navigation, My Day, Timeclock state, and logout/login.

If the plan reports an existing User, Membership, Employee, Branch, role, or email
conflict, stop before apply and reconcile that canonical identity. A name match is
never sufficient authority.

## Laptop1 Phone handoff

After activation, provide Laptop1 Phone only the Employee-confirmed login email and
the statement that activation completed. Do not transmit the password or activation
secret. Laptop1 Phone should keep ACP Employee pinned to Preview, ask the Employee
to enter their password directly, verify MAIN/permission-derived navigation, then
perform own Timekeeping acceptance without supplying an Employee ID or authoritative
device timestamp.

Production, Payroll, customer communication, Apple signing, and TestFlight are out
of scope.
