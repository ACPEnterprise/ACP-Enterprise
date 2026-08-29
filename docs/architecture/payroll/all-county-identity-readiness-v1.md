# All County Payroll Identity Readiness v1

Inspection time: 2026-08-29T00:46:40Z

Repository authority: `348c235568a8a6afae3ac968f25f7c94c7b6b337`

Runtime inspected: isolated ACP Preview, read-only PostgreSQL metadata queries.
No HCP or QBO evidence was accessed or used.

## Authoritative runtime summary

The active All County Company tenant contains:

- zero native Employee records;
- one active Membership and one User, with no Employee linkage;
- zero configured Timekeeping pay periods;
- zero approved Workday Time entries;
- zero approved Payroll policy records;
- zero approved compensation authorities.

The existing User/Membership pair was not matched to an intended Employee. A
name-only, email-like, phone, HCP, or job-history association is insufficient.
Owner resolution must determine whether it belongs to an in-scope person before
any linkage is proposed.

## Readiness matrix

`ONBOARDING_REQUIRED` is the classification for each person because the
authoritative Company tenant has no Employee records. User and Membership state
remain unresolved rather than inferred from the unmatched tenant identity.

| Name | Pay type | Worker class | Employee | User | Membership | Employee/User linkage | Branch | Workday | Payroll identity | Compensation | Blocker | Next action |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Michael Fouse | Salaried | Owner / salaried management | Missing | No exact native candidate | No attributable Membership | Missing | Unassigned | Not ready | Not ready | Input required | `ONBOARDING_REQUIRED` | Resolve unmatched tenant identity; then create or verify User/Membership, create Employee, bind verified Membership, assign Branch, and qualify login |
| Lianne Hernandez | Salaried | Salaried office / management | Missing | No exact native candidate | No attributable Membership | Missing | Unassigned | Not ready | Not ready | Input required | `ONBOARDING_REQUIRED` | Resolve unmatched tenant identity; then create or verify User/Membership, create Employee, bind verified Membership, assign Branch, and qualify login |
| Alex Donahue | Hourly | Hourly supervisor | Missing | No exact native candidate | No attributable Membership | Missing | Unassigned | Not ready | Not ready | Input required | `ONBOARDING_REQUIRED` | Resolve unmatched tenant identity; then create or verify User/Membership, create Employee, bind verified Membership, assign Branch, and qualify login; later bind worker class in compensation authority |
| Melvin Santiago | Hourly | Hourly labor | Missing | No exact native candidate | No attributable Membership | Missing | Unassigned | Not ready | Not ready | Input required | `ONBOARDING_REQUIRED` | Resolve unmatched tenant identity; then create or verify User/Membership, create Employee, bind verified Membership, assign Branch, and qualify login |
| Adam Mari | Hourly | Hourly labor | Missing | No exact native candidate | No attributable Membership | Missing | Unassigned | Not ready | Not ready | Input required | `ONBOARDING_REQUIRED` | Resolve unmatched tenant identity; then create or verify User/Membership, create Employee, bind verified Membership, assign Branch, and qualify login |
| Dareis Montgomery | Hourly | Hourly labor | Missing | No exact native candidate | No attributable Membership | Missing | Unassigned | Not ready | Not ready | Input required | `ONBOARDING_REQUIRED` | Resolve unmatched tenant identity; then create or verify User/Membership, create Employee, bind verified Membership, assign Branch, and qualify login |
| Dakota Wilcox | Hourly | Hourly labor | Missing | No exact native candidate | No attributable Membership | Missing | Unassigned | Not ready | Not ready | Input required | `ONBOARDING_REQUIRED` | Resolve unmatched tenant identity; then create or verify User/Membership, create Employee, bind verified Membership, assign Branch, and qualify login |
| Jason Calci | Hourly | Hourly labor | Missing | No exact native candidate | No attributable Membership | Missing | Unassigned | Not ready | Not ready | Input required | `ONBOARDING_REQUIRED` | Resolve unmatched tenant identity; then create or verify User/Membership, create Employee, bind verified Membership, assign Branch, and qualify login |

