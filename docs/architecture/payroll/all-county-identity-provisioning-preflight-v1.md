# All County Identity Provisioning Preflight v1

Inspection date: 2026-08-28

Repository authority at inspection: `f6a1e45`

Scope: authoritative repository contracts plus read-only ACP Preview metadata.
No HCP or QBO identity evidence was accessed or used. No identity, credential,
permission, Branch, compensation, Timekeeping, or Payroll record was mutated.

## Existing unmatched identity

The one active tenant identity is:

- display identity: `Preview Administrator`;
- owner-safe login indicator: `p***@allcountyhomeservices.com`;
- Company: `All County Plumbing & Leak` (`ACP`);
- User and Membership: active;
- login email: verified;
- credential record: present;
- default Branch: `Main Branch`;
- all-Branch access: enabled;
- role: `COMPANY_ADMINISTRATOR`;
- created: 2026-07-20;
- native Employee linkage: none.

Classification: `POSSIBLE_MATCH_OWNER_REVIEW_REQUIRED`. The record is
authoritatively the existing Preview administrator identity, but ACP contains no
evidence binding it to Michael Fouse or another intended Employee. It must not be
reused as an Employee login until the owner confirms its human owner. If it is a
platform-only administrator account, classify it `NOT_AN_IN_SCOPE_EMPLOYEE` and
leave it unlinked.

## Company and Branch authority

The canonical tenant is `All County Plumbing & Leak`, Company code `ACP`, active,
with timezone `America/New_York`.

Exactly one active, non-archived Branch exists:

| Branch | Code | Authority | Timezone |
|---|---|---|---|
| Main Branch | `MAIN` | Explicit primary Branch | `America/New_York` |

The native access model has an optional Membership default Branch, explicit
Membership-to-Branch grants, and an all-Branch flag. Employee home Branch is
Company-bound independently. Database constraints reject cross-Company default
or home Branch relationships.

`MAIN` is the only authoritative initial home/default Branch candidate for all
eight. No native Employee, role, or Job-classification evidence establishes a
different Branch. Owner confirmation is still required before assignment.

## Employee-number mechanism

`Employee.employee_number` is required, non-blank, at most 50 characters, and
unique among non-archived Employees within a Company. It is not globally unique.
There is no accepted automatic generator or next-number allocator. HCP identifiers
must not be used.

Proposed Company-scoped scheme for approval: `EMP-0001`, `EMP-0002`, and so on.
The provisioning implementation should serialize allocation per Company, reject
collisions, and never reuse an archived Employee number. This packet does not
allocate any number.

## Login and invitation input

Native User login requires a globally unique normalized email, name fields, and
a secure credential. Phone is neither stored nor required by the current native
User authentication contract. ACP contains no authoritative named User/contact
record for any of the eight.

The authentication domain supports hashed credentials, single-use email
verification, password reset, token revocation, and secure password policy. The
ordinary runtime does **not** yet expose a User/Employee onboarding or invitation
creation service; only the one-time platform bootstrap creates a User and initial
credential. `PAYROLL.IDENTITY.PROVISIONING.1` therefore needs a minimal native,
audited, idempotent onboarding service that composes existing authentication
primitives. It must never return or persist plaintext invitation credentials.

Owner input required for every intended Employee: the intended login email,
supplied through the future protected provisioning operation. No email should be
committed to this document.

## Proposed provisioning matrix

All rows remain `ONBOARDING_REQUIRED` and `COMPENSATION_INPUT_REQUIRED`.

| Person | Pay/class context | Employee/User action | Proposed Branch | Login input | Timekeeping role | Post-identity Payroll blockers |
|---|---|---|---|---|---|---|
| Michael Fouse | Salaried; owner/management | Create Employee; create User unless owner confirms the administrator account is his intended login; bind verified Membership | `MAIN`, owner confirmation required | Protected email required, or explicit reuse confirmation | Base Employee only unless separately approved | Compensation, policy activation, time/attendance evidence as required, approval |
| Lianne Hernandez | Salaried; office/management | Create Employee, User, Membership, and linkage | `MAIN`, owner confirmation required | Protected email required | Base Employee only unless separately approved | Compensation, policy activation, time/attendance evidence as required, approval |
| Alex Donahue | Hourly supervisor | Create Employee, User, Membership, and linkage | `MAIN`, owner confirmation required | Protected email required | Base Employee; supervisor permissions require four explicit decisions | Compensation, approved time, policy activation, approval |
| Melvin Santiago | Hourly labor | Create Employee, User, Membership, and linkage | `MAIN`, owner confirmation required | Protected email required | Base Employee | Compensation, approved time, policy activation, approval |
| Adam Mari | Hourly labor | Create Employee, User, Membership, and linkage | `MAIN`, owner confirmation required | Protected email required | Base Employee | Compensation, approved time, policy activation, approval |
| Dareis Montgomery | Hourly labor | Create Employee, User, Membership, and linkage | `MAIN`, owner confirmation required | Protected email required | Base Employee | Compensation, approved time, policy activation, approval |
| Dakota Wilcox | Hourly labor | Create Employee, User, Membership, and linkage | `MAIN`, owner confirmation required | Protected email required | Base Employee | Compensation, approved time, policy activation, approval |
| Jason Calci | Hourly labor | Create Employee, User, Membership, and linkage | `MAIN`, owner confirmation required | Protected email required | Base Employee | Compensation, approved time, policy activation, approval |

