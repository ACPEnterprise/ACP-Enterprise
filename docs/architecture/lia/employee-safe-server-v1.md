# LIA employee-safe server v1

`LIA.EMPLOYEE_SAFE.v1` is the Mobile-facing, read-only boundary over ACP's shared
LIA response contract. ACP Employee calls `POST /api/v1/lia/employee/ask`; it must
not call the owner-oriented `POST /api/v1/lia/ask` route.

The route requires current ACP authentication, an active Company Membership, the
canonical `ACP_EMPLOYEE_MOBILE` role, and the explicit
`COMPANY_EMPLOYEE_OPERATIONS_OWN_LIA_READ` permission. The standard authorization
dependency rejects disabled/archived Users, inactive Memberships, inactive
Companies, stale credential/authorization versions, and unauthorized Company or
Branch headers before the LIA service runs. The service then resolves the active
Employee through the existing Employee Operations projection.

## Capability policy

- **Employee-safe:** the authenticated Employee's bounded My Day/assigned-work
  projection and an explicitly selected, currently assigned Job's field-readiness
  projection.
- **Role/permission-gated:** assigned Job context additionally requires the
  existing `COMPANY_JOB_READ` permission and current primary/crew assignment in an
  authorized Branch.
- **Owner/admin-only:** Company profitability, Economics/Luminary, Beacon,
  Payroll, compensation, Company financials, payments, unrestricted Customer
  history, other Employees, and administrative evidence are denied before source
  retrieval.

Client-supplied Company, Branch, Job, Appointment, role, or permission claims never
grant authority. A Job identifier is usable only after the existing Field Service
authority revalidates Company, authorized Branch, active Employee identity, and
current assignment. Unknown and foreign records use the same existence-hiding
response.

Responses retain the shared `LiaResponse` envelope: classification, authority,
limitations, source contract, as-of/freshness, evidence digest, authorization
version, Company/Branch scope, and safe navigation. Evidence is limited to
`EMPLOYEE.DAY.v1` and `FIELD.JOB.STATE.v1`; prompts and transcripts are not stored.
No mutation or provider call exists on this route.

## Release dependency

There is no schema migration. Before enabling the Mobile surface, Enterprise must
run the existing permission-catalog synchronization, then the existing canonical
role reconciliation for each tenant so `ACP_EMPLOYEE_MOBILE` receives the new
permission and affected Users receive a new authorization version. Until both are
complete, the route correctly returns `403`.

## Phone/C integration

Phone/C should send the normal bearer token, `X-Company-ID`, optional
`X-Branch-ID`, and a strict `LiaRequest` body to `/api/v1/lia/employee/ask`. It may
pass a `jobs` context with an opaque Job ID and prior evidence digest; the server
still revalidates assignment. `UNAUTHORIZED`, `UNAVAILABLE`, and `STALE` must remain
terminal/refresh states, not client-side fallbacks to the broad LIA route.
