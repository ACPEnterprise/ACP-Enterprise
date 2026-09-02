# Employee and Workforce Operationalization

## Minimum real-Employee data contract

ACP application access requires only an authoritative unique login email, Employee
name/display identity, Company, explicit Branch grant, reviewed baseline role, and
reviewed explicit additive permissions. Workforce capability, language,
certification, availability, and restriction evidence is optional enrichment unless
a separately approved operating policy makes particular evidence mandatory. Payroll
compensation, tax, banking, home address, and HR termination data are not onboarding
requirements.

The preflight plan classifies identity evidence before apply:

- `NEW_EMPLOYEE_CANDIDATE`: no existing login identity; the normal atomic workflow
  may create User, Membership, Employee, Branch grant, role grants, permission
  profile, and protected invitation.
- `EXISTING_USER_NEEDS_MEMBERSHIP`: a global User exists but Company linkage needs
  explicit review. It is not silently attached.
- `MEMBERSHIP_NEEDS_EMPLOYEE_LINK`: a Company Membership exists without an Employee;
  eligibility for the accepted existing-identity path must be confirmed.
- `DUPLICATE_CONFLICT`: the Company identity already resolves to an Employee.

Names never establish identity. Migration may provide a provider-neutral candidate
and source/crosswalk reference, but Employee authority owns the final explicit
disposition. Weak matches remain `STRONG_CANDIDATE_REQUIRES_REVIEW` or
`DUPLICATE_CONFLICT`; they are not automatically consolidated.

## Owner permission review

The owner reviews the canonical role as a starting bundle, actual role-default
permissions, explicit additive permissions, own-data restrictions, Branch scope,
and high-impact flags. Additive profiles do not implement deny semantics. Removing
role-derived authority requires an authorized role change; explicit additions survive
only while their profile role remains active. Every server mutation remains subject
to current permission, tenant, Branch, optimistic/replay, audit, and authorization-
version controls.

High-impact review covers non-read operations in protected domains including
Administration/identity, Accounting, Payments, Payroll administration, Purchasing,
Inventory, Migration, Beacon, Economics, Assets, and Communications. Read-only
permissions are not labeled high-impact merely because their domain is sensitive.

## Policy and dependency boundaries

- Working windows, proficiency meanings, required certifications, temporary timed
  restrictions, training curricula, and persistent named crews remain unconfigured
  or dependency-blocked. ACP does not invent 8–5 schedules or HR policy.
- Certification expiration is recorded evidence. It disqualifies work only through
  an approved requirement/readiness policy.
- Workforce capability is evidence, never application permission.
- Timekeeping, Scheduling, Dispatch, Payroll, Communications, Mobile, and Migration
  retain their own mutation authority.
- Transactional delivery currently reports provider readiness from Communications.
  Owner-mediated non-Production activation is not email delivery.

## Real-company acceptance script

1. Enter the owner-confirmed unique email and Employee display identity.
2. Select explicit Company Branch access; never default to all Branches.
3. Select a canonical baseline role based on duties, not title inference.
4. Review role defaults, explicit additions, own-data and Branch limits.
5. Confirm each high-impact permission.
6. Review the read-only onboarding plan and resolve every collision/blocker.
7. Apply once and verify the resulting identity and authorization version.
8. Create the protected invitation and inspect Communications delivery truth.
9. The Employee activates their own credential and signs in.
10. Verify intended API and UI allows/denies, then Branch and permission revocation.
11. If ACP Employee is used, execute the separately owned physical-device matrix.
12. Record support/recovery evidence without secrets.

No real Employee, including Lianne Hernandez, is created by this program. A future
authorized step must supply her exact email, Branch, duties/baseline role, explicit
permission decisions, high-impact confirmations, optional Workforce evidence, and
delivery method.

## Adoption checklist

Admit a real source; review the Migration crosswalk; disposition every identity;
confirm Branches; review roles and explicit permissions; establish only necessary
Workforce evidence; verify provider or approved Preview fallback; activate; qualify
Mobile and Timekeeping; exercise revocation; and establish support ownership. Bulk
review is bounded candidate-by-candidate and never bulk-grants high-impact authority.