Salaried attendance remains independent from salary calculation. Alex's worker
class and straight-time overtime exception grant no authorization permissions.

## Timekeeping permission decisions

The six native Timekeeping permissions exist and are active. No current Company
role carries them.

Base Employee role proposed for all eight:

- `COMPANY_TIMEKEEPING_OWN_PUNCH`;
- `COMPANY_TIMEKEEPING_OWN_READ`.

The current submission service uses `OWN_PUNCH` for an Employee submitting their
own recorded/corrected entry; no separate own-submit permission exists.

Salaried management receives no manager authority automatically. For Alex, the
owner must answer YES or NO independently for:

1. `COMPANY_TIMEKEEPING_MANUAL_ENTRY`;
2. `COMPANY_TIMEKEEPING_CORRECT`;
3. `COMPANY_TIMEKEEPING_APPROVE`;
4. `COMPANY_TIMEKEEPING_ADMIN_READ`.

If approved, those permissions should be composed in a narrow Company role rather
than added to `COMPANY_USER`. No Timekeeping role may grant Payroll policy,
compensation, calculation, approval, payment, or Company administration.

## Owner decisions required

1. YES/NO: Is `Preview Administrator` the intended login identity for Michael
   Fouse? If NO, leave it as an unlinked administrator.
2. YES/NO: Use `MAIN` as home/default Branch for all eight?
3. YES/NO: Approve the Company-scoped `EMP-####` Employee-number scheme and an
   atomic allocator that never reuses archived numbers?
4. Provide each intended login email through the protected provisioning path.
5. YES/NO separately for each of Alex's four supervisor permissions above.
6. Identify any manager other than Alex who should later receive manual-entry,
   correction, approval, or administrative-read authority. Absence means no grant.

## Exact provisioning sequence

1. Lock the Company-scoped provisioning operation and re-read current identities.
2. Resolve the administrator disposition before considering reuse.
3. Normalize and check the protected login email globally; reject any unexplained
   existing User rather than matching it.
4. Resolve or atomically allocate the approved Company Employee number.
5. Create the native Employee in `ACP` with `MAIN` only after owner approval.
6. Create a User only when no verified User exists; otherwise verify ownership and
   active status before reuse.
7. Create or verify the unique `User + Company` Membership using the existing
   idempotent Company-administration service.
8. Set/verify default Branch and explicit Branch access in the same Company.
9. Establish the credential through the new protected invitation composition;
   store only hashes and deliver any one-time token out of band.
10. Bind `Employee.membership_id` only after Company, User, Membership, and Branch
    identity checks pass.
11. Create/verify narrow Timekeeping roles, assign only approved permissions, and
    bind roles through existing Membership-role administration.
12. Verify authenticated Membership-to-Employee Workday self-resolution and reject
    any duplicate/cross-Company result.
13. Re-run Payroll identity admission. Compensation, policy, time, and approval
    blockers remain separate.

The accepted order differs slightly from creating Employee first in every case:
User reuse and email collision must be resolved before committing a new linked
identity. The implementation should keep creation/linkage atomic where possible
and leave no partially authoritative login chain after failure.

## Duplicate and idempotency safeguards

- User: normalize email and lock/check the globally unique
  `users.normalized_email`; existing unexplained identity fails closed.
- Membership: lock/check `user_id + company_id`; the accepted service returns an
  identical existing Membership but rejects different requested state.
- Employee: lock Company and check employee number, intended identity attributes,
  and any Membership link; `membership_id` is unique and Company-bound.
- Employee number: allocate under a Company transaction lock; active-number
  uniqueness is database enforced.
- Invitation: permit one active invitation transaction per User, revoke/supersede
  prior unused verification material, and make retries return safe status rather
  than issue parallel identities.
- Branch: require active Branch ownership in `ACP`; composite foreign keys reject
  cross-Company default/home Branch assignment.
- Linkage: require the exact verified User→ACP Membership chain and zero existing
  Employee links before setting `Employee.membership_id`.
- Roles: existing role/permission and Membership-role assignments are idempotent;
  do not alter the administrator role or broad `COMPANY_USER` role.

## Mobile and first-Payroll effect

The mobile UI can be implemented now against the accepted API and synthetic
identities. Successful provisioning would unlock employee login and Workday
self-resolution. Real punch activation would additionally require deployed mobile
UI/runtime, the Base Employee Timekeeping role, active Branch context, HTTPS/session
qualification, and an explicit non-production activation milestone.

After identity provisioning, each Employee remains blocked from first Payroll by
protected compensation authority. Hourly Employees also require approved Workday
Time; salaried admission follows the approved attendance-only policy rather than
hours-times-rate. Company Payroll policy activation, configured pay period, sealed
time inputs where required, and human approval remain runtime gates. Identity
provisioning performs none of them.

## Next implementation boundary

Before eight-person provisioning can execute, the product needs the bounded native
onboarding composition absent from the current runtime:

`PAYROLL.IDENTITY.PROVISIONING.1 — Native User/Employee Invitation, Membership,
Branch, Linkage, and Narrow Timekeeping Role Provisioning`.

That milestone should implement and validate the generic onboarding service, then
apply it only after the six owner decision groups above are answered. Compensation
authority and Payroll calculation remain separate milestones.