Aggregate classification:

- `READY_NATIVE_IDENTITY`: 0
- `ONBOARDING_REQUIRED`: 8
- `AMBIGUOUS_IDENTITY`: 0 named records, with one unmatched tenant identity
  requiring owner disposition
- `INACTIVE_IDENTITY`: 0
- `NOT_FOUND`: 0 final classifications; absence is handled as onboarding rather
  than claiming name-only proof

## Accepted linkage

The native self-service chain is:

`User → active Company Membership → Employee.membership_id → active Employee`

The Employee and Membership are both Company-bound. Home/default Branch and
explicit Branch access must belong to that same Company. Workday self-resolution
fails closed unless the authenticated Membership links to one active Employee.
Cross-Company identities cannot satisfy the relationship constraints.

For Payroll identity readiness, the same Employee must then bind to:

- the effective Company Payroll policy;
- a protected effective compensation authority;
- the matching pay period;
- a sealed approved `payroll.time-input.v1`.

None of those runtime authorities currently exists in Preview.

## Protected onboarding plan

No steps below are executed by this milestone.

1. Owner resolves the unmatched existing User/Membership identity using trusted
   business evidence outside name similarity. Select reuse or leave unrelated.
2. Create one native Workforce Employee per intended person with Company,
   owner-approved Employee number, active status, and home Branch.
3. For each person without a verified User, use native Enterprise invitation and
   credential-establishment workflows. Never create or transmit passwords in a
   readiness document.
4. Create or verify one active Company Membership per User, with default Branch
   and explicit Branch access.
5. Bind `Employee.membership_id` only after User ownership and Company scope are
   verified. Reject duplicate Membership or Employee candidates.
6. Verify the Employee, Membership, User, credential, Company, and Branch are
   active and mutually scoped.
7. Assign only the approved Timekeeping role permissions. Do not derive roles
   automatically from worker class.
8. Re-run native identity readiness and Workday self-resolution.
9. In separate milestones, activate All County Payroll policy, enter protected
   compensation authority, configure the pay period, and approve time evidence.

Any ambiguous match stops at owner resolution. The plan creates no parallel
authentication or identity system.

## Permission plan

Employee mobile role:

- `COMPANY_TIMEKEEPING_OWN_PUNCH`
- `COMPANY_TIMEKEEPING_OWN_READ`

Manager/supervisor functions are separately granted only when authorized:

- `COMPANY_TIMEKEEPING_MANUAL_ENTRY`
- `COMPANY_TIMEKEEPING_CORRECT`
- `COMPANY_TIMEKEEPING_APPROVE`
- `COMPANY_TIMEKEEPING_ADMIN_READ` only when operationally required

Payroll policy, compensation, and admission permissions remain separate. Alex's
`hourly_supervisor` class grants no Timekeeping-manager, Payroll, compensation,
or approval permission by itself. Employees cannot approve their own time.

## Salaried boundary

Michael and Lianne are intended salaried Employees. Workday is attendance-only
under All County policy v1.1 unless a later approved policy requires time for
Payroll admission. Time entries do not multiply salary and no hourly rate is
derived.

## Compensation boundary

Every person remains `COMPENSATION_INPUT_REQUIRED`. No monetary value was
inspected or recorded. Later entry must use the protected
`payroll.compensation-authority.v1` runtime with explicit approval.

## Mobile and Payroll sequencing

`TIME.WORKDAY.MOBILE.1` implementation can proceed independently against the
accepted APIs and synthetic identities. Real Employee mobile activation remains
blocked until native onboarding, Membership linkage, credential establishment,
Branch scope, permissions, and a non-production deployment are separately
authorized.

The next Payroll operation must be identity provisioning/linkage. Compensation
entry and Payroll calculation remain separate successor milestones.
